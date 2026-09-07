"""Маршрутизация вызовов: роль -> модель, повторы, фоллбэк, учёт токенов.

Единственная точка, через которую агент общается с моделью.

Free-tier модели отдают 429 под нагрузкой — это штатная ситуация, а не отказ
(замеры в docs/DECISIONS.md, ADR-008). Поэтому цепочка фоллбэка обязательна.
"""

from __future__ import annotations

import asyncio
import logging
import random

from ..config import Settings
from .anthropic import AnthropicProvider
from .base import (
    LLMError,
    LLMProvider,
    LLMResponse,
    Message,
    ModelUnavailable,
    RateLimited,
    ToolSpec,
)
from .budget import Budget
from .openai_compat import OpenAICompatProvider

log = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_MODEL = 3
BASE_BACKOFF_S = 2.0
MAX_BACKOFF_S = 30.0
#: сколько раз обойти цепочку моделей целиком, прежде чем сдаться
MAX_CHAIN_PASSES = 3


def build_provider(settings: Settings) -> LLMProvider:
    if settings.is_anthropic:
        return AnthropicProvider(base_url=settings.base_url, api_key=settings.api_key)
    return OpenAICompatProvider(
        name=settings.provider,
        base_url=settings.base_url,
        api_key=settings.api_key,
    )


class LLMRouter:
    def __init__(self, settings: Settings, *, budget: Budget | None = None) -> None:
        self._settings = settings
        self._provider = build_provider(settings)
        self.budget = budget or Budget(
            max_steps=settings.max_steps,
            max_input_tokens=settings.max_task_input_tokens,
        )
        # Модели, которые окончательно отпали в этом запуске (нет баланса, нет модели).
        self._dead: set[str] = set()

    async def aclose(self) -> None:
        await self._provider.aclose()

    async def call(
        self,
        role: str,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Вызывает модель роли, при неудаче — следующую в цепочке.

        Ждём только тогда, когда обойдена вся цепочка: пауза перед повтором
        занятой модели бессмысленна, пока рядом стоит другая, со своей квотой.
        """
        last: LLMError | None = None

        for cycle in range(1, MAX_CHAIN_PASSES + 1):
            chain = [m for m in self._settings.models.chain(role) if m not in self._dead]
            if not chain:
                raise LLMError(f"для роли {role!r} не осталось живых моделей")

            for model in chain:
                try:
                    response = await self._call_model(
                        model,
                        messages,
                        tools=tools,
                        max_tokens=max_tokens or self._settings.max_output_tokens,
                        temperature=temperature,
                    )
                except ModelUnavailable as e:
                    # Нет баланса или модели — повторы и другие роли не помогут.
                    log.warning("модель %s выбывает: %s", model, e)
                    self._dead.add(model)
                    last = e
                    continue
                except LLMError as e:
                    log.warning("модель %s не ответила: %s", model, e)
                    last = e
                    continue

                self.budget.record(response.model, response.usage)
                if model != chain[0]:
                    log.info("роль %s отработала на фоллбэке %s", role, model)
                return response

            if cycle < MAX_CHAIN_PASSES:
                delay = _backoff(cycle, last)
                log.info("вся цепочка роли %s занята, пауза %.1f c", role, delay)
                await asyncio.sleep(delay)

        raise last or LLMError(f"роль {role!r}: все модели цепочки отказали")

    # ── повторы внутри одной модели ──────────────────────────────────

    async def _call_model(
        self,
        model: str,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        last: LLMError | None = None

        for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            try:
                return await self._provider.complete(
                    messages=messages,
                    model=model,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except LLMError as e:
                last = e
                # 429 повтором той же модели не лечится: отдаём управление
                # роутеру, он сразу попробует следующую в цепочке.
                if isinstance(e, RateLimited) or not e.retryable:
                    raise
                if attempt == MAX_ATTEMPTS_PER_MODEL:
                    raise
                delay = _backoff(attempt, e)
                log.info(
                    "%s: попытка %d/%d не удалась (%s), пауза %.1f c",
                    model,
                    attempt,
                    MAX_ATTEMPTS_PER_MODEL,
                    type(e).__name__,
                    delay,
                )
                await asyncio.sleep(delay)

        raise last or LLMError(f"{model}: повторы исчерпаны")


def _backoff(attempt: int, error: LLMError | None) -> float:
    """Экспонента с джиттером; Retry-After от провайдера уважаем."""
    if isinstance(error, RateLimited) and error.retry_after:
        return min(error.retry_after, MAX_BACKOFF_S)
    delay = min(BASE_BACKOFF_S * (2 ** (attempt - 1)), MAX_BACKOFF_S)
    return delay * random.uniform(0.7, 1.3)
