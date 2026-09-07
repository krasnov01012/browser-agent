"""Чтение страницы: содержимое, поиск, зрение.

`read_page` — главный механизм экономии контекста: текст страницы уходит
sub-агенту и обратно возвращается только ответ на вопрос.
"""

from __future__ import annotations

from playwright.async_api import Error as PlaywrightError

from ..browser.extract import page_markdown
from ..browser.marks import screenshot_with_marks
from ..browser.refs import RefError
from ..core.subagent import extract
from .errors import ToolFailed
from .registry import Tool, ToolContext, ToolResult, make_tool, p_bool, p_str

#: сколько совпадений показать в find_in_page
MAX_MATCHES = 15
#: чем читатель отвечает, когда ответа в тексте нет (см. core/subagent.py)
NOT_FOUND = "в тексте этого нет"

#: Считает вхождения дважды: в отрисованном тексте и во всех текстовых узлах.
#:
#: `innerText` показывает только то, что реально нарисовано. Свёрнутый список,
#: закрытое меню, неактивная вкладка виджета в него не попадают, хотя в разметке
#: присутствуют. Обход текстовых узлов их видит, и разница между двумя числами
#: и есть ответ «оно здесь, но скрыто» — а это совсем другой совет, чем «нет».
#:
#: Атрибуты (aria-label, title, placeholder) не считаются: подписи оттуда уже
#: пришли в снапшот и проверены первым ярусом поиска.
COUNT_JS = """
(q) => {
  const visible = (document.body ? document.body.innerText : '').toLowerCase().split(q).length - 1;
  let total = 0;
  if (document.body) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const tag = node.parentElement && node.parentElement.tagName;
        return (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT')
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      total += (n.nodeValue || '').toLowerCase().split(q).length - 1;
    }
  }
  return { visible, total };
}
"""


@make_tool(
    "read_page",
    "Ask a question about the readable content of the page and get a short answer. "
    "The page text itself is never loaded into your context — a separate reader "
    "answers your question. Ask something specific: what the requirements are, what "
    "the sender wants, what the price is. Use ref to limit reading to one area.",
    properties={
        "question": p_str("What you need to know from this page"),
        "ref": p_str("Optional ref to read only that element's area"),
        "format": p_str(
            "concise: a short answer. detailed: allows a longer one.",
            enum=["concise", "detailed"],
        ),
    },
    required=["question"],
)
async def read_page(
    ctx: ToolContext,
    question: str,
    ref: str | None = None,
    format: str = "concise",
) -> ToolResult:
    handle = None
    if ref:
        try:
            handle = await ctx.controller.refs.resolve(ref)
        except RefError as e:
            raise ToolFailed("read_page", e.for_model()) from e

    content = await page_markdown(ctx.controller.page, handle)
    answer = await extract(
        ctx.router,
        content=content,
        question=question,
        detailed=format == "detailed",
    )
    # Читатель видит только текст страницы. Введённые значения, подписи кнопок
    # и состояние галочек в него не попадают — без подсказки агент упирается
    # в «этого нет» и начинает искать там же ещё раз.
    if NOT_FOUND in answer.lower():
        answer += (
            "\n\nПодсказка: читатель видит только текст страницы. Введённые значения "
            "полей, подписи кнопок и состояние переключателей ищите не здесь, "
            "а в состоянии страницы, которое приходит вам каждый шаг."
        )
    return ToolResult(text=answer, state_changed=False)


