"""Показать снимок страницы так, как его видит агент.

Быстрый способ ответить на вопрос «что модель вообще видела на этом шаге»,
не гоняя весь прогон. Адрес и (необязательно) действия задаются аргументами:

    .venv/Scripts/python scripts/probe_page.py https://example.com
    .venv/Scripts/python scripts/probe_page.py https://example.com --read
    .venv/Scripts/python scripts/probe_page.py --current

Браузер тот же, что у агента, поэтому одновременно с замером запускать нельзя.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.browser import BrowserController  # noqa: E402
from agent.browser.extract import page_markdown  # noqa: E402
from agent.config import load_settings  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    controller = BrowserController(load_settings())
    await controller.start()
    try:
        if args.url:
            await controller.goto(args.url)
            await asyncio.sleep(args.wait)

        state = await controller.snapshot()
        print(state.render())
        print(
            f"\n--- элементов {len(state.elements)}, за краем ~{state.offscreen}, "
            f"токенов {state.tokens}"
        )

        if args.read:
            text = await page_markdown(controller.page)
            print(f"\n--- read_page: {len(text)} символов\n")
            print(text[: args.chars])
    finally:
        await controller.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="probe_page")
    parser.add_argument("url", nargs="?", help="куда пойти; без него — текущая вкладка")
    parser.add_argument("--read", action="store_true", help="показать и результат read_page")
    parser.add_argument("--chars", type=int, default=3000, help="сколько символов текста печатать")
    parser.add_argument("--wait", type=float, default=2.0, help="пауза после перехода, с")
    sys.exit(asyncio.run(main(parser.parse_args())))
