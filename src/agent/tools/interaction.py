"""Взаимодействие со страницей: клики, ввод, прокрутка, файлы.

Цель действия задаётся ТОЛЬКО через ref из последнего снапшота. Параметра
«селектор» здесь нет и не будет: у модели не должно быть возможности его
выдумать (docs/CONSTRAINTS.md §2.2).
"""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import ElementHandle
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PWTimeout

from ..browser.controller import DIALOG_ACCEPT, DIALOG_DISMISS
from ..browser.refs import RefError
from .errors import ActionTimeout, Covered, NotVisible, ToolFailed
from .registry import Tool, ToolContext, ToolResult, make_tool, p_bool, p_int, p_str

ACTION_TIMEOUT_MS = 15_000
#: сколько ждать окончания прокрутки перед замером позиции
SCROLL_SETTLE_MS = 150


#: во что можно печатать; всё остальное — не текстовое поле
_KIND_JS = """el => {
    if (el.isContentEditable) return 'editable';
    const tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return 'text';
    if (tag === 'select') return 'select';
    if (tag !== 'input') return tag;
    const typable = ['text', 'search', 'email', 'url', 'tel', 'password', 'number',
                     'date', 'time', 'datetime-local', 'month', 'week'];
    const type = (el.type || 'text').toLowerCase();
    return typable.includes(type) ? 'text' : 'input:' + type;
}"""

#: чем заменить неподходящий инструмент — подсказка идёт прямо в текст ошибки
_INSTEAD = {
    "select": "это выпадающий список — используйте select_option",
    "input:checkbox": "это флажок — его переключают кликом",
    "input:radio": "это переключатель — нужный вариант выбирают кликом",
    "input:file": "это поле для файла — используйте upload_file",
    "input:submit": "это кнопка отправки — по ней кликают",
    "input:button": "это кнопка — по ней кликают",
    "input:range": "это ползунок — его двигают кликом",
}


async def _kind(handle: ElementHandle) -> str:
    """Чем на самом деле является элемент. Пустая строка — определить не вышло."""
    try:
        return str(await handle.evaluate(_KIND_JS))
    except PlaywrightError:
        return ""


#: включён элемент или выключен; null — он вообще не переключатель
_TOGGLE_JS = """el => {
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    const role = (el.getAttribute('role') || '').toLowerCase();

    let on = null, kind = '';
    if (tag === 'input' && (type === 'checkbox' || type === 'radio')) {
        on = el.checked; kind = type;
    } else if (el.hasAttribute('aria-checked')) {
        on = el.getAttribute('aria-checked') === 'true';
        kind = role === 'radio' ? 'radio' : 'checkbox';
    } else if (el.hasAttribute('aria-selected')) {
        on = el.getAttribute('aria-selected') === 'true';
        kind = 'option';
    }
    if (on === null) return null;

    const label = (el.labels && el.labels[0] ? el.labels[0].innerText : '')
        || el.getAttribute('aria-label') || el.value || '';
    return {on, kind, label: label.trim().slice(0, 40)};
}"""

#: как назвать новое состояние — по типу элемента и тому, включён ли он
_TOGGLE_WORDS = {
    ("checkbox", True): "отмечен",
    ("checkbox", False): "снят",
    ("radio", True): "выбран",
    ("radio", False): "не выбран",
    ("option", True): "выбран",
    ("option", False): "не выбран",
}


async def _toggle(handle: ElementHandle) -> dict | None:
    """Состояние переключателя. None — элемент не переключается."""
    try:
        return await handle.evaluate(_TOGGLE_JS)
    except PlaywrightError:
        return None


def _toggle_report(ref: str, before: dict | None, after: dict | None, label: str = "") -> str:
    """Что сказать модели про переключатель после клика.

    Клик по уже отмеченному флажку снимает его, и в состоянии страницы это
    отражено — но замер order_form показал, что агент этого не замечает:
    он щёлкнул «Bacon» пять раз подряд, каждый раз возвращая флажок в прежний
    вид, и до кнопки отправки так и не дошёл. Поэтому результат клика говорит
    об исходе прямым текстом (docs/ADR.md ADR-022).

    Обычный клик до сих пор отвечал одним лишь номером ref, и это было хуже,
    чем кажется. Номера живут один шаг, а после компакции от шага остаётся
    строка «click — Клик по e94»: на вопрос «сколько раз я нажал ту кнопку»
    такая история не отвечает. В прогоне `vacancy_apply` агент отправил четыре
    отклика вместо трёх именно поэтому (docs/ADR.md ADR-039).
    """
    if after is None:
        return f"Клик по {ref}" + (f": «{label}»" if label else "")

    name = f"«{after['label']}» " if after["label"] else ""
    state = _TOGGLE_WORDS.get((after["kind"], after["on"]), "изменён")

    if before is not None and before["on"] == after["on"]:
        # Флажок повторный клик снимет, а радиокнопку — нет: она уже выбрана,
        # и щёлкать по ней можно бесконечно без всякого эффекта.
        advice = (
            "повторный клик снимет отметку"
            if after["kind"] == "checkbox" and after["on"]
            else "повторные клики ничего не дадут"
        )
        return f"Клик по {ref}: {name}и до клика был {state}, ничего не изменилось — {advice}."
    return f"Клик по {ref}: {name}теперь {state}"


