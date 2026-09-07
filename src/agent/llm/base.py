"""Контракт провайдера LLM.

Ничего за пределами agent/llm/ не импортирует SDK или модуль конкретного
провайдера — только эти типы. Смена провайдера = правка .env.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


# ── Ошибки ────────────────────────────────────────────────────────────


class LLMError(Exception):
    """Базовая ошибка провайдера."""

    retryable = False

    def __init__(self, message: str, *, model: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.model = model
        self.status = status


class AuthError(LLMError):
    """Ключ неверен или отозван. Повтор бессмыслен."""


class ModelUnavailable(LLMError):
    """Модель не существует, недоступна на тарифе или требует баланса."""


class RateLimited(LLMError):
    """429. Ждём и пробуем снова, затем уходим на следующую модель в цепочке."""

    retryable = True

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, model=model, status=status)
        self.retry_after = retry_after


class TransientError(LLMError):
    """Сеть, таймаут, 5xx. Повторяем."""

    retryable = True


class MalformedResponse(LLMError):
    """Ответ пришёл, но разобрать его не удалось."""


# ── Данные ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def __str__(self) -> str:
        args = json.dumps(self.arguments, ensure_ascii=False)
        return f"{self.name}({args})"


@dataclass(slots=True)
class ImageContent:
    """Скриншот для vision-фоллбэка."""

    data_b64: str
    media_type: str = "image/png"


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class Message:
    role: Role
    content: str = ""
    images: list[ImageContent] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    # для role="tool" — какой вызов этот результат закрывает
    tool_call_id: str | None = None
    # reasoning_content у GLM/o-моделей. Показываем в UI, но НИКОГДА
    # не отправляем обратно — это лишние токены (ADR-011).
    reasoning: str | None = None
    # подсказка провайдеру, что префикс стоит закэшировать
    cacheable: bool = False

    @classmethod
    def system(cls, text: str, *, cacheable: bool = True) -> Message:
        return cls(role="system", content=text, cacheable=cacheable)

    @classmethod
    def user(cls, text: str, images: list[ImageContent] | None = None) -> Message:
        return cls(role="user", content=text, images=images or [])

    @classmethod
    def tool_result(cls, call_id: str, text: str) -> Message:
        return cls(role="tool", content=text, tool_call_id=call_id)


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )

    @property
    def billed_input(self) -> int:
        """Входные токены за вычетом попавших в кэш."""
        return max(0, self.input_tokens - self.cached_tokens)

    def __str__(self) -> str:
        cached = f" (кэш {self.cached_tokens})" if self.cached_tokens else ""
        return f"in={self.input_tokens}{cached} out={self.output_tokens}"


@dataclass(slots=True)
class LLMResponse:
    message: Message
    usage: Usage
    model: str
    stop_reason: str = ""
    latency_s: float = 0.0

    @property
    def truncated(self) -> bool:
        """Ответ обрезан по max_tokens — у reasoning-моделей это частый случай."""
        return self.stop_reason in {"length", "max_tokens"}


# ── Протокол ──────────────────────────────────────────────────────────


@runtime_checkable
class LLMProvider(Protocol):
    """Реализуется в openai_compat.py и anthropic.py."""

    name: str

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...


# ── Разбор аргументов инструмента ─────────────────────────────────────


def parse_tool_arguments(raw: str | dict[str, Any] | None, *, tool: str) -> dict[str, Any]:
    """Модели возвращают аргументы строкой JSON и иногда её портят.

    Пустая строка — валидный случай (инструмент без параметров).
    """
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise MalformedResponse(
            f"инструмент {tool}: аргументы не разобрались как JSON ({e}): {raw[:200]!r}"
        ) from e
    if not isinstance(parsed, dict):
        raise MalformedResponse(
            f"инструмент {tool}: ожидался объект, получено {type(parsed).__name__}"
        )
    return parsed