@make_tool(
    "find_in_page",
    "Search the page text for a phrase and get back the matching refs. Cheaper than "
    "scrolling through a long page looking for something.",
    properties={"query": p_str("Text to look for, case-insensitive")},
    required=["query"],
)
async def find_in_page(ctx: ToolContext, query: str) -> ToolResult:
    needle = query.strip().lower()
    if not needle:
        raise ToolFailed("find_in_page", "пустой запрос")

    hits = []
    if ctx.state is not None:
        for element in ctx.state.elements:
            haystack = f"{element.name} {element.value}".lower()
            if needle in haystack:
                hits.append(element)

    if hits:
        lines = [e.render() for e in hits[:MAX_MATCHES]]
        more = f"\n(и ещё {len(hits) - MAX_MATCHES})" if len(hits) > MAX_MATCHES else ""
        return ToolResult(
            text=f"Найдено в текущем состоянии ({len(hits)}):\n" + "\n".join(lines) + more,
            state_changed=False,
        )

    # В снапшоте нет. Дальше важно различить три разных случая, потому что
    # действовать в них надо по-разному: текст ниже по странице, текст в
    # разметке но не отрисован, и текста нет вовсе.
    try:
        counts = await ctx.controller.page.evaluate(COUNT_JS, needle)
        visible = int(counts.get("visible") or 0)
        total = int(counts.get("total") or 0)
    except (PlaywrightError, AttributeError, TypeError):
        visible = total = 0

    if visible:
        return ToolResult(
            text=(
                f"Среди интерактивных элементов совпадений нет, но текст {query!r} "
                f"встречается на странице {visible} раз(а) — прокрутите к нему. "
                f"Если он нужен вам как содержание, а не как цель клика, "
                f"спросите про него read_page: прокрутка текст не покажет."
            ),
            state_changed=False,
        )

    if total:
        return ToolResult(
            text=(
                f"Текст {query!r} есть в разметке ({total} раз(а)), но не отображается. "
                f"Почти всегда это свёрнутый раздел, закрытое меню или неактивная "
                f"вкладка виджета. Прокрутка его не покажет — его надо раскрыть: "
                f"найдите в состоянии страницы элемент, который открывает эту часть "
                f"интерфейса, нажмите его и повторите поиск."
            ),
            state_changed=False,
        )

    # Ничего. Раньше здесь стояло «на странице не найден» — и это загоняло
    # в тупик: в прогоне с Gmail агент семь шагов подряд искал «Спам», меняя
    # регистр и язык, потому что ответ не подсказывал ни одного другого хода.
    # Пунктов меню там не было и в разметке: интерфейс дорисовывает их только
    # после раскрытия «Ещё» (docs/DECISIONS.md ADR-039).
    return ToolResult(
        text=(
            f"Текста {query!r} на странице нет — ни видимого, ни скрытого в разметке. "
            f"Повторять этот поиск бессмысленно: другой регистр, другой язык или "
            f"второй такой же запрос дадут ровно то же самое. "
            f"Если нужное здесь всё-таки должно быть, значит страница его ещё "
            f"не построила: разделы за раскрывающими элементами часто создаются "
            f"только в момент открытия. Посмотрите в состоянии страницы, есть ли "
            f"чем раскрыть скрытую часть интерфейса, откройте её и повторите поиск. "
            f"Если раскрывать нечего — этого раздела здесь нет, идите к цели "
            f"другим путём."
        ),
        state_changed=False,
    )


@make_tool(
    "screenshot",
    "Look at the page as an image, with element refs drawn on top. Use this only "
    "when the page state is not enough to decide — canvas, image-based UI, or an "
    "unusual widget. It costs far more than the text state, so do not call it "
    "routinely.",
    properties={"marked": p_bool("Draw ref labels over elements (default true)")},
)
async def screenshot(ctx: ToolContext, marked: bool = True) -> ToolResult:
    refs = [e.ref for e in ctx.state.elements if e.in_viewport] if ctx.state else []
    try:
        data, drawn = await screenshot_with_marks(ctx.controller.page, refs, marked=marked)
    except RuntimeError as e:
        raise ToolFailed("screenshot", str(e)) from e

    # Картинку в сообщение подставит цикл — здесь только пометка о ней.
    return ToolResult(
        text=f"Скриншот сделан, размечено элементов: {drawn}",
        state_changed=False,
        image_b64=data,
    )


TOOLS: list[Tool] = [read_page, find_in_page, screenshot]
