"""Протокольный слой MCP: перевод схем, аннотаций и результатов.

Браузера здесь нет вовсе — сессия подменена заглушкой. Сторожится то, что
ломается молча: описание инструмента, разъехавшееся с его настоящей схемой,
потерянный признак необратимости и ошибка, ушедшая клиенту как исправный ответ.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

pytest.importorskip("mcp", reason="MCP — optional-extra: pip install -e .[mcp]")

import anyio
from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from agent.mcp.server import (
    INSTRUCTIONS,
    build_server,
    describe,
    describe_all,
    to_content,
)
from agent.mcp.session import CallOutcome, mcp_registry
from agent.tools import build_registry


class StubSession:
    """Сессия без браузера: помнит вызов и отдаёт заготовленный ответ."""

    def __init__(self, outcome: CallOutcome | None = None) -> None:
        self.registry = mcp_registry()
        self.outcome = outcome or CallOutcome(text="ок")
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> CallOutcome:
        self.calls.append((name, arguments))
        return self.outcome


@asynccontextmanager
async def client_for(session: StubSession):
    """Клиент и сервер, соединённые в памяти, без stdio и подпроцессов."""
    server = build_server(session)  # type: ignore[arg-type]
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: server.run(
                    server_read, server_write, server.create_initialization_options()
                )
            )
            # Ограничение по времени: зависший тест хуже упавшего.
            with anyio.fail_after(15):
                async with ClientSession(client_read, client_write) as client:
                    await client.initialize()
                    yield client
            tg.cancel_scope.cancel()


# ── описание инструментов ─────────────────────────────────────────────


def test_schema_is_taken_from_the_tool_itself():
    """Схема должна быть той же самой, а не похожей.

    Переписанная руками схема расходится с инструментом при первой же правке
    сигнатуры, и клиент начинает слать аргументы, которых инструмент не ждёт.
    """
    tool = build_registry().get("click")
    assert describe(tool).input_schema == tool.spec().parameters


def test_every_exposed_tool_is_described():
    registry = mcp_registry()
    assert [t.name for t in describe_all(registry)] == registry.names()


@pytest.mark.parametrize(
    ("name", "destructive"),
    [("click", True), ("type_text", True), ("page_state", False), ("list_tabs", False)],
)
def test_destructive_flag_becomes_an_annotation(name: str, destructive: bool):
    """По этой подсказке клиент решает, спрашивать ли пользователя.

    Флаг тот же, по которому подтверждение спрашивает сам агент, — второго
    списка «опасных» инструментов не заводится.
    """
    described = describe(mcp_registry().get(name))
    assert described.annotations is not None
    assert described.annotations.destructive_hint is destructive
    assert described.annotations.open_world_hint is True


def test_schema_travels_under_the_name_the_protocol_expects():
    """Поля питоновские, на проводе — camelCase; ошибка здесь ломает всех клиентов."""
    payload = describe(mcp_registry().get("click")).model_dump(by_alias=True, exclude_none=True)
    assert "inputSchema" in payload
    assert payload["annotations"]["destructiveHint"] is True


def test_instructions_explain_where_refs_come_from():
    """Клиент читает их до первого вызова: без этого ref будут выдуманы."""
    assert "ref" in INSTRUCTIONS and "page_state" in INSTRUCTIONS


# ── результат вызова ──────────────────────────────────────────────────


def test_text_only_result_is_one_block():
    content = to_content(CallOutcome(text="готово"))
    assert len(content) == 1
    assert content[0].text == "готово"


def test_screenshot_becomes_an_image_block():
    """Base64 строкой в тексте модель не увидит — MCP умеет картинки."""
    content = to_content(CallOutcome(text="скриншот", image_b64="iVBORw0KGgo="))
    assert isinstance(content[1], types.ImageContent)
    assert content[1].data == "iVBORw0KGgo="
    assert content[1].mime_type == "image/png"


# ── живой обмен по протоколу ──────────────────────────────────────────


async def test_client_sees_the_tools_over_the_wire():
    """Сборка сервера: обработчики должны быть подключены, а не просто написаны."""
    session = StubSession()
    async with client_for(session) as client:
        result = await client.list_tools()
    names = {t.name for t in result.tools}
    assert "page_state" in names and "click" in names
    assert "ask_user" not in names


async def test_arguments_reach_the_session_unchanged():
    """Разбор аргументов — забота реестра; протокольный слой их не трогает."""
    session = StubSession()
    async with client_for(session) as client:
        await client.call_tool("click", {"ref": "e21", "лишнее": 1})
    assert session.calls == [("click", {"ref": "e21", "лишнее": 1})]


async def test_tool_error_arrives_as_a_result_not_a_transport_error():
    """Иначе текст ошибки не дойдёт до модели и обойти её она не сможет.

    По протоколу ошибка инструмента — обычный ответ с isError; исключение же
    станет ошибкой JSON-RPC, которую клиент покажет как поломку сервера.
    """
    session = StubSession(CallOutcome(text="Элемент e22 перекрыт", is_error=True))
    async with client_for(session) as client:
        result = await client.call_tool("click", {"ref": "e22"})
    assert isinstance(result, types.CallToolResult)
    assert result.is_error
    assert "перекрыт" in result.content[0].text
