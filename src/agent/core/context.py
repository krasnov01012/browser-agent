"""Управление контекстом.

Требование задания: целые страницы в контекст не отправлять. Здесь собраны
механизмы, которые держат объём:

1. Системный промпт и схемы инструментов неизменны — провайдер их кэширует.
2. Состояние страницы живёт только в текущем сообщении и в историю не попадает.
3. История компактится: у старых шагов остаётся однострочное резюме.
4. Scratchpad живёт вне истории и всегда прикладывается целиком, поэтому
   находки переживают компакцию.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..llm import ImageContent, Message, ToolCall

#: у скольких последних шагов результат сохраняется дословно
KEEP_VERBATIM = 3
#: длина однострочного резюме старого шага
SUMMARY_CHARS = 140
#: скриншоты тяжёлые — в истории держим только самый свежий
KEEP_IMAGES = 1


@dataclass
class Scratchpad:
    """Внешняя память задачи. Не компактится никогда."""

    facts: list[str] = field(default_factory=list)

    def add(self, fact: str) -> None:
        text = fact.strip()
        if text and text not in self.facts:
            self.facts.append(text)

    def __len__(self) -> int:
        return len(self.facts)

    def render(self) -> str:
        if not self.facts:
            return ""
        lines = "\n".join(f"{i}. {f}" for i, f in enumerate(self.facts, 1))
        return f"Что вы уже выяснили:\n{lines}"


@dataclass(slots=True)
class Step:
    index: int
    call: ToolCall | None
    result: str
    reasoning: str | None = None
    image_b64: str | None = None
    error_kind: str | None = None

    def summary(self) -> str:
        """Однострочник, остающийся после компакции."""
        action = self.call.name if self.call else "нет вызова"
        head = " ".join(self.result.split())[:SUMMARY_CHARS]
        mark = f" [{self.error_kind}]" if self.error_kind else ""
        return f"шаг {self.index}: {action}{mark} — {head}"


@dataclass
class Conversation:
    task: str
    scratchpad: Scratchpad = field(default_factory=Scratchpad)
    steps: list[Step] = field(default_factory=list)
    #: ответы пользователя на ask_user
    answers: list[tuple[str, str]] = field(default_factory=list)
    #: факты из прошлых сессий; неизменны в течение прогона
    recalled: str = ""

    def record(self, step: Step) -> None:
        self.steps.append(step)

    def record_answer(self, question: str, answer: str) -> None:
        self.answers.append((question, answer))

    # ── сборка сообщений ─────────────────────────────────────────────

    def build(
        self,
        *,
        system_prompt: str,
        state_text: str,
        notice: str = "",
    ) -> list[Message]:
        messages: list[Message] = [Message.system(system_prompt, cacheable=True)]
        # Память прошлых сессий приклеена к задаче, а не к текущему шагу:
        # так префикс остаётся неизменным и попадает в кэш провайдера.
        head = f"Задача от пользователя:\n{self.task}"
        if self.recalled:
            head += f"\n\n{self.recalled}"
        messages.append(Message.user(head))
        messages.extend(self._history())
        messages.append(self._current(state_text, notice))
        return messages

    def _history(self) -> list[Message]:
        out: list[Message] = []
        cutoff = len(self.steps) - KEEP_VERBATIM
        images_left = KEEP_IMAGES

        for position, step in enumerate(self.steps):
            if step.call is None:
                # Шаг без вызова инструмента. Раньше он молча пропускался,
                # и модель не получала обратной связи о собственной ошибке —
                # то есть могла повторять её бесконечно.
                out.append(Message.user(step.result))
                continue
            verbatim = position >= cutoff

            out.append(Message(role="assistant", content="", tool_calls=[step.call]))

            if verbatim:
                out.append(Message.tool_result(step.call.id, step.result))
                # Картинку нельзя вложить в сообщение роли "tool" — протокол
                # этого не допускает, и она молча потерялась бы. Отправляем
                # её следующим сообщением пользователя.
                if step.image_b64 and images_left > 0:
                    images_left -= 1
                    out.append(
                        Message.user(
                            "Скриншот страницы с номерами элементов:",
                            [ImageContent(data_b64=step.image_b64)],
                        )
                    )
            else:
                # Старый шаг: остаётся только след того, что было сделано.
                out.append(Message.tool_result(step.call.id, step.summary()))
        return out

    def _current(self, state_text: str, notice: str) -> Message:
        blocks: list[str] = []
        if notice:
            blocks.append(notice)
        if self.answers:
            recent = "\n".join(f"— «{q}» → {a}" for q, a in self.answers[-3:])
            blocks.append(f"Ответы пользователя:\n{recent}")
        memory = self.scratchpad.render()
        if memory:
            blocks.append(memory)
        blocks.append(f"Состояние страницы:\n{state_text}")
        blocks.append("Выберите одно следующее действие.")
        return Message.user("\n\n".join(blocks))

    # ── статистика ───────────────────────────────────────────────────

    def error_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for step in self.steps:
            if step.error_kind:
                counts[step.error_kind] = counts.get(step.error_kind, 0) + 1
        return counts

    def tool_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for step in self.steps:
            if step.call:
                counts[step.call.name] = counts.get(step.call.name, 0) + 1
        return counts
