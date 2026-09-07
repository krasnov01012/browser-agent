"""Ожидание, пока страница перестанет меняться.

`networkidle` на живых сайтах не наступает: аналитика и поллинг держат сеть
занятой постоянно. Считаем вместо этого покой DOM плюс незавершённые запросы
(логика в js/stability.js), с жёстким потолком по времени.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

log = logging.getLogger(__name__)

_JS_DIR = Path(__file__).parent / "js"
STABILITY_JS = (_JS_DIR / "stability.js").read_text(encoding="utf-8")

POLL_INTERVAL_S = 0.1


@dataclass(slots=True)
class Stability:
    quiet_ms: int
    inflight: int
    ready_state: str
    settled: bool

    @property
    def label(self) -> str:
        """Короткая пометка для строки STATE в снапшоте."""
        if self.settled:
            return "loaded"
        if self.inflight:
            return f"loading ({self.inflight} запросов)"
        return "unstable"


async def probe(page: Page) -> Stability | None:
    """Одно измерение. None, если страница сейчас недоступна для скрипта."""
    try:
        raw = await page.evaluate(STABILITY_JS)
    except PlaywrightError as e:
        log.debug("детектор покоя недоступен: %s", e)
        return None
    if not isinstance(raw, dict):
        return None
    return Stability(
        quiet_ms=int(raw.get("quietMs") or 0),
        inflight=int(raw.get("inflight") or 0),
        ready_state=str(raw.get("readyState") or ""),
        settled=False,
    )


async def wait_until_settled(
    page: Page,
    *,
    quiet_ms: int,
    timeout_ms: int,
) -> Stability:
    """Ждёт покоя. По истечении потолка возвращает состояние как есть.

    Не бросает по таймауту намеренно: вечный спиннер не должен убивать задачу.
    Агент увидит `STATE unstable` и решит сам — ждать ещё или действовать.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    last = Stability(quiet_ms=0, inflight=0, ready_state="", settled=False)

    while True:
        measured = await probe(page)
        if measured is not None:
            last = measured
            quiet_enough = measured.quiet_ms >= quiet_ms
            idle = measured.inflight == 0
            loaded = measured.ready_state == "complete"
            if quiet_enough and idle and loaded:
                last.settled = True
                return last

        if loop.time() >= deadline:
            log.debug(
                "страница не успокоилась за %d мс (тишина %d мс, запросов %d)",
                timeout_ms,
                last.quiet_ms,
                last.inflight,
            )
            return last

        await asyncio.sleep(POLL_INTERVAL_S)
