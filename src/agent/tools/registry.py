"""Реестр инструментов и генерация их JSON-схем.

Схемы уходят в контекст на каждом шаге, поэтому описания пишутся плотно
и по делу: назначение, граница с соседними инструментами, типовая ошибка.
Суммарный бюджет всех схем — около 2k токенов.

Инструменты общего назначения. Ни одного, знающего про конкретный сайт
или тип задачи (docs/CONSTRAINTS.md §2.1).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..llm import ToolSpec
from .errors import BadArguments, UnknownTool

if TYPE_CHECKING:
    from ..browser import BrowserController, PageState
    from ..core.context import Scratchpad
    from ..llm import LLMRouter


@dataclass(slots=True)
class ToolContext:
    """Всё, что инструмент вправе трогать."""

    controller: BrowserController
    scratchpad: Scratchpad
    #: нужен инструментам, которые сами обращаются к модели (read_page)
    router: LLMRouter
    state: PageState | None = None


@dataclass(slots=True)
class ToolResult:
    """Что инструмент возвращает циклу."""

    #: текст для модели; состояние страницы цикл добавит сам
    text: str
    #: нужно ли пересобрать снапшот после действия
    state_changed: bool = True
    #: задача завершена
    finished: bool = False
    #: успешно ли, если завершена
    success: bool = True
    #: вопрос пользователю — цикл встаёт на паузу
    question: str | None = None
    #: PNG в base64 для vision-фоллбэка; цикл вложит его в сообщение
    image_b64: str | None = None


ToolFn = Callable[..., Awaitable[ToolResult]]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    properties: dict[str, dict[str, Any]]
    required: list[str]
    fn: ToolFn
    #: действие меняет состояние во внешнем мире — для security layer
    destructive: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": self.properties,
                "required": self.required,
            },
        )


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"инструмент {tool.name} уже зарегистрирован")
        self._tools[tool.name] = tool

    def include(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownTool(name, list(self._tools))
        return tool

    def specs(self) -> list[ToolSpec]:
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    async def invoke(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        kwargs = _bind(tool, arguments)
        return await tool.fn(ctx, **kwargs)


#: как модели пишут «значения нет», когда параметр необязательный
_EMPTY = {"null", "none", "undefined", "nil", "nan", ""}


def _bind(tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    """Сверяет присланные аргументы с сигнатурой.

    Лишние аргументы отбрасываем молча — модели любят добавлять поясняющие
    поля, и падать из-за этого было бы расточительно. А вот пропущенный
    обязательный аргумент возвращаем как понятную ошибку.
    """
    signature = inspect.signature(tool.fn)
    accepted = {n for n in signature.parameters if n != "ctx"}

    missing = [name for name in tool.required if name not in arguments]
    if missing:
        raise BadArguments(tool.name, f"не хватает аргументов: {', '.join(missing)}")

    bound = {k: v for k, v in arguments.items() if k in accepted}

    # Необязательный параметр модели часто заполняют строкой "null" вместо того,
    # чтобы его опустить. Замер order_form: шесть шагов подряд ушло на
    # scroll(ref="null") с ответом «нет такого ref». Для обязательных полей
    # такой замены нет — там "null" может быть настоящим текстом.
    for key, value in list(bound.items()):
        if key not in tool.required and isinstance(value, str) and value.strip().lower() in _EMPTY:
            del bound[key]

    return bound


# ── помощники для описания параметров ─────────────────────────────────


def p_str(description: str, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    return schema


def p_int(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def p_bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def make_tool(
    name: str,
    description: str,
    *,
    properties: dict[str, dict[str, Any]] | None = None,
    required: list[str] | None = None,
    destructive: bool = False,
) -> Callable[[ToolFn], Tool]:
    """Декоратор: функция -> зарегистрированный инструмент."""

    def wrap(fn: ToolFn) -> Tool:
        return Tool(
            name=name,
            description=description,
            properties=properties or {},
            required=required or [],
            fn=fn,
            destructive=destructive,
        )

    return wrap
