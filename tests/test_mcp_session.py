"""Сессия MCP-сервера: свежесть состояния, жизненный цикл браузера, ошибки.

Браузер здесь поддельный. Проверяется то, что в MCP пришлось построить заново,
потому что агентного цикла рядом нет: кто и когда снимает снапшот, что видит
инструмент в `ctx.state`, что получает клиент вместо исключения и что делает
сервер, когда Chrome не запущен или умер посреди работы.
"""

from __future__ import annotations

import asyncio

import pytest

from agent.browser import BrowserUnavailable
from agent.browser.snapshot import Element, PageState
from agent.mcp.session import STATE_HEADER, BrowserSession, mcp_registry
from agent.tools.errors import Covered
from agent.tools.registry import Tool, ToolRegistry, ToolResult, make_tool, p_str


def state(url: str = "https://example.test/", ref: str = "e1") -> PageState:
    return PageState(
        url=url,
        title="Страница",
        elements=[Element(ref=ref, role="button", name="Кнопка")],
    )


class FakeController:
    """Контроллер без браузера: считает снимки и умеет притворяться мёртвым."""

    def __init__(self, states: list[PageState] | None = None) -> None:
        self._states = states or [state()]
        self.snapshots = 0
        self.closed = False
        self.started = False
        self.connected = True

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def snapshot(self, *, wait: bool = True) -> PageState:
        self.snapshots += 1
        return self._states[min(self.snapshots - 1, len(self._states) - 1)]


class FakeRouter:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def session_with(
    *tools: Tool,
    settings,
    controller: FakeController | None = None,
    controllers: list[FakeController] | None = None,
) -> tuple[BrowserSession, list[FakeController], FakeRouter]:
    """Сессия на поддельном браузере. Возвращает ещё и то, что она создала."""
    queue = list(controllers or [controller or FakeController()])
    made: list[FakeController] = []
    router = FakeRouter()

    def make_controller(_settings):
        made.append(queue.pop(0) if queue else FakeController())
        return made[-1]

    registry = ToolRegistry()
    registry.include(list(tools))
    return (
        BrowserSession(
            settings,
            registry=registry,
            controller_factory=make_controller,
            router_factory=lambda _settings: router,
        ),
        made,
        router,
    )


# ── какие инструменты вообще выставлены ───────────────────────────────


def test_loop_only_tools_are_not_exposed():
    """ask_user, finish и remember обслуживают цикл, а цикла в MCP нет.

    Выставить их наружу — значит пообещать клиенту паузу, которой сервер
    не умеет, и завершение задачи, которой он не ведёт.
    """
    names = mcp_registry().names()
    assert "ask_user" not in names
    assert "finish" not in names
    assert "remember" not in names
    assert "click" in names


def test_page_state_is_added_because_nobody_else_snapshots():
    """В цикле снимок делается сам перед каждым шагом; здесь просить его некому."""
    assert "page_state" in mcp_registry().names()


# ── состояние страницы ────────────────────────────────────────────────


@make_tool("act", "действие", properties={"ref": p_str("ref")}, required=["ref"])
async def act(ctx, ref: str) -> ToolResult:
    return ToolResult(text=f"сделано с {ref}")


@make_tool("look", "чтение")
async def look(ctx) -> ToolResult:
    return ToolResult(text="прочитано", state_changed=False)


async def test_action_brings_the_new_state_back(settings):
    """Без этого клиенту негде взять ref для следующего шага.

    В цикле состояние приходит модели перед каждым шагом; в MCP единственный
    канал к клиенту — ответ инструмента, значит состояние едет в нём.
    """
    session, _, _ = session_with(
        act, settings=settings, controller=FakeController([state(ref="e1"), state(ref="e77")])
    )
    outcome = await session.call("act", {"ref": "e1"})
    assert STATE_HEADER in outcome.text
    assert "e77" in outcome.text, "приехало состояние до действия, а не после"


