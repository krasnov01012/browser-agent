"""Точка входа.

python -m agent.main --task "..."   разовый запуск
python -m agent.main --cli          диалог в терминале
python -m agent.main --mcp          MCP-сервер по stdio
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
from collections.abc import Callable

from .browser import BrowserController, BrowserUnavailable
from .config import Settings, load_settings
from .core.loop import AgentLoop, RunResult
from .llm import LLMRouter
from .tools import build_registry

log = logging.getLogger(__name__)

DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
OFF = "\x1b[0m"


def console_sink(verbose: bool) -> Callable[[str, dict], None]:
    """Печать хода работы. То, что видно на видео."""

    def emit(kind: str, data: dict) -> None:
        if kind == "step":
            print(
                f"\n{DIM}── шаг {data['index']} · {data['url'][:70]} · "
                f"{data['elements']} элементов · ~{data['state_tokens']} токенов{OFF}"
            )
        elif kind == "thought" and verbose:
            text = " ".join(data["text"].split())[:280]
            print(f"{DIM}   думает: {text}{OFF}")
        elif kind == "tool_call":
            args = ", ".join(f"{k}={v!r}" for k, v in data["arguments"].items())
            print(f"{CYAN}   → {data['name']}({args}){OFF}")
        elif kind == "tool_error":
            print(f"{RED}   ✗ {data['name']}: {data['kind']}{OFF}")
        elif kind == "tool_result" and not data.get("error"):
            print(f"{DIM}   ← {' '.join(data['text'].split())[:200]}{OFF}")
        elif kind == "warning":
            print(f"{YELLOW}   ! {data['text']}{OFF}")
        elif kind == "question":
            print(f"\n{BOLD}{YELLOW}? {data['text']}{OFF}")

    return emit


async def ask_in_terminal(question: str) -> str:
    answer = await asyncio.to_thread(input, f"{BOLD}> {OFF}")
    return answer.strip() or "пользователь ничего не ответил"


async def run_task(settings: Settings, task: str, *, verbose: bool) -> RunResult:
    controller = BrowserController(settings)
    await controller.start()
    router = LLMRouter(settings)
    try:
        loop = AgentLoop(
            settings=settings,
            controller=controller,
            router=router,
            registry=build_registry(),
            on_event=console_sink(verbose),
            ask_user=ask_in_terminal,
        )
        return await loop.run(task)
    finally:
        await router.aclose()
        await controller.close()


async def repl(settings: Settings, *, verbose: bool) -> int:
    controller = BrowserController(settings)
    await controller.start()
    router = LLMRouter(settings)
    registry = build_registry()
    print(f"{GREEN}Агент готов. Опишите задачу, пустая строка — выход.{OFF}")
    try:
        while True:
            task = (await asyncio.to_thread(input, f"\n{BOLD}задача> {OFF}")).strip()
            if not task:
                return 0
            router.budget.reset()
            loop = AgentLoop(
                settings=settings,
                controller=controller,
                router=router,
                registry=registry,
                on_event=console_sink(verbose),
                ask_user=ask_in_terminal,
            )
            result = await loop.run(task)
            print(_format(result))
    except (EOFError, KeyboardInterrupt):
        return 0
    finally:
        await router.aclose()
        await controller.close()


def _format(result: RunResult) -> str:
    mark = f"{GREEN}готово{OFF}" if result.success else f"{RED}не доведено{OFF}"
    return f"\n{BOLD}── {mark} ──{OFF}\n{result.report()}"


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="browser-agent")
    parser.add_argument("--task", help="выполнить одну задачу и выйти")
    parser.add_argument("--cli", action="store_true", help="диалог в терминале")
    parser.add_argument("--ui", action="store_true", help="веб-панель")
    parser.add_argument("--mcp", action="store_true", help="MCP-сервер по stdio")
    parser.add_argument("-v", "--verbose", action="store_true", help="показывать ход мысли")
    parser.add_argument("--debug", action="store_true", help="подробные логи")
    parser.add_argument(
        "--confirm-destructive",
        action="store_true",
        help="спрашивать подтверждение перед необратимыми действиями",
    )
    parser.add_argument(
        "--no-memory", action="store_true", help="не переносить факты между запусками"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    try:
        settings = load_settings()
    except ValueError as e:
        # В stderr, а не в stdout: с --mcp стандартный вывод занят протоколом,
        # и посторонняя строка в нём — это порванное рукопожатие вместо
        # понятного сообщения в журнале клиента.
        print(f"{RED}Конфигурация: {e}{OFF}", file=sys.stderr)
        return 1

    overrides: dict[str, bool] = {}
    if args.confirm_destructive:
        overrides["confirm_destructive"] = True
    if args.no_memory:
        overrides["persist_memory"] = False
    if overrides:
        settings = dataclasses.replace(settings, **overrides)

    try:
        if args.mcp:
            from .mcp.server import serve_stdio

            # Ни одной печати в stdout: там протокол (docs/DECISIONS.md ADR-040).
            asyncio.run(serve_stdio(settings))
            return 0
        if args.ui:
            from .ui.server import serve

            print(f"{GREEN}Панель: http://{settings.ui_host}:{settings.ui_port}{OFF}")
            serve(settings)
            return 0
        if args.task:
            result = asyncio.run(run_task(settings, args.task, verbose=args.verbose))
            print(_format(result))
            return 0 if result.success else 1
        return asyncio.run(repl(settings, verbose=args.verbose))
    except BrowserUnavailable as e:
        print(f"\n{RED}{e}{OFF}\n")
        return 1
    except KeyboardInterrupt:
        print("\nпрервано")
        return 130


def mcp_cli() -> int:
    """Отдельная команда `browser-agent-mcp` — то же, что `--mcp`.

    Нужна ради конфигурации MCP-клиентов: в них указывается одна команда,
    и «запустите с флагом» там читается хуже, чем отдельное имя. Остальные
    флаги (`--debug`) при этом продолжают работать.
    """
    return cli(["--mcp", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(cli())