async def _resolve(ctx: ToolContext, ref: str, tool: str) -> ElementHandle:
    """ref -> элемент, с приведением ошибок к виду, понятному модели."""
    try:
        return await ctx.controller.refs.resolve(ref)
    except RefError as e:
        raise ToolFailed(tool, e.for_model()) from e


async def _bring_into_view(handle: ElementHandle, ref: str) -> None:
    try:
        await handle.scroll_into_view_if_needed(timeout=5000)
    except PWTimeout as e:
        raise NotVisible(ref) from e
    except PlaywrightError as e:
        raise ToolFailed("scroll_into_view", str(e)[:200]) from e


#: сколько предков перекрывающего узла осмотреть в поисках известного ref
_BLOCKER_DEPTH = 6
#: сколько элементов управления внутри перекрывающего блока перечислить
_BLOCKER_CONTROLS = 6

_DESCRIBE_BLOCKER_JS = (Path(__file__).parents[1] / "browser" / "js" / "blocker.js").read_text(
    encoding="utf-8"
)


async def _describe_blocker(handle: ElementHandle) -> str:
    """Кто именно перекрывает элемент и что внутри него можно нажать.

    Выбор действия остаётся за агентом: подписи берутся со страницы как есть,
    своего списка «кнопок закрытия» у нас нет (docs/ADR.md ADR-041).
    """
    try:
        found = await handle.evaluate(
            _DESCRIBE_BLOCKER_JS,
            {"depth": _BLOCKER_DEPTH, "maxControls": _BLOCKER_CONTROLS},
        )
    except PlaywrightError:
        return ""
    if not found:
        return ""

    described = f"<{found['tag']}>"
    if found["label"]:
        described += f" «{found['label']}»"
    if found["ref"]:
        described += f" (ref {found['ref']})"
    if found["controls"]:
        inside = ", ".join(
            f"{c['ref']} «{c['label']}»" if c["label"] else c["ref"] for c in found["controls"]
        )
        described += f"; внутри него: {inside}"
    return described


@make_tool(
    "click",
    "Click an element by its ref from the latest snapshot. Scrolls to it first. "
    "This is also how you set checkboxes, radio buttons and custom dropdown options "
    "— the result says whether the element ended up checked or selected. "
    "If the element is covered by an overlay, the error names the blocking element "
    "so you can dismiss it. Opening a new tab or a native dialog will show up in "
    "the page state that follows.",
    properties={
        "ref": p_str("Element ref from the latest snapshot, e.g. e21"),
        "button": p_str("Mouse button", enum=["left", "right"]),
    },
    required=["ref"],
    destructive=True,
)
async def click(ctx: ToolContext, ref: str, button: str = "left") -> ToolResult:
    # Нативный диалог блокирует страницу целиком — он обслуживается отдельно.
    if ref in (DIALOG_ACCEPT, DIALOG_DISMISS):
        text = await ctx.controller.resolve_dialog(accept=ref == DIALOG_ACCEPT)
        return ToolResult(text=text)

    handle = await _resolve(ctx, ref, "click")
    await _bring_into_view(handle, ref)
    before = await _toggle(handle)

    try:
        await handle.click(button=button, timeout=ACTION_TIMEOUT_MS)
    except PWTimeout as e:
        blocker = await _describe_blocker(handle)
        if blocker:
            raise Covered(ref, blocker) from e
        raise ActionTimeout(f"клик по {ref}") from e
    except PlaywrightError as e:
        raise ToolFailed("click", str(e)[:200]) from e

    label = ctx.state.label_for(ref) if ctx.state is not None else ""
    return ToolResult(text=_toggle_report(ref, before, await _toggle(handle), label))