async def test_reading_does_not_re_read_the_page(settings):
    """Состояние стоит несколько тысяч токенов — за просто так его не шлют."""
    controller = FakeController()
    session, _, _ = session_with(look, settings=settings, controller=controller)
    outcome = await session.call("look", {})
    assert STATE_HEADER not in outcome.text
    # Единственный снимок — тот, что снят перед вызовом.
    assert controller.snapshots == 1


@make_tool("spy", "подсматривает состояние")
async def spy(ctx) -> ToolResult:
    spy_seen.append(ctx.state)
    return ToolResult(text="ок", state_changed=False)


spy_seen: list[PageState | None] = []


async def test_tool_sees_the_same_state_the_client_saw(settings):
    """Иначе ref из ответа клиента и ref в `ctx.state` — из разных снимков.

    `find_in_page` и `screenshot` читают `ctx.state`; если он новее того,
    что видел клиент, они отвечают про страницу, которой клиент не видел.
    """
    spy_seen.clear()
    first, second = state(ref="e1"), state(ref="e2")
    session, _, _ = session_with(
        act, spy, settings=settings, controller=FakeController([first, second])
    )
    await session.call("act", {"ref": "e1"})  # после действия снят second
    await session.call("spy", {})
    assert spy_seen == [second]


async def test_page_state_returns_a_snapshot(settings):
    session, _, _ = session_with(settings=settings, controller=FakeController([state(ref="e9")]))
    outcome = await session.call("page_state", {})
    assert STATE_HEADER in outcome.text
    assert "e9" in outcome.text
    assert not outcome.is_error


# ── ошибки ────────────────────────────────────────────────────────────


@make_tool("covered", "падает как перекрытый элемент", properties={}, required=[])
async def covered(ctx) -> ToolResult:
    raise Covered("e22", "<div> «Куки»")


async def test_tool_error_arrives_as_its_own_text(settings):
    """Клиенту нужен текст for_model(), а не трейсбек: он его читает моделью."""
    session, _, _ = session_with(covered, settings=settings)
    outcome = await session.call("covered", {})
    assert outcome.is_error
    assert "перебирать другие ref" in outcome.text
    assert "Traceback" not in outcome.text


async def test_failed_call_brings_the_state_along(settings):
    """Ошибка почти всегда значит «страница не та» — показываем, какая она."""
    session, _, _ = session_with(covered, settings=settings)
    outcome = await session.call("covered", {})
    assert STATE_HEADER in outcome.text


async def test_missing_required_argument_is_an_answer_not_a_crash(settings):
    session, _, _ = session_with(act, settings=settings)
    outcome = await session.call("act", {})
    assert outcome.is_error
    assert "ref" in outcome.text


async def test_unknown_tool_lists_what_exists(settings):
    session, _, _ = session_with(act, settings=settings)
    outcome = await session.call("клик", {})
    assert outcome.is_error
    assert "page_state" in outcome.text


@make_tool("boom", "падает не по-нашему")
async def boom(ctx) -> ToolResult:
    raise ZeroDivisionError("деление на ноль")


async def test_unexpected_crash_does_not_end_the_session(settings):
    """Сервер живёт неделями: одно упавшее обращение не повод его закрывать."""
    session, _, _ = session_with(boom, look, settings=settings)
    outcome = await session.call("boom", {})
    assert outcome.is_error
    assert "ZeroDivisionError" in outcome.text
    assert not (await session.call("look", {})).is_error


# ── жизненный цикл браузера ───────────────────────────────────────────


class DeadController(FakeController):
    async def start(self) -> None:
        raise BrowserUnavailable("не удалось подключиться к Chrome, запустите launch_chrome.ps1")


