"""Сессия браузера для MCP-сервера: жизненный цикл, свежесть состояния, вызов.

Здесь лежит вся содержательная часть обёртки, кроме самого протокола. Причина
разделения простая: в агентном цикле инструменту всё готовит цикл — он снимает
снапшот перед каждым шагом, кладёт его в `ToolContext.state` и показывает модели.
У MCP-сервера цикла нет: клиент дёргает инструменты по одному, между вызовами
может пройти минута, а `ref` без свежего снапшота — просто строка. Значит,
то, что делал цикл, должна делать сессия (docs/ADR.md ADR-040).

Правила сессии, все три:

1. Браузер поднимается лениво, при первом вызове, и переподключается, если
   соединение умерло.
2. Состояние снимается один раз при первом вызове и заново после каждого
   действия, которое страницу изменило.
3. Свежее состояние уезжает клиенту прямо в ответе инструмента — иначе взять
   `ref` ему негде.

Модуль намеренно не импортирует пакет `mcp`: он должен работать (и тестироваться)
без установленного optional-extra.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Error as PlaywrightError

from ..browser import BrowserController, BrowserUnavailable, PageState
from ..config import Settings
from ..core.context import Scratchpad
from ..llm import LLMRouter
from ..tools import ToolContext, ToolError, ToolRegistry, ToolResult, build_registry
from ..tools.registry import make_tool

log = logging.getLogger(__name__)

#: Инструменты, которые обслуживают агентный цикл и вне его бессмысленны.
#:
#: `ask_user` останавливает цикл и ждёт ответа — MCP-сервер ждать не умеет и не
#: должен: в MCP пользователь сидит по ту сторону клиента, и спросить его клиент
#: может сам, без инструмента. `finish` завершает прогон, которого здесь нет.
#: `remember` пишет в scratchpad, который цикл показывает модели каждый шаг, —
#: здесь его читать некому, а история вызовов и так лежит в контексте клиента.
LOOP_ONLY_TOOLS = frozenset({"ask_user", "finish", "remember"})

#: чем подписан блок состояния страницы в ответе инструмента
STATE_HEADER = "--- состояние страницы (ref для других инструментов берите только отсюда) ---"


@make_tool(
    "page_state",
    "Take a fresh snapshot of the page: url, title and the interactive elements with "
    "their refs. Every ref you pass to another tool must come from the latest snapshot. "
    "Tools that change the page return the new state themselves, so call this when you "
    "have no state yet, or when the page may have changed on its own.",
)
async def page_state(ctx: ToolContext) -> ToolResult:
    """Снимок по требованию клиента.

    Инструмент пустой, и это не заглушка. Состояние к ответу подставляет сама
    сессия — всякий раз, когда результат помечен `state_changed`. Достаточно
    выставить эту пометку, и снимок приедет тем же путём, что и после клика,
    без второй ветки кода.

    В реестре агента такого инструмента нет намеренно: циклу он не нужен, он
    снимает состояние сам, а лишняя схема в контексте стоит токенов.
    """
    return ToolResult(text="Снимок состояния снят.", state_changed=True)


def mcp_registry(base: ToolRegistry | None = None) -> ToolRegistry:
    """Реестр в том виде, в каком его видит MCP-клиент.

    Собирается из обычного реестра агента: инструменты те же самые объекты,
    переписывать их незачем. Разница ровно в двух вещах — убраны инструменты
    цикла и добавлен `page_state`.
    """
    base = base or build_registry()
    registry = ToolRegistry()
    registry.include([base.get(name) for name in base.names() if name not in LOOP_ONLY_TOOLS])
    registry.register(page_state)
    return registry


@dataclass(slots=True)
class CallOutcome:
    """Результат вызова в терминах, не знающих про MCP.

    Протокольный слой переводит его в `CallToolResult`; тесты сверяют по нему
    поведение сессии, не поднимая сервер.
    """

    text: str
    image_b64: str | None = None
    is_error: bool = False


class BrowserSession:
    """Один браузер на весь процесс сервера, вызовы строго по очереди."""

    def __init__(
        self,
        settings: Settings,
        *,
        registry: ToolRegistry | None = None,
        controller_factory: Callable[[Settings], BrowserController] = BrowserController,
        router_factory: Callable[[Settings], LLMRouter] = LLMRouter,
    ) -> None:
        self._settings = settings
        self._registry = mcp_registry(registry)
        self._new_controller = controller_factory
        self._new_router = router_factory
        self._controller: BrowserController | None = None
        self._router: LLMRouter | None = None
        self._scratchpad = Scratchpad()
        self._state: PageState | None = None
        # Клиент вправе прислать два вызова разом, а браузер у нас один: общая
        # активная вкладка, общий реестр ref. Два клика внахлёст перемешали бы
        # снимки между собой, поэтому вызовы выполняются строго по одному.
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def call(self, name: str, arguments: dict[str, Any]) -> CallOutcome:
        async with self._lock:
            return await self._call(name, arguments)

    async def aclose(self) -> None:
        """Отпустить браузер и модель. Вызывается при остановке сервера."""
        if self._router is not None:
            await self._router.aclose()
            self._router = None
        await self._drop_browser()

    # ── вызов ────────────────────────────────────────────────────────

    async def _call(self, name: str, arguments: dict[str, Any]) -> CallOutcome:
        try:
            await self._ensure_ready()
        except BrowserUnavailable as e:
            # Не поломка сервера, а состояние окружения: Chrome не запущен.
            # Текст исключения уже объясняет, чем его запустить.
            return CallOutcome(text=str(e), is_error=True)

        if self._state is None:
            await self._snapshot()

        ctx = ToolContext(
            controller=self._require_controller(),
            scratchpad=self._scratchpad,
            router=self._require_router(),
            state=self._state,
        )

        try:
            result = await self._registry.invoke(name, arguments, ctx)
        except ToolError as e:
            # Ошибки инструментов написаны для модели — их и отдаём, дословно.
            # Питоновский трейсбек здесь не нужен никому (tools/errors.py).
            return CallOutcome(text=await self._compose(e.for_model()), is_error=True)
        except BrowserUnavailable as e:
            await self._drop_browser()
            return CallOutcome(text=f"Браузер перестал отвечать: {e}", is_error=True)
        except Exception as e:
            # Непредусмотренная ошибка не должна ронять долгоживущий сервер:
            # клиент получит текст и попробует другой путь, как в цикле агента.
            log.exception("инструмент %s упал", name)
            return CallOutcome(
                text=(
                    f"Инструмент {name} завершился неожиданной ошибкой "
                    f"({type(e).__name__}). Попробуйте другой способ."
                ),
                is_error=True,
            )

        return CallOutcome(
            text=await self._compose(_describe(result), refresh=result.state_changed),
            image_b64=result.image_b64,
        )

    # ── состояние страницы ───────────────────────────────────────────

    async def _compose(self, text: str, *, refresh: bool = True) -> str:
        """Ответ инструмента плюс состояние страницы, если оно могло измениться.

        Состояние прикладывается не всегда: после `read_page` или `list_tabs`
        страница та же, и повторять четыре тысячи токенов ради этого незачем —
        у клиента они уже есть с прошлого раза. А вот после действия и после
        любой ошибки состояние идёт обязательно: ошибка чаще всего означает,
        что страница не та, какой её считает клиент, и следующий его ход
        зависит от того, что там теперь на самом деле.
        """
        if not refresh:
            return text
        state = await self._snapshot()
        return f"{text}\n\n{state}" if state else text

    async def _snapshot(self) -> str:
        """Снять состояние заново и отрисовать его для клиента."""
        controller = self._controller
        if controller is None:
            return ""
        try:
            self._state = await controller.snapshot()
        except (BrowserUnavailable, PlaywrightError) as e:
            # Вкладку закрыли прямо во время вызова. Сам вызов мог удаться,
            # поэтому это не ошибка вызова, а пометка о том, что состояния нет.
            self._state = None
            log.warning("снимок состояния не удался: %s", e)
            return "(состояние страницы прочитать не удалось — попробуйте page_state ещё раз)"
        return f"{STATE_HEADER}\n{self._state.render()}"

    # ── жизненный цикл ───────────────────────────────────────────────

    async def _ensure_ready(self) -> None:
        """Поднять браузер и роутер при первом обращении.

        Лениво, а не на старте процесса. MCP-клиент запускает свои серверы разом
        и заранее — Chrome в этот момент может быть ещё не запущен, а падение при
        старте клиент показывает как «сервер сломан» и больше к нему не идёт.
        Отложенное подключение оставляет рабочим `tools/list` и объясняет беду
        текстом в ответ на первый же вызов.

        Здесь же переподключение: сервер живёт неделями, а Chrome за это время
        перезапускают. Мёртвое соединение видно по `connected`.
        """
        if self._controller is not None and not self._controller.connected:
            log.info("соединение с Chrome потеряно — переподключаемся")
            await self._drop_browser()

        if self._controller is None:
            controller = self._new_controller(self._settings)
            # Присваиваем только после успешного старта: не поднявшийся
            # контроллер не должен остаться в сессии — следующий вызов
            # обязан попробовать заново.
            await controller.start()
            self._controller = controller
            self._state = None

        if self._router is None:
            # Нужен одному `read_page`, но создаётся вместе с браузером:
            # сервер, к которому не обратились ни разу, не держит ни одного
            # http-клиента.
            self._router = self._new_router(self._settings)

    async def _drop_browser(self) -> None:
        controller, self._controller, self._state = self._controller, None, None
        if controller is None:
            return
        try:
            await controller.close()
        except Exception as e:
            log.debug("закрытие контроллера: %s", e)

    def _require_controller(self) -> BrowserController:
        if self._controller is None:  # pragma: no cover — сюда не попасть после _ensure_ready
            raise BrowserUnavailable("браузер не подключён")
        return self._controller

    def _require_router(self) -> LLMRouter:
        if self._router is None:  # pragma: no cover — сюда не попасть после _ensure_ready
            raise BrowserUnavailable("роутер моделей не создан")
        return self._router


def _describe(result: ToolResult) -> str:
    """Текст результата с учётом полей, которых в MCP нет.

    `question` и `finished` — понятия агентного цикла: первое ставит цикл на
    паузу, второе его завершает. Инструменты, которые их выставляют, наружу
    не выведены (LOOP_ONLY_TOOLS), но поля есть у любого `ToolResult`, и молча
    терять их нельзя: вопрос пользователю, приехавший как обычный ответ, — это
    ровно тот случай, когда клиент уверенно делает не то.
    """
    parts = [result.text]
    if result.question:
        parts.append(
            f"Инструменту нужен ответ пользователя: {result.question}\n"
            f"Сервер ждать не умеет — спросите пользователя сами и вызовите инструмент "
            f"заново, уже с ответом."
        )
    if result.finished:
        parts.append(
            f"Инструмент считает задачу завершённой (success={str(result.success).lower()}). "
            f"Для MCP это просто отчёт: сервер ничего не заканчивает и продолжает работать."
        )
    return "\n\n".join(part for part in parts if part)


__all__ = [
    "LOOP_ONLY_TOOLS",
    "STATE_HEADER",
    "BrowserSession",
    "CallOutcome",
    "mcp_registry",
    "page_state",
]
