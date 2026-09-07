"""Память между сессиями.

Факты, накопленные в scratchpad, переживают перезапуск: агент может опереться
на то, что выяснил в прошлый раз.

Важно для соблюдения ограничений: сюда попадает только то, что агент **добыл
сам** во время работы. Предзаполнять память знаниями о сайтах нельзя — это
превратило бы её в подсказку (docs/CONSTRAINTS.md §2.3).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: сколько записей хранить; старые вытесняются
MAX_ENTRIES = 200
#: сколько последних фактов подмешивать в новую задачу
RECALL_LIMIT = 12


@dataclass(slots=True)
class MemoryEntry:
    fact: str
    task: str
    at: float

    def age_days(self) -> float:
        return (time.time() - self.at) / 86400


class Memory:
    """Хранилище фактов в JSON-файле."""

    def __init__(self, directory: Path, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._path = directory / "facts.json"
        self._entries: list[MemoryEntry] = []
        if enabled:
            self._load()

    # ── ввод-вывод ───────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("память не прочиталась, начинаем с чистой: %s", e)
            return
        for item in raw if isinstance(raw, list) else []:
            try:
                self._entries.append(
                    MemoryEntry(
                        fact=str(item["fact"]),
                        task=str(item.get("task", "")),
                        at=float(item.get("at", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

    def save(self) -> None:
        if not self.enabled:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {"fact": e.fact, "task": e.task, "at": e.at} for e in self._entries[-MAX_ENTRIES:]
            ]
            self._path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError as e:
            log.warning("память не сохранилась: %s", e)

    # ── работа ───────────────────────────────────────────────────────

    def remember_all(self, facts: list[str], task: str) -> None:
        now = time.time()
        known = {e.fact for e in self._entries}
        for fact in facts:
            text = fact.strip()
            if text and text not in known:
                self._entries.append(MemoryEntry(fact=text, task=task, at=now))
                known.add(text)
        del self._entries[:-MAX_ENTRIES]

    def recall(self) -> str:
        """Блок для промпта. Пусто, если вспоминать нечего."""
        if not self.enabled or not self._entries:
            return ""
        recent = self._entries[-RECALL_LIMIT:]
        lines = []
        for entry in recent:
            age = entry.age_days()
            when = "сегодня" if age < 1 else f"{int(age)} дн. назад"
            lines.append(f"— {entry.fact} ({when})")
        return (
            "Из прошлых сессий вы знаете следующее. Это может быть устаревшим — "
            "проверяйте, прежде чем полагаться:\n" + "\n".join(lines)
        )

    def __len__(self) -> int:
        return len(self._entries)