async def test_browser_that_is_not_running_is_explained_in_words(settings):
    """Клиент запускает серверы при своём старте — Chrome тогда может не быть.

    Падать на этом нельзя: клиент пометит сервер сломанным и больше не придёт.
    """
    session, _, _ = session_with(
        look, settings=settings, controllers=[DeadController(), DeadController()]
    )
    outcome = await session.call("look", {})
    assert outcome.is_error
    assert "launch_chrome" in outcome.text


async def test_browser_is_retried_on_the_next_call(settings):
    """Пользователь запустил Chrome после сервера — второй вызов обязан ожить."""
    alive = FakeController()
    session, made, _ = session_with(look, settings=settings, controllers=[DeadController(), alive])
    await session.call("look", {})
    outcome = await session.call("look", {})
    assert not outcome.is_error
    assert len(made) == 2 and alive.started


async def test_dead_connection_is_replaced(settings):
    """Chrome перезапускают чаще, чем MCP-клиент."""
    first, second = FakeController(), FakeController()
    session, made, _ = session_with(look, settings=settings, controllers=[first, second])
    await session.call("look", {})
    first.connected = False
    await session.call("look", {})
    assert len(made) == 2
    assert first.closed and second.started


async def test_closing_the_session_releases_everything(settings):
    controller = FakeController()
    session, _, router = session_with(look, settings=settings, controller=controller)
    await session.call("look", {})
    await session.aclose()
    assert controller.closed and router.closed


# ── понятия, которых в MCP нет ────────────────────────────────────────


@make_tool("asker", "хочет спросить пользователя")
async def asker(ctx) -> ToolResult:
    return ToolResult(text="", state_changed=False, question="Каким адресом войти?")


async def test_question_becomes_words_for_the_client(settings):
    """ask_user наружу не выставлен, но поле question есть у любого результата.

    Потерять его молча — значит превратить вопрос в утверждение.
    """
    session, _, _ = session_with(asker, settings=settings)
    outcome = await session.call("asker", {})
    assert "Каким адресом войти?" in outcome.text
    assert "вызовите инструмент заново" in outcome.text


@make_tool("ender", "объявляет задачу законченной")
async def ender(ctx) -> ToolResult:
    return ToolResult(text="готово", state_changed=False, finished=True, success=False)


async def test_finished_is_only_a_report(settings):
    session, _, _ = session_with(ender, settings=settings)
    outcome = await session.call("ender", {})
    assert "success=false" in outcome.text
    assert not outcome.is_error


@make_tool("shot", "отдаёт картинку")
async def shot(ctx) -> ToolResult:
    return ToolResult(text="скриншот", state_changed=False, image_b64="iVBORw0KGgo=")


async def test_screenshot_leaves_the_session_as_an_image(settings):
    session, _, _ = session_with(shot, settings=settings)
    outcome = await session.call("shot", {})
    assert outcome.image_b64 == "iVBORw0KGgo="


# ── одновременность ───────────────────────────────────────────────────


overlap = {"now": 0, "max": 0}


@make_tool("slow", "долгий")
async def slow(ctx) -> ToolResult:
    overlap["now"] += 1
    overlap["max"] = max(overlap["max"], overlap["now"])
    await asyncio.sleep(0)
    overlap["now"] -= 1
    return ToolResult(text="ок", state_changed=False)


async def test_calls_never_overlap(settings):
    """Браузер один: вкладка общая, реестр ref общий.

    Клиент вправе прислать два вызова разом — второй клик посреди первого
    перемешал бы снимки, и ref начали бы указывать не туда.
    """
    overlap.update(now=0, max=0)
    session, _, _ = session_with(slow, settings=settings)
    await asyncio.gather(*(session.call("slow", {}) for _ in range(5)))
    assert overlap["max"] == 1


@pytest.mark.parametrize("name", ["click", "type_text", "close_tab", "upload_file"])
def test_destructive_flag_survives_the_transfer(name: str):
    """Аннотации MCP строятся из него же — если флаг потеряется, потеряются и они."""
    assert mcp_registry().get(name).destructive
