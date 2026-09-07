"""Подтверждение необратимых действий — продвинутый паттерн №3.

По умолчанию выключен (решение брифинга), включается `CONFIRM_DESTRUCTIVE=true`
или флагом `--confirm-destructive`.

Никаких списков «опасных кнопок»: это был бы хардкод знаний о сайтах
(docs/CONSTRAINTS.md §2.3). Вместо этого дешёвая модель смотрит на само
действие и на подпись элемента и решает, необратимо ли оно.
"""

from __future__ import annotations

import logging

from ..browser import PageState
from ..llm import LLMError, LLMRouter, Message
from ..tools import Tool

log = logging.getLogger(__name__)

SYSTEM = """Ты — предохранитель браузерного агента.

Тебе описывают одно действие, которое агент собирается совершить на странице.
Реши, является ли оно НЕОБРАТИМЫМ с точки зрения пользователя.

Необратимо — это когда действие:
- отправляет сообщение, заявку, форму или публикует что-либо;
- удаляет или безвозвратно меняет данные;
- тратит деньги или подтверждает заказ;
- меняет настройки аккаунта, выходит из него, разрывает связь с сервисом.

Обратимо — навигация, прокрутка, открытие и закрытие вкладок, раскрытие
разделов, ввод текста в поле без отправки, применение фильтров, поиск.

Ответь ровно одним словом:
НЕОБРАТИМО — если действие подходит под первый список,
ОБРАТИМО — во всех остальных случаях, включая сомнительные."""


class SecurityGuard:
    """Решает, нужно ли спросить пользователя перед действием."""

    def __init__(self, router: LLMRouter, *, enabled: bool) -> None:
        self._router = router
        self.enabled = enabled

    async def confirmation_for(
        self,
        tool: Tool,
        arguments: dict,
        state: PageState | None,
    ) -> str | None:
        """Вопрос пользователю, если действие необратимо. Иначе None."""
        if not self.enabled or not tool.destructive:
            return None

        target = describe_target(arguments, state)
        verdict = await self._classify(tool.name, arguments, target)
        if not verdict:
            return None

        return (
            f"Агент собирается выполнить необратимое действие: "
            f"{tool.name} — {target}. Подтверждаете? (да / нет)"
        )

    async def _classify(self, name: str, arguments: dict, target: str) -> bool:
        prompt = (
            f"Действие: {name}\n"
            f"Аргументы: {arguments}\n"
            f"Элемент: {target}\n\n"
            f"Необратимо или обратимо?"
        )
        try:
            response = await self._router.call(
                "extractor",
                [Message.system(SYSTEM), Message.user(prompt)],
                max_tokens=400,
            )
        except LLMError as e:
            # Предохранитель, который сам сломался, не должен блокировать работу.
            log.warning("классификатор недоступен, действие пропущено: %s", e)
            return False

        answer = response.message.content.strip().upper()
        return "НЕОБРАТИМО" in answer


def describe_target(arguments: dict, state: PageState | None) -> str:
    """Человеческое описание цели действия — по подписи из снапшота.

    Публичная: тем же описанием пользуется реестр совершённых действий
    (core/ledger.py), и расходиться эти два взгляда на одно действие
    не должны — иначе кнопка в вопросе пользователю и она же в реестре
    назовутся по-разному.
    """
    ref = str(arguments.get("ref") or "")
    if not ref:
        return ", ".join(f"{k}={v!r}" for k, v in arguments.items()) or "без цели"
    if state is None:
        return f"элемент {ref}"

    for element in state.elements:
        if element.ref == ref:
            return f"{element.role} «{state.label_for(ref) or 'без подписи'}»"
    return f"элемент {ref}"