@make_tool(
    "type_text",
    "Type into a text field, textarea or rich-text editor. For autocomplete fields "
    "leave submit=false, then look at the updated page and click the option you want "
    "— pressing Enter blindly usually picks the wrong one.",
    properties={
        "ref": p_str("Element ref of the input"),
        "text": p_str("Text to type"),
        "clear": p_bool("Clear the field first (default true)"),
        "submit": p_bool("Press Enter afterwards (default false)"),
    },
    required=["ref", "text"],
    # Сам ввод обратим, но submit=true отправляет форму — решает предохранитель.
    destructive=True,
)
async def type_text(
    ctx: ToolContext,
    ref: str,
    text: str,
    clear: bool = True,
    submit: bool = False,
) -> ToolResult:
    handle = await _resolve(ctx, ref, "type_text")
    await _bring_into_view(handle, ref)

    # Проверяем до действия: иначе наружу вылезет сырая ошибка Playwright
    # («Input of type "checkbox" cannot be filled»), из которой агенту
    # непонятно, что делать (docs/TOOLS.md, таксономия ошибок).
    kind = await _kind(handle)
    if kind not in ("text", "editable", ""):
        hint = _INSTEAD.get(kind, "печатать в него нельзя")
        raise ToolFailed("type_text", f"Элемент {ref} — не текстовое поле: {hint}.")

    try:
        editable = kind == "editable"
        if clear:
            if editable:
                await handle.evaluate("el => { el.textContent = ''; }")
            else:
                await handle.fill("", timeout=ACTION_TIMEOUT_MS)

        if editable:
            # fill не триггерит обработчики rich-text редакторов — только посимвольно.
            await handle.click(timeout=ACTION_TIMEOUT_MS)
            await handle.type(text, delay=8)
        else:
            await handle.fill(text, timeout=ACTION_TIMEOUT_MS)

        if submit:
            await handle.press("Enter", timeout=ACTION_TIMEOUT_MS)
    except PWTimeout as e:
        raise ActionTimeout(f"ввод в {ref}") from e
    except PlaywrightError as e:
        raise ToolFailed("type_text", str(e)[:200]) from e

    tail = ", нажат Enter" if submit else ""
    return ToolResult(text=f"В {ref} введено: {text!r}{tail}")


@make_tool(
    "select_option",
    "Pick an option in a native <select>. This tool works on <select> and nothing "
    "else: radio buttons, checkboxes and custom dropdowns all look like a choice "
    "but are operated by clicking the option you want.",
    properties={
        "ref": p_str("Element ref of the select"),
        "value": p_str("Option value or its visible text"),
    },
    required=["ref", "value"],
)
async def select_option(ctx: ToolContext, ref: str, value: str) -> ToolResult:
    handle = await _resolve(ctx, ref, "select_option")

    # Радиокнопки и кастомные дропдауны — самая частая ошибка адресации: они
    # выглядят как выбор варианта, но select_option к ним неприменим.
    kind = await _kind(handle)
    if kind not in ("select", ""):
        instead = (
            "переключатели выбирают кликом по нужному варианту"
            if kind.startswith("input:")
            else "если это кастомный список — откройте его кликом и кликните вариант"
        )
        raise ToolFailed(
            "select_option",
            f"Элемент {ref} — не выпадающий список <select>: {instead}.",
        )

    try:
        await handle.select_option(value=value, timeout=ACTION_TIMEOUT_MS)
    except PlaywrightError:
        try:
            await handle.select_option(label=value, timeout=ACTION_TIMEOUT_MS)
        except PlaywrightError as e:
            raise ToolFailed(
                "select_option",
                f"в {ref} нет варианта {value!r}. Доступны: {await _options(handle)}",
            ) from e
    return ToolResult(text=f"В {ref} выбрано {value!r}")


async def _options(handle: ElementHandle) -> str:
    """Что вообще можно выбрать — иначе агент угадывает значение вслепую."""
    try:
        found = await handle.evaluate(
            "el => Array.from(el.options).slice(0, 30).map(o => o.label || o.value).filter(Boolean)"
        )
    except PlaywrightError:
        return "не удалось прочитать"
    return ", ".join(f"«{o}»" for o in found) or "список пуст"


