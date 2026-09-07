"""Навигация: адреса, история, вкладки."""

from __future__ import annotations

from playwright.async_api import Error as PlaywrightError

from .errors import NavigationFailed, ToolFailed
from .registry import Tool, ToolContext, ToolResult, make_tool, p_int, p_str


@make_tool(
    "goto",
    "Open an absolute URL in the current tab. Use only when you already know the "
    "address — for finding pages, prefer navigating from what is on screen.",
    properties={"url": p_str("Absolute URL including scheme, e.g. https://example.org/page")},
    required=["url"],
)
async def goto(ctx: ToolContext, url: str) -> ToolResult:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")
    try:
        await ctx.controller.goto(url)
    except PlaywrightError as e:
        raise NavigationFailed(f"{url} — {_short(e)}") from e
    return ToolResult(text=f"Открыт адрес {url}")


@make_tool(
    "go_back",
    "Go back one entry in the browser history of the current tab.",
)
async def go_back(ctx: ToolContext) -> ToolResult:
    try:
        moved = await ctx.controller.go_back()
    except PlaywrightError as e:
        raise NavigationFailed(_short(e)) from e
    if not moved:
        return ToolResult(text="Назад идти некуда — это первая страница в истории вкладки")
    return ToolResult(text="Вернулись на предыдущую страницу")


@make_tool(
    "list_tabs",
    "List open browser tabs. The snapshot header already shows tabs when more than "
    "one is open, so call this only when you need full URLs.",
    properties={
        "format": p_str(
            "concise: index and title. detailed: adds the full URL.",
            enum=["concise", "detailed"],
        )
    },
)
async def list_tabs(ctx: ToolContext, format: str = "concise") -> ToolResult:
    tabs = ctx.controller.tabs()
    detailed = format == "detailed"
    lines = []
    for tab in tabs:
        mark = " (активна)" if tab.active else ""
        lines.append(f"[{tab.index}] {tab.title}{mark}" + (f" — {tab.url}" if detailed else ""))
    return ToolResult(text="Вкладки:\n" + "\n".join(lines), state_changed=False)


@make_tool(
    "switch_tab",
    "Make another tab active. Everything else acts on the active tab.",
    properties={"index": p_int("Tab index from list_tabs")},
    required=["index"],
)
async def switch_tab(ctx: ToolContext, index: int) -> ToolResult:
    try:
        await ctx.controller.switch_tab(int(index))
    except (IndexError, ValueError) as e:
        raise ToolFailed("switch_tab", str(e)) from e
    return ToolResult(text=f"Активна вкладка {index}")


@make_tool(
    "close_tab",
    "Close a tab. The last remaining tab cannot be closed.",
    properties={"index": p_int("Tab index from list_tabs")},
    required=["index"],
    destructive=True,
)
async def close_tab(ctx: ToolContext, index: int) -> ToolResult:
    try:
        await ctx.controller.close_tab(int(index))
    except (IndexError, ValueError) as e:
        raise ToolFailed("close_tab", str(e)) from e
    return ToolResult(text=f"Вкладка {index} закрыта")


def _short(error: Exception) -> str:
    """Playwright пишет многострочно; модели хватит первой строки."""
    return str(error).strip().splitlines()[0][:200]


TOOLS: list[Tool] = [goto, go_back, list_tabs, switch_tab, close_tab]
