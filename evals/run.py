"""Прогон набора задач и сводка метрик.

Задание требует измеримого качества, а не ощущения «вроде работает». Здесь
каждая задача из tasks.yaml запускается N раз, результат сверяется с ожиданием,
и печатается таблица: доля успеха, шаги, токены, время, ошибки.

Запуск:
    .venv/Scripts/python evals/run.py                  # всё, кроме требующего логина
    .venv/Scripts/python evals/run.py --repeat 3       # три прогона на задачу
    .venv/Scripts/python evals/run.py --tag smoke      # только smoke
    .venv/Scripts/python evals/run.py --id vacancies   # одна задача
    .venv/Scripts/python evals/run.py --with-login     # включая почту

Браузер и роутер общие на весь набор: поднимать их на каждую задачу дорого.
Но перед каждым прогоном браузер сбрасывается до одной пустой вкладки —
иначе задачи заражают друг друга оставленным состоянием.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.browser import BrowserController, BrowserUnavailable  # noqa: E402
from agent.config import Settings, load_settings  # noqa: E402
from agent.core.loop import SYSTEM_PROMPT_FILE, AgentLoop, RunResult  # noqa: E402
from agent.llm import LLMRouter  # noqa: E402
from agent.tools import build_registry  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")

TASKS_FILE = Path(__file__).parent / "tasks.yaml"
RESULTS_FILE = Path(__file__).parent / "results.json"

GREEN, RED, DIM, BOLD, OFF = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[1m", "\x1b[0m"


@dataclass(slots=True)
class Case:
    id: str
    task: str
    tags: list[str] = field(default_factory=list)
    needs_login: bool = False
    max_steps: int | None = None
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Attempt:
    case_id: str
    run: int
    passed: bool
    reasons: list[str]
    steps: int
    tokens_in: int
    tokens_out: int
    elapsed_s: float
    errors: dict[str, int]
    run_id: str

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def load_cases(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = []
    for item in raw.get("tasks", []):
        cases.append(
            Case(
                id=str(item["id"]),
                task=" ".join(str(item["task"]).split()),
                tags=[str(t) for t in item.get("tags", [])],
                needs_login=bool(item.get("needs_login", False)),
                max_steps=item.get("max_steps"),
                expect=dict(item.get("expect") or {}),
            )
        )
    return cases


def judge(case: Case, result: RunResult) -> list[str]:
    """Причины провала. Пустой список — задача зачтена."""
    reasons: list[str] = []
    expect = case.expect

    if "success" in expect and bool(expect["success"]) != result.success:
        reasons.append(f"успех {result.success}, ожидался {expect['success']}")

    report = result.summary.lower()
    for needle in expect.get("mentions", []):
        if str(needle).lower() not in report:
            reasons.append(f"в отчёте нет «{needle}»")

    forbidden = set(expect.get("forbid_errors", []))
    for kind, count in result.error_counts.items():
        if kind in forbidden:
            reasons.append(f"ошибка {kind}×{count}")

    # Потолок шагов проверять отдельно не нужно: его держит Budget, а упёршийся
    # прогон и так приходит с success=False.
    return reasons


#: нейтральная стартовая страница — на ней нет ничего, что можно принять за задачу
BLANK = "about:blank"


async def reset_browser(controller: BrowserController) -> None:
    """Возвращает браузер в исходное состояние: одна пустая вкладка.

    Без этого задачи заражают друг друга. В замере vacancies первым действием
    агента был `switch_tab index=3` — он подхватил вкладку, оставленную
    предыдущим кейсом, и продолжил работать в чужом контексте. Цифры при таком
    старте несравнимы: результат зависит от того, что натворил сосед по набору.

    Профиль (`browser-agent-profile`) отдельный от личного Chrome, а логины
    живут в куках, а не во вкладках, — закрытие вкладок ничего не теряет.
    """
    for index in range(len(controller.pages) - 1, 0, -1):
        with contextlib.suppress(Exception):
            await controller.close_tab(index)
    with contextlib.suppress(Exception):
        await controller.switch_tab(0)
        await controller.goto(BLANK)


async def run_case(
    settings: Settings,
    controller: BrowserController,
    router: LLMRouter,
    case: Case,
    run_index: int,
) -> Attempt:
    await reset_browser(controller)
    if case.max_steps:
        settings = dataclasses.replace(settings, max_steps=case.max_steps)
    router.budget.reset()
    router.budget.max_steps = settings.max_steps

    loop = AgentLoop(
        settings=settings,
        controller=controller,
        router=router,
        registry=build_registry(),
        on_event=_progress,
    )
    result = await loop.run(case.task)
    reasons = judge(case, result)

    return Attempt(
        case_id=case.id,
        run=run_index,
        passed=not reasons,
        reasons=reasons,
        steps=result.steps,
        tokens_in=result.usage.input_tokens,
        tokens_out=result.usage.output_tokens,
        elapsed_s=round(result.elapsed_s, 1),
        errors=result.error_counts,
        run_id=result.run_id,
    )


def crashed(case: Case, run_index: int, error: Exception) -> Attempt:
    """Задача, не дошедшая до вердикта, записывается как провал с причиной."""
    return Attempt(
        case_id=case.id,
        run=run_index,
        passed=False,
        reasons=[f"прогон упал: {type(error).__name__}: {error}"[:200]],
        steps=0,
        tokens_in=0,
        tokens_out=0,
        elapsed_s=0.0,
        errors={"crash": 1},
        run_id="",
    )


def _progress(kind: str, data: dict) -> None:
    if kind == "step":
        print(f"{DIM}  шаг {data['index']} · {data['url'][:60]}{OFF}")
    elif kind == "tool_call":
        print(f"{DIM}    → {data['name']}{OFF}")


async def main(args: argparse.Namespace) -> int:
    cases = load_cases(TASKS_FILE)
    if args.id:
        cases = [c for c in cases if c.id in args.id]
    if args.tag:
        cases = [c for c in cases if set(args.tag) & set(c.tags)]
    if not args.with_login:
        cases = [c for c in cases if not c.needs_login]
    if not cases:
        print("нечего запускать — проверьте --id / --tag")
        return 1

    # Память между сессиями на замерах выключена: иначе второй прогон стартует
    # не с того же места, что первый, и цифры перестают быть сравнимыми.
    settings = dataclasses.replace(load_settings(), persist_memory=False)
    controller = BrowserController(settings)
    await controller.start()
    router = LLMRouter(settings)

    attempts: list[Attempt] = []
    started = time.monotonic()
    try:
        for case in cases:
            for run_index in range(1, args.repeat + 1):
                print(f"\n{BOLD}▸ {case.id} · прогон {run_index}/{args.repeat}{OFF}")
                print(f"{DIM}  {case.task[:110]}{OFF}")
                try:
                    attempt = await run_case(settings, controller, router, case, run_index)
                except Exception as e:
                    # Упавшая задача — это результат «провал», а не конец набора.
                    # Замер `order_form`+`vacancies` уже терялся целиком из-за
                    # исключения на 22-м шаге второй задачи: первая была пройдена,
                    # но сводка не дошла до диска (docs/DECISIONS.md ADR-031).
                    logging.getLogger("evals").exception("задача %s упала", case.id)
                    attempt = crashed(case, run_index, e)
                attempts.append(attempt)
                mark = f"{GREEN}зачтено{OFF}" if attempt.passed else f"{RED}провал{OFF}"
                print(f"  {mark} · шагов {attempt.steps} · {attempt.elapsed_s} c")
                for reason in attempt.reasons:
                    print(f"{RED}    — {reason}{OFF}")
                if not controller.connected:
                    print(f"{RED}  браузер закрыт — остаток набора пропущен{OFF}")
                    raise BrowserUnavailable("Chrome закрылся посреди набора")
    except KeyboardInterrupt:
        print("\nпрервано, печатаю то, что успели")
    except BrowserUnavailable as e:
        print(f"{RED}{e}{OFF}")
    finally:
        await router.aclose()
        with contextlib.suppress(Exception):
            await controller.close()

    summarize(cases, attempts, time.monotonic() - started, args.out)
    return 0 if all(a.passed for a in attempts) else 1


def summarize(
    cases: list[Case], attempts: list[Attempt], elapsed: float, out: Path = RESULTS_FILE
) -> None:
    if not attempts:
        return

    print(f"\n{BOLD}── сводка ──{OFF}")
    header = f"{'задача':<16}{'успех':>8}{'шаги':>8}{'ток. вх':>10}{'ток. вых':>10}{'время':>8}"
    print(DIM + header + OFF)

    rows = []
    for case in cases:
        mine = [a for a in attempts if a.case_id == case.id]
        if not mine:
            continue
        passed = sum(a.passed for a in mine)
        rate = passed / len(mine)
        row = {
            "id": case.id,
            "runs": len(mine),
            "passed": passed,
            "success_rate": round(rate, 2),
            "steps_median": statistics.median(a.steps for a in mine),
            "tokens_in_median": statistics.median(a.tokens_in for a in mine),
            "tokens_out_median": statistics.median(a.tokens_out for a in mine),
            "seconds_median": statistics.median(a.elapsed_s for a in mine),
        }
        rows.append(row)
        colour = GREEN if rate == 1 else RED if rate == 0 else ""
        print(
            f"{case.id:<16}{colour}{passed}/{len(mine):<6}{OFF}"
            f"{row['steps_median']:>8.0f}{row['tokens_in_median']:>10.0f}"
            f"{row['tokens_out_median']:>10.0f}{row['seconds_median']:>8.0f}"
        )

    total_passed = sum(a.passed for a in attempts)
    print(
        f"\nвсего {total_passed}/{len(attempts)} "
        f"({total_passed / len(attempts):.0%}), набор занял {elapsed / 60:.1f} мин"
    )

    payload = {
        "at": time.strftime("%Y-%m-%d %H:%M"),
        # Без этих двух полей результаты двух прогонов невозможно отличить
        # задним числом, а сравнивать редакции промпта иначе бессмысленно.
        "prompt": SYSTEM_PROMPT_FILE,
        "provider": os.getenv("LLM_PROVIDER", "?"),
        "summary": rows,
        "attempts": [a.as_dict() for a in attempts],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{DIM}подробности: {out}{OFF}")


def cli() -> int:
    parser = argparse.ArgumentParser(prog="evals")
    parser.add_argument("--repeat", type=int, default=1, help="прогонов на задачу")
    parser.add_argument("--id", nargs="*", help="только эти задачи")
    parser.add_argument("--tag", nargs="*", help="только задачи с этими ярлыками")
    parser.add_argument(
        "--with-login", action="store_true", help="включая требующие залогиненного профиля"
    )
    parser.add_argument("--out", type=Path, default=RESULTS_FILE, help="куда положить подробности")
    args = parser.parse_args()
    try:
        return asyncio.run(main(args))
    except BrowserUnavailable as e:
        print(f"\n{RED}{e}{OFF}\n")
        return 1


if __name__ == "__main__":
    sys.exit(cli())
