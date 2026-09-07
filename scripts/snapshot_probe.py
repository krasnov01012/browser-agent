"""Замер слоя снапшотов на живых страницах.

Контрольная метрика фазы 1: состояние страницы должно укладываться
в SNAPSHOT_TOKEN_BUDGET (по умолчанию 4000 токенов) при том, что все реально
кликабельные элементы видны.

Запуск:
    .venv/Scripts/python scripts/snapshot_probe.py                 # текущая вкладка
    .venv/Scripts/python scripts/snapshot_probe.py URL [URL ...]   # обойти адреса
    .venv/Scripts/python scripts/snapshot_probe.py --full URL      # печатать снапшот целиком
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.browser import BrowserController, BrowserUnavailable
from agent.config import load_settings

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")

PREVIEW_LINES = 30


def report(state, budget: int, *, full: bool) -> bool:
    text = state.render()
    tokens = state.tokens
    ok = tokens <= budget

    print(f"\n{'=' * 78}")
    print(f"{state.url}")
    print(f"{'=' * 78}")

    lines = text.splitlines()
    shown = lines if full else lines[:PREVIEW_LINES]
    print("\n".join(shown))
    if not full and len(lines) > PREVIEW_LINES:
        print(f"... ещё {len(lines) - PREVIEW_LINES} строк (--full чтобы увидеть)")

    visible = sum(1 for e in state.elements if e.in_viewport)
    print(f"\n{'—' * 78}")
    print(f"элементов        {len(state.elements)} (в зоне видимости {visible})")
    print(f"за краем окна    ~{state.offscreen}")
    print(f"строк            {len(lines)}")
    print(f"символов         {len(text)}")
    print(f"ТОКЕНОВ          {tokens}   бюджет {budget}   {'OK' if ok else 'ПРЕВЫШЕН'}")
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("urls", nargs="*", help="адреса для обхода")
    parser.add_argument("--full", action="store_true", help="печатать снапшот целиком")
    args = parser.parse_args()

    settings = load_settings()
    budget = settings.snapshot_token_budget

    controller = BrowserController(settings)
    try:
        await controller.start()
    except BrowserUnavailable as e:
        print(f"\n{e}\n")
        return 1

    failures = 0
    try:
        if not args.urls:
            state = await controller.snapshot()
            if not report(state, budget, full=args.full):
                failures += 1
        else:
            previous = None
            for url in args.urls:
                await controller.goto(url)
                state = await controller.snapshot()
                if not report(state, budget, full=args.full):
                    failures += 1

                # Проверяем дельту: повторный снимок той же страницы
                # должен давать почти пустой diff.
                again = await controller.snapshot()
                delta = again.diff(state)
                print(f"дельта повтора   {len(delta)} симв. / ~{len(delta) // 3} токенов")
                previous = again
            del previous
    finally:
        await controller.close()

    print()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
