"""Учёт токенов и жёсткие потолки на задачу.

Смысл не в деньгах, а в защите от зацикливания: агент, который застрял,
должен упереться в лимит и завершиться отчётом, а не молотить бесконечно.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Usage


class BudgetExceeded(RuntimeError):
    """Задача исчерпала лимит шагов или токенов."""


@dataclass
class Budget:
    max_steps: int
    max_input_tokens: int
    # доля лимита, после которой агент получает предупреждение и идёт к завершению
    warn_ratio: float = 0.8

    steps: int = 0
    usage: Usage = field(default_factory=Usage)
    by_model: dict[str, Usage] = field(default_factory=dict)

    # ── учёт ─────────────────────────────────────────────────────────

    def record(self, model: str, usage: Usage) -> None:
        self.usage = self.usage + usage
        self.by_model[model] = self.by_model.get(model, Usage()) + usage

    def reset(self) -> None:
        """Новая задача. Роутер живёт дольше прогона, счётчики — нет:
        иначе метрики второй задачи включали бы расход первой."""
        self.steps = 0
        self.usage = Usage()
        self.by_model = {}

    def start_step(self) -> None:
        """Вызывается перед шагом. Бросает, если лимит уже выбран."""
        if self.steps >= self.max_steps:
            raise BudgetExceeded(f"исчерпан лимит шагов ({self.max_steps})")
        if self.usage.input_tokens >= self.max_input_tokens:
            raise BudgetExceeded(
                "исчерпан лимит входных токенов "
                f"({self.usage.input_tokens}/{self.max_input_tokens})"
            )
        self.steps += 1

    # ── состояние ────────────────────────────────────────────────────

    @property
    def steps_left(self) -> int:
        return max(0, self.max_steps - self.steps)

    @property
    def tokens_left(self) -> int:
        return max(0, self.max_input_tokens - self.usage.input_tokens)

    @property
    def exhaustion(self) -> float:
        """Насколько выбран самый нагруженный из двух лимитов, 0..1."""
        by_steps = self.steps / self.max_steps if self.max_steps else 0.0
        by_tokens = (
            self.usage.input_tokens / self.max_input_tokens if self.max_input_tokens else 0.0
        )
        return min(1.0, max(by_steps, by_tokens))

    @property
    def should_wrap_up(self) -> bool:
        """Пора сворачиваться — агенту уходит предупреждение в контекст."""
        return self.exhaustion >= self.warn_ratio

    def summary(self) -> str:
        cache_note = ""
        if self.usage.input_tokens:
            share = self.usage.cached_tokens / self.usage.input_tokens
            cache_note = f", из кэша {share:.0%}"
        return (
            f"шагов {self.steps}/{self.max_steps}, "
            f"токенов на вход {self.usage.input_tokens}/{self.max_input_tokens}{cache_note}, "
            f"на выход {self.usage.output_tokens}"
        )
