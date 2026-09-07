"""Извлечение читаемого содержимого страницы в Markdown.

Нужно не агенту напрямую, а sub-агенту-экстрактору: полный текст статьи или
письма никогда не попадает в основной контекст.
"""

from __future__ import annotations

import asyncio
import logging
import re

import trafilatura
from playwright.async_api import ElementHandle, Page
from playwright.async_api import Error as PlaywrightError

log = logging.getLogger(__name__)

#: потолок на текст, уходящий sub-агенту
MAX_MARKDOWN_CHARS = 24_000

#: какую долю видимого текста должна сохранить trafilatura, чтобы ей поверить
MIN_RECALL = 0.25


async def page_markdown(page: Page, handle: ElementHandle | None = None) -> str:
    """Читаемое содержимое страницы или отдельной области в Markdown."""
    try:
        html = (
            await handle.evaluate("el => el.outerHTML")
            if handle is not None
            else await page.content()
        )
    except PlaywrightError as e:
        log.debug("не удалось получить HTML: %s", e)
        return ""

    # trafilatura синхронна и на больших страницах заметна — уводим с event loop.
    text = await asyncio.to_thread(_to_markdown, html)
    visible = await _visible_text(page, handle)
    if not _plausible(text, visible):
        text = visible

    text = _tidy(text)
    if len(text) > MAX_MARKDOWN_CHARS:
        text = text[:MAX_MARKDOWN_CHARS] + "\n\n[...текст обрезан...]"
    return text


def _to_markdown(html: str) -> str:
    try:
        return (
            trafilatura.extract(
                html,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                favor_recall=True,
            )
            or ""
        )
    except Exception as e:
        log.debug("trafilatura не справилась: %s", e)
        return ""


def _plausible(extracted: str, visible: str) -> bool:
    """Не выбросила ли trafilatura большую часть страницы.

    Она ищет статью: заголовок, автор, абзацы связного текста. Список вакансий,
    входящие письма, корзина, лента — не статьи, и на них она отдаёт первую
    попавшуюся карточку, а остальное считает обвязкой. Со страницы результатов
    поиска приходило 1447 символов из 27898 — одна карточка из полусотни, и
    читатель честно отвечал «в тексте этого нет» на любой вопрос о списке.

    Отличить один случай от другого можно по доле сохранённого текста: у статьи
    она около единицы и выше (разметка ссылок добавляет символов), у списка —
    сотые доли. Порог посередине, промахнуться трудно (docs/ADR.md ADR-028).
    """
    if not extracted:
        return False
    if not visible:
        return True
    return len(extracted) / len(visible) >= MIN_RECALL


async def _visible_text(page: Page, handle: ElementHandle | None) -> str:
    """Весь видимый текст: письма и приложения часто не выглядят как «статья»."""
    try:
        if handle is not None:
            return await handle.evaluate("el => el.innerText") or ""
        return await page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except PlaywrightError:
        return ""


def _tidy(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
