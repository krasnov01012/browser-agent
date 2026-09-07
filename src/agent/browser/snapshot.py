"""Страница -> компактное состояние для модели.

Сырой HTML живой SPA — сотни тысяч токенов. Здесь он превращается в несколько
тысяч: обходчик собирает только интерактивное и реально видимое, одинаковые
соседние карточки схлопываются, а между шагами отдаётся не весь снапшот,
а разница с предыдущим.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Page

from .refs import RefRegistry
from .stability import Stability

log = logging.getLogger(__name__)

_JS_DIR = Path(__file__).parent / "js"
COLLECT_JS = (_JS_DIR / "collect.js").read_text(encoding="utf-8")

# Сколько одинаковых соседей показать до схлопывания.
COLLAPSE_KEEP = 3
COLLAPSE_MIN_RUN = 5
# Смешанный русско-английский текст: примерно столько символов на токен.
CHARS_PER_TOKEN = 3.4


def estimate_tokens(text: str) -> int:
    return round(len(text) / CHARS_PER_TOKEN)


@dataclass(slots=True)
class Element:
    ref: str
    role: str
    name: str = ""
    value: str = ""
    href: str = ""
    state: dict[str, bool] = field(default_factory=dict)
    sig: str = ""
    in_viewport: bool = True
    top: int = 0
    landmark: bool = False

    def identity(self) -> tuple:
        """То, изменение чего модель должна заметить."""
        return (self.role, self.name, self.value, tuple(sorted(self.state.items())))

    def render(self) -> str:
        parts = [f"[{self.ref}]", f"{self.role:<9}"]
        parts.append(f'"{self.name}"' if self.name else '""')
        if self.value:
            parts.append(f'= "{self.value}"')
        if self.href:
            parts.append(f"→ {self.href}")
        if self.state:
            flags = " ".join(f"{k}={str(v).lower()}" for k, v in sorted(self.state.items()))
            parts.append(flags)
        return " ".join(parts)


@dataclass(slots=True)
class TabInfo:
    index: int
    title: str
    url: str
    active: bool


@dataclass(slots=True)
class PageState:
    url: str
    title: str
    elements: list[Element]
    tabs: list[TabInfo] = field(default_factory=list)
    scroll_y: int = 0
    scroll_height: int = 0
    viewport: int = 0
    offscreen: int = 0
    truncated: bool = False
    stability: Stability | None = None

    # ── опознание ────────────────────────────────────────────────────

    def fingerprint(self) -> str:
        """Отпечаток состояния: совпал с предыдущим — страница не изменилась.

        Прокрутка в отпечаток не входит намеренно. Прокрутка, сдвинувшая
        страницу на десяток пикселей и не открывшая ни одного нового элемента,
        для агента не изменила ничего, а по scroll_y выглядела бы движением
        вперёд (docs/DECISIONS.md ADR-039).
        """
        body = "|".join(f"{e.ref}{e.identity()}" for e in self.elements)
        digest = hashlib.blake2s(body.encode("utf-8"), digest_size=8).hexdigest()
        return f"{self.url}#{len(self.elements)}#{digest}"

    def label_for(self, ref: str) -> str:
        """Подпись элемента по ref. Пусто — такого ref в снапшоте нет."""
        for element in self.elements:
            if element.ref == ref:
                return element.name or element.value or ""
        return ""

    # ── отрисовка ────────────────────────────────────────────────────

    def header(self) -> list[str]:
        lines = [f"URL    {self.url}", f"TITLE  {self.title}"]

        if len(self.tabs) > 1:
            shown = [f"[{t.index}{'*' if t.active else ''}] {t.title[:40]}" for t in self.tabs]
            lines.append("TABS   " + "  │  ".join(shown))

        if self.scroll_height > self.viewport > 0:
            pct = round(100 * self.scroll_y / max(1, self.scroll_height - self.viewport))
            lines.append(f"SCROLL {self.scroll_y} / {self.scroll_height}  ({min(pct, 100)}%)")

        if self.stability is not None:
            lines.append(f"STATE  {self.stability.label}")
        return lines

    def body(self) -> list[str]:
        lines: list[str] = []
        for chunk, repeats in _collapse(self.elements):
            lines.append(chunk.render())
            if repeats:
                lines.append(f"       × ещё {repeats} того же вида")
        return lines

    def footer(self) -> list[str]:
        lines: list[str] = []
        if self.offscreen:
            lines.append(f"↓ ещё ~{self.offscreen} элементов вне видимой области, прокрутите")
        if self.truncated:
            lines.append("⚠ страница очень большая, показана только часть — уточните область")
        if not self.elements:
            lines.append("(интерактивных элементов не найдено — возможно, страница ещё грузится)")
        return lines

    def render(self) -> str:
        return "\n".join([*self.header(), "", *self.body(), *self.footer()]).strip()

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.render())

    # ── разница с предыдущим состоянием ──────────────────────────────

    def diff(self, previous: PageState | None) -> str:
        """Состояние страницы целиком, с пометками того, что изменилось.

        Раньше здесь возвращались только изменения — и это была ошибка,
        стоившая половины прогона `order_form`. Текст состояния попадает
        только в текущее сообщение и нигде не сохраняется: история хранит
        результаты инструментов, а не снапшоты (`core/context.py`). Базы,
        относительно которой считается разница, у модели попросту нет.
        На неизменной странице агент с пятого шага получал «Δ страница
        не изменилась» и ни одного ref — и вслепую скроллил в поисках поля,
        которое всё это время было на экране (docs/DECISIONS.md ADR-024).

        Поэтому список элементов приходит полностью и всегда, а разница
        показывается пометками `Δ +` и `Δ ~` на строках и перечнем исчезнувших.
        """
        if previous is None or previous.url != self.url:
            return self.render()

        before = {e.ref: e for e in previous.elements}
        marks: dict[str, str] = {}
        for element in self.elements:
            old = before.get(element.ref)
            if old is None:
                marks[element.ref] = "Δ +"
            elif old.identity() != element.identity():
                marks[element.ref] = "Δ ~"

        removed = [e for ref, e in before.items() if ref not in {x.ref for x in self.elements}]

        lines = [*self.header(), ""]
        tabs_note = self._tab_change(previous)
        if tabs_note:
            lines.append(tabs_note)
        if not (marks or removed or tabs_note):
            lines.append("Δ по сравнению с прошлым шагом ничего не изменилось")
        lines.append("")

        # Схлопывать можно только неизменившиеся: иначе пометка на элементе
        # внутри группы пропадёт вместе с ним самим.
        for marked, run in _runs(self.elements, marks):
            if marked:
                lines.append(f"{marks[run[0].ref]} {run[0].render()}")
                continue
            for chunk, repeats in _collapse(run):
                lines.append(f"    {chunk.render()}")
                if repeats:
                    lines.append(f"        × ещё {repeats} того же вида")
        for element in removed:
            lines.append(f'Δ - [{element.ref}] {element.role} "{element.name}" — исчез')

        lines.extend(self.footer())
        return "\n".join(lines)

    def _tab_change(self, previous: PageState) -> str:
        """Что сказать про вкладки, если их состав изменился.

        Ссылка с target=_blank открывает вкладку в фоне: страница под агентом
        не меняется, в списке элементов не меняется ничего, а результат клика —
        «Клик по e62». Прогон vacancy_apply показал, к чему это ведёт: агент
        счёл клик несработавшим и повторил его девять раз, наплодив шесть
        одинаковых вкладок. Строка TABS в шапке при этом росла, но пометок Δ
        в шапке нет, и агент её не замечал.

        Состав вкладок — такой же результат действия, как содержимое страницы,
        и виден должен быть так же (docs/DECISIONS.md ADR-022).
        """
        was = Counter(t.url for t in previous.tabs)
        now = Counter(t.url for t in self.tabs)
        opened, closed = now - was, sum((was - now).values())

        notes: list[str] = []
        for tab in self.tabs:
            if not opened.get(tab.url):
                continue
            opened[tab.url] -= 1
            title = tab.title[:40] or tab.url[:40]
            # Дубль отдельной строкой: именно он означает, что агент повторяет
            # уже сработавшее действие, а не что оно не сработало.
            if was.get(tab.url):
                notes.append(
                    f"Δ вкладка «{title}» открылась ещё раз — она уже была открыта. "
                    f"Клик сработал и в прошлый раз; повторять его не нужно."
                )
            else:
                notes.append(
                    f"Δ открылась новая вкладка [{tab.index}] «{title}». "
                    f"Вы остались на прежней — перейти к ней можно через switch_tab."
                )
        if closed:
            notes.append(f"Δ вкладок закрылось: {closed}")
        return "\n".join(notes)


def _runs(elements: list[Element], marks: dict[str, str]) -> list[tuple[bool, list[Element]]]:
    """Режет список на отрезки: помеченные — по одному, прочие — подряд."""
    out: list[tuple[bool, list[Element]]] = []
    for element in elements:
        marked = element.ref in marks
        if out and not marked and not out[-1][0]:
            out[-1][1].append(element)
        else:
            out.append((marked, [element]))
    return out


def _collapse(elements: list[Element]) -> list[tuple[Element, int]]:
    """Схлопывает подряд идущие элементы одинаковой структуры И с одинаковым именем.

    Совпадение имени в условии принципиально. Имя — это полезная нагрузка:
    50 одинаковых кнопок действия схлопывать нужно, 50 разных заголовков —
    нельзя, иначе агенту не из чего выбирать. Схлопывание только по структуре
    склеивало заголовки списка с навигационными ссылками.
    """
    out: list[tuple[Element, int]] = []
    index = 0
    while index < len(elements):
        head = elements[index]
        sig, name = head.sig, head.name
        run = index
        while run < len(elements) and elements[run].sig == sig and elements[run].name == name:
            run += 1
        length = run - index

        if sig and length >= COLLAPSE_MIN_RUN:
            for element in elements[index : index + COLLAPSE_KEEP]:
                out.append((element, 0))
            out[-1] = (out[-1][0], length - COLLAPSE_KEEP)
        else:
            out.extend((element, 0) for element in elements[index:run])
        index = run
    return out


# ── сбор ──────────────────────────────────────────────────────────────


async def _collect_frame(frame: Frame) -> dict | None:
    try:
        raw = await frame.evaluate(COLLECT_JS)
    except PlaywrightError as e:
        log.debug("фрейм пропущен: %s", e)
        return None
    return raw if isinstance(raw, dict) else None


def _to_element(item: dict, ref: str) -> Element:
    return Element(
        ref=ref,
        role=str(item.get("role") or ""),
        name=str(item.get("name") or ""),
        value=str(item.get("value") or ""),
        href=str(item.get("href") or ""),
        state={k: bool(v) for k, v in (item.get("state") or {}).items()},
        sig=str(item.get("sig") or ""),
        in_viewport=bool(item.get("inViewport")),
        top=int(item.get("top") or 0),
        landmark=bool(item.get("landmark")),
    )


async def capture(
    page: Page,
    registry: RefRegistry,
    *,
    tabs: list[TabInfo] | None = None,
    stability: Stability | None = None,
) -> PageState:
    """Снимает состояние страницы вместе со всеми её фреймами."""
    frames = page.frames
    registry.clear(frames)

    elements: list[Element] = []
    offscreen = 0
    truncated = False
    url, title = page.url, ""
    scroll_y = scroll_height = viewport = 0

    for index, frame in enumerate(frames):
        raw = await _collect_frame(frame)
        if raw is None:
            continue

        if index == 0:
            url = str(raw.get("url") or page.url)
            title = str(raw.get("title") or "")
            scroll = raw.get("scroll") or {}
            scroll_y = int(scroll.get("y") or 0)
            scroll_height = int(scroll.get("height") or 0)
            viewport = int(scroll.get("viewport") or 0)

        offscreen += int(raw.get("offscreen") or 0)
        truncated = truncated or bool(raw.get("truncated"))

        for item in raw.get("elements") or []:
            local_ref = str(item.get("ref") or "")
            if not local_ref:
                continue
            ref = registry.qualify(index, local_ref)
            registry.add(ref, frame, local_ref)
            elements.append(_to_element(item, ref))

    # Порядок чтения: сверху вниз, видимое раньше того, что за краем экрана.
    elements.sort(key=lambda e: (not e.in_viewport, e.top))

    return PageState(
        url=url,
        title=title,
        elements=elements,
        tabs=tabs or [],
        scroll_y=scroll_y,
        scroll_height=scroll_height,
        viewport=viewport,
        offscreen=offscreen,
        truncated=truncated,
        stability=stability,
    )