@make_tool(
    "press_key",
    "Press a key or a shortcut, optionally focusing an element first. Useful for "
    "Escape to close overlays, Tab to move focus, Enter to submit.",
    properties={
        "key": p_str('Key name, e.g. "Enter", "Escape", "Tab", "Control+a"'),
        "ref": p_str("Optional element ref to focus before pressing"),
    },
    required=["key"],
    # Enter в форме — та же отправка, что и клик по кнопке.
    destructive=True,
)
async def press_key(ctx: ToolContext, key: str, ref: str | None = None) -> ToolResult:
    try:
        if ref:
            handle = await _resolve(ctx, ref, "press_key")
            await handle.press(key, timeout=ACTION_TIMEOUT_MS)
        else:
            await ctx.controller.page.keyboard.press(key)
    except PWTimeout as e:
        raise ActionTimeout(f"нажатие {key}") from e
    except PlaywrightError as e:
        raise ToolFailed("press_key", str(e)[:200]) from e
    where = f" в {ref}" if ref else ""
    return ToolResult(text=f"Нажато {key}{where}")


#: js для чтения позиции прокрутки — страницы и произвольного контейнера
_PAGE_OFFSET = "() => [window.scrollX, window.scrollY]"
_ELEMENT_OFFSET = "el => [el.scrollLeft, el.scrollTop]"


@make_tool(
    "scroll",
    "Scroll the page, or a scrollable container when ref is given. This is how you "
    "reveal items in long or virtualised lists: scroll, look at the new state, repeat. "
    "The result tells you whether anything actually moved: if it did not, you have "
    "reached the edge and scrolling again will not help.",
    properties={
        "direction": p_str("Direction", enum=["up", "down", "left", "right"]),
        "amount": p_int("How many screens to scroll (default 1)"),
        "ref": p_str("Optional ref of a scrollable container"),
    },
    required=["direction"],
)
async def scroll(
    ctx: ToolContext,
    direction: str,
    amount: int = 1,
    ref: str | None = None,
) -> ToolResult:
    steps = max(1, min(int(amount or 1), 10))
    page = ctx.controller.page
    try:
        viewport = await page.evaluate("() => window.innerHeight")
        distance = int(viewport * steps)
        dx, dy = {
            "down": (0, distance),
            "up": (0, -distance),
            "right": (distance, 0),
            "left": (-distance, 0),
        }.get(direction, (0, distance))

        # Позицию замеряем до и после: прокрутка «в упор» ничем не отличается
        # от удавшейся, и без замера агент уходит крутить одно и то же по кругу.
        if ref:
            handle = await _resolve(ctx, ref, "scroll")
            before = await handle.evaluate(_ELEMENT_OFFSET)
            await handle.evaluate("(el, d) => el.scrollBy(d.x, d.y)", {"x": dx, "y": dy})
            await page.wait_for_timeout(SCROLL_SETTLE_MS)
            after = await handle.evaluate(_ELEMENT_OFFSET)
        else:
            before = await page.evaluate(_PAGE_OFFSET)
            await page.mouse.wheel(dx, dy)
            # wheel не дожидается окончания прокрутки, а плавная идёт с анимацией.
            await page.wait_for_timeout(SCROLL_SETTLE_MS)
            after = await page.evaluate(_PAGE_OFFSET)
    except PlaywrightError as e:
        raise ToolFailed("scroll", str(e)[:200]) from e

    where = f" внутри {ref}" if ref else ""
    moved = abs(after[0] - before[0]) + abs(after[1] - before[1])
    if moved < 1:
        edge = {"down": "низа", "up": "верха", "right": "правого края", "left": "левого края"}
        return ToolResult(
            text=(
                f"Прокрутка не сдвинула страницу{where}: достигнут предел "
                f"{edge.get(direction, 'края')}. Повторять её бессмысленно — "
                f"нужного элемента здесь нет, ищите другой путь."
            ),
            state_changed=False,
        )
    return ToolResult(text=f"Прокрутка {direction} на {steps} экран(а){where}, сдвиг {moved} px")


@make_tool(
    "upload_file",
    "Attach a local file to a file input, bypassing the OS dialog.",
    properties={
        "ref": p_str("Element ref of the file input"),
        "path": p_str("Absolute path to the local file"),
    },
    required=["ref", "path"],
    # Приложенный файл может уехать вместе с формой.
    destructive=True,
)
async def upload_file(ctx: ToolContext, ref: str, path: str) -> ToolResult:
    handle = await _resolve(ctx, ref, "upload_file")
    try:
        await handle.set_input_files(path, timeout=ACTION_TIMEOUT_MS)
    except PlaywrightError as e:
        raise ToolFailed("upload_file", str(e)[:200]) from e
    return ToolResult(text=f"В {ref} приложен файл {path}")


TOOLS: list[Tool] = [click, type_text, select_option, press_key, scroll, upload_file]
