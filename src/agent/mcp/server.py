"""MCP-сервер по stdio: инструменты агента наружу, для чужой модели.

Тонкий слой. Всё, что требовало решений, — в `session.py`; здесь только перевод
между двумя словарями: `Tool` реестра -> `types.Tool` протокола, `CallOutcome`
-> `CallToolResult`. Схемы не пишутся руками: их отдаёт `Tool.spec()`, тот же
самый метод, которым инструменты описываются модели в агентном цикле. Второго
описания у инструмента быть не должно — оно немедленно разъедется с первым
(docs/ADR.md ADR-040).

Запуск: `python -m agent.main --mcp` или консольная команда `browser-agent-mcp`.
Транспорт — stdio, то есть stdout занят протоколом: печатать в него нельзя,
человеческие сообщения идут в stderr.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .. import __version__
from ..config import Settings
from ..tools.registry import Tool, ToolRegistry
from .session import BrowserSession, CallOutcome

log = logging.getLogger(__name__)

#: имя сервера в рукопожатии; по нему клиент подписывает инструменты
SERVER_NAME = "browser-agent"

#: Что клиент читает до первого вызова.
#:
#: Здесь описывается устройство работы, а не какой-либо сайт: откуда берутся
#: `ref` и почему действия делаются по одному (docs/CONSTRAINTS.md §2.3).
INSTRUCTIONS = (
    "Drives a real, visible Chrome window over CDP. Targets are addressed by ref "
    "(e.g. e21) taken from the latest page snapshot: refs are handed out by the "
    "snapshot itself, there are no selectors and you cannot invent one. Call "
    "page_state to get the first snapshot; after that every tool that changes the "
    "page returns the new state with its result. Do one action at a time and look "
    "at what came back — the page decides what is possible next, not a plan made "
    "in advance."
)


def describe(tool: Tool) -> types.Tool:
    """Инструмент реестра -> инструмент MCP.

    Аннотации — единственное, что добавляется к описанию. `destructive_hint`
    берётся из того же флага, по которому security layer решает, спрашивать ли
    подтверждение (`security/guard.py`), так что второго списка «опасных»
    инструментов не заводится.

    `read_only_hint` намеренно не выставляется. В реестре такого признака нет,
    а вывести его здесь — значит завести второй источник правды, который начнёт
    расходиться с первым при первом же новом инструменте. Клиенты трактуют
    отсутствие подсказки как «неизвестно», и это честно.
    """
    spec = tool.spec()
    return types.Tool(
        name=spec.name,
        description=spec.description,
        input_schema=spec.parameters,
        annotations=types.ToolAnnotations(
            destructive_hint=tool.destructive,
            # Браузер ходит в живой веб: набор целей не фиксирован и меняется
            # между вызовами — ровно то, о чём говорит openWorldHint.
            open_world_hint=True,
        ),
    )


def describe_all(registry: ToolRegistry) -> list[types.Tool]:
    return [describe(registry.get(name)) for name in registry.names()]


def to_content(outcome: CallOutcome) -> list[types.TextContent | types.ImageContent]:
    """Результат вызова -> блоки содержимого MCP.

    Скриншот уезжает картинкой, а не строкой base64 в тексте: MCP умеет
    передавать изображения, и клиент покажет его модели так же, как это делает
    цикл агента (`core/context.py`).
    """
    content: list[types.TextContent | types.ImageContent] = [types.TextContent(text=outcome.text)]
    if outcome.image_b64:
        content.append(types.ImageContent(data=outcome.image_b64, mime_type="image/png"))
    return content


def build_server(session: BrowserSession) -> Server[Any]:
    """Собирает сервер поверх готовой сессии."""
    # Список инструментов неизменен на всё время работы сервера: реестр
    # собирается один раз, поэтому и описания считаются один раз.
    tools = describe_all(session.registry)

    async def on_list_tools(
        ctx: ServerRequestContext[Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(
        ctx: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        outcome = await session.call(params.name, params.arguments or {})
        # is_error=True, а не исключение наружу: по протоколу ошибка инструмента
        # — это нормальный ответ, который модель увидит и сможет обойти.
        # Исключение стало бы ошибкой транспорта, и текст до модели не дошёл бы.
        return types.CallToolResult(content=to_content(outcome), is_error=outcome.is_error)

    return Server(
        SERVER_NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def serve_stdio(settings: Settings) -> None:
    """Поднять сервер на stdin/stdout и работать, пока клиент не закроет поток."""
    session = BrowserSession(settings)
    server = build_server(session)
    log.info("MCP-сервер готов, инструментов: %d", len(session.registry))
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        # Клиент ушёл — отпускаем браузер. Само окно Chrome при этом остаётся
        # открытым: оно пользовательское, мы только отсоединяемся (ADR-002).
        await session.aclose()
