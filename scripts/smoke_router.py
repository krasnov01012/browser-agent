"""Сквозная проверка слоя LLM: config -> router -> провайдер -> разбор ответа.

В отличие от smoke_llm.py (сырой HTTP, без зависимостей) здесь проверяется
реальный код агента: роли, цепочка фоллбэка, учёт токенов, парсинг tool call.

Запуск:  .venv/Scripts/python scripts/smoke_router.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import load_settings
from agent.llm import LLMRouter, Message, ToolSpec

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")

# Инструмент нарочно такой же формы, как боевой click: агент обязан выбрать
# ref из снапшота, а не выдумать селектор.
CLICK = ToolSpec(
    name="click",
    description="Click an element from the current page snapshot.",
    parameters={
        "type": "object",
        "properties": {
            "ref": {"type": "string", "description": "Element ref, e.g. e21"},
            "reason": {"type": "string", "description": "Why this element"},
        },
        "required": ["ref"],
    },
)

SYSTEM = (
    "You are a browser automation agent. You receive a compressed page snapshot and "
    "choose exactly one tool call per step. Never invent refs — use only refs present "
    "in the snapshot."
)

SNAPSHOT = """URL    https://example.org/search
TITLE  Search results

[e12] textbox  "Search"  = "playwright"
[e13] button   "Find"
[e21] link     "Playwright: fast and reliable automation"  -> /docs/intro
[e22] link     "Unrelated sponsored result"                -> /ads/1

Task: open the documentation page for Playwright."""


async def main() -> int:
    try:
        settings = load_settings()
    except ValueError as e:
        print(f"конфигурация: {e}")
        return 1

    print(f"провайдер   {settings.provider}  ({settings.base_url})")
    print(f"навигатор   {settings.models.navigator}")
    print(f"цепочка     {' -> '.join(settings.models.chain('navigator'))}\n")

    router = LLMRouter(settings)
    try:
        router.budget.start_step()
        response = await router.call(
            "navigator",
            [Message.system(SYSTEM), Message.user(SNAPSHOT)],
            tools=[CLICK],
        )
    except Exception as e:
        print(f"ОШИБКА  {type(e).__name__}: {e}")
        return 1
    finally:
        await router.aclose()

    print(f"модель      {response.model}")
    print(f"задержка    {response.latency_s:.1f} c")
    print(f"стоп        {response.stop_reason}{'  (ОБРЕЗАН)' if response.truncated else ''}")
    print(f"токены      {response.usage}")

    if response.message.reasoning:
        head = response.message.reasoning.strip().replace("\n", " ")[:160]
        print(f"reasoning   {head}...")

    if not response.message.tool_calls:
        print("\nМОДЕЛЬ НЕ ВЫЗВАЛА ИНСТРУМЕНТ — она непригодна для агента")
        print(f"content: {response.message.content[:300]!r}")
        return 1

    call = response.message.tool_calls[0]
    print(f"\ntool call   {call}")

    ok = call.name == "click" and call.arguments.get("ref") == "e21"
    print("проверка    " + ("OK — выбран верный ref" if ok else "НЕВЕРНО — ожидался ref e21"))
    print(f"бюджет      {router.budget.summary()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
