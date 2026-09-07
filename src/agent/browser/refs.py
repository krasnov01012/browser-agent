"""Реестр ref: короткий идентификатор элемента -> живой узел в браузере.

Модель никогда не видит селекторы и внутренние id — только ref вида `e21`.
Это осознанное решение: замена технических идентификаторов на короткие
семантические заметно снижает выдумывание несуществующих целей.

Ref стабилен, пока узел жив: реестр на стороне страницы помнит соответствие
узел -> ref, поэтому частичный ре-рендер номера не сдвигает.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from playwright.async_api import ElementHandle, Frame
from playwright.async_api import Error as PlaywrightError

# Сколько валидных ref показать в сообщении об ошибке.
_SUGGEST_LIMIT = 12

_RESOLVE_JS = "r => (window.__agentRegistry && window.__agentRegistry.byRef.get(r)) || null"
_ALIVE_JS = """r => {
  const registry = window.__agentRegistry;
  const el = registry && registry.byRef.get(r);
  return Boolean(el && el.isConnected);
}"""

#: `e21` в главном документе, `f2e5` — во втором фрейме
_REF_SHAPE = re.compile(r"(?:f(\d+))?(e\d+)")


class RefError(Exception):
    """Базовая: ref не удалось превратить в действие."""

    def for_model(self) -> str:
        raise NotImplementedError


class InvalidRef(RefError):
    """Такого ref в последнем снапшоте не было — вероятно, он выдуман."""

    def __init__(self, ref: str, known: list[str]) -> None:
        super().__init__(f"неизвестный ref {ref!r}")
        self.ref = ref
        self.known = known

    def for_model(self) -> str:
        sample = ", ".join(self.known[:_SUGGEST_LIMIT])
        extra = len(self.known) - _SUGGEST_LIMIT
        more = f" и ещё {extra}" if extra > 0 else ""
        return (
            f"Элемента {self.ref} нет в текущем снапшоте. "
            f"Используйте только ref из последнего состояния страницы: {sample}{more}."
        )


class StaleRef(RefError):
    """Узел был, но исчез из DOM — страница перерисовалась."""

    def __init__(self, ref: str) -> None:
        super().__init__(f"ref {ref!r} больше не существует")
        self.ref = ref

    def for_model(self) -> str:
        return (
            f"Элемент {self.ref} исчез со страницы — она успела перерисоваться. "
            f"Посмотрите на обновлённое состояние и выберите цель заново."
        )


@dataclass(slots=True)
class RefRegistry:
    """Соответствие ref -> (фрейм, локальный ref внутри фрейма).

    Фреймы адресуются префиксом: `e21` в главном документе, `f2e5` во втором
    фрейме. Для модели это просто непрозрачная строка — устройство фреймов
    её не касается.
    """

    _entries: dict[str, tuple[Frame, str]] = field(default_factory=dict)
    #: фреймы последнего снимка по их номеру — по ним ищется то,
    #: что в снимок не попало (см. `_offscreen_entry`)
    _frames: dict[int, Frame] = field(default_factory=dict)

    def clear(self, frames: Iterable[Frame] = ()) -> None:
        self._entries.clear()
        self._frames = dict(enumerate(frames))

    def add(self, ref: str, frame: Frame, local_ref: str) -> None:
        self._entries[ref] = (frame, local_ref)

    def known(self) -> list[str]:
        return list(self._entries)

    def __contains__(self, ref: object) -> bool:
        return ref in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def qualify(frame_index: int, local_ref: str) -> str:
        """Локальный ref фрейма -> глобальный."""
        return local_ref if frame_index == 0 else f"f{frame_index}{local_ref}"

    @staticmethod
    def normalize(ref: str) -> str:
        """Приводит ref к каноническому виду.

        В снапшоте ref напечатан как `[e12]` — скобки нужны, чтобы глазом
        отделить его от подписи. Модель добросовестно копирует то, что видит,
        и присылает `"[e12]"`. Замер vacancies: 14 вызовов подряд отклонены,
        прогон закончился ничем, притом что нужный ref был правильный.
        Разницу между `[e12]` и `e12` видит только парсер, поэтому её здесь
        и не стало (docs/DECISIONS.md ADR-023).
        """
        return ref.strip().strip("[]").strip()

    async def _offscreen_entry(self, ref: str) -> tuple[Frame, str] | None:
        """Ref не из последнего снимка — но, возможно, элемент никуда не делся.

        В снимок попадает окно вокруг видимой области, поэтому поле поиска,
        уехавшее вверх после трёх прокруток, из него пропадает. Модель помнит
        его ref и называет по делу, а реестр отвечает «такого нет»: на замере
        `vacancies` так сгорели два шага подряд на поле, которое всё это время
        было на странице. Реестр на стороне страницы помнит каждый выданный ref
        и сам вычищает отсоединённые узлы, так что спросить его дешевле, чем
        гонять агента искать заново; прокрутку к элементу дальше сделает
        Playwright — у него это часть проверки кликабельности.

        Фрейм берётся не по имени, а по номеру из того же снимка, который выдал
        ref: `f2e5` разрешается во фрейме, который был вторым при последнем
        обходе. Иначе после перестановки фреймов `e5` соседа выглядел бы как
        тот же самый элемент (docs/DECISIONS.md ADR-030).
        """
        match = _REF_SHAPE.fullmatch(ref)
        if match is None:
            return None
        frame = self._frames.get(int(match.group(1) or 0))
        if frame is None:
            return None

        local_ref = match.group(2)
        try:
            alive = await frame.evaluate(_ALIVE_JS, local_ref)
        except PlaywrightError:
            return None
        if not alive:
            return None

        entry = (frame, local_ref)
        self._entries[ref] = entry
        return entry

    async def resolve(self, ref: str) -> ElementHandle:
        """ref -> живой ElementHandle. Бросает InvalidRef или StaleRef."""
        ref = self.normalize(ref)
        entry = self._entries.get(ref) or await self._offscreen_entry(ref)
        if entry is None:
            raise InvalidRef(ref, self.known())

        frame, local_ref = entry
        try:
            handle = await frame.evaluate_handle(_RESOLVE_JS, local_ref)
        except PlaywrightError as e:
            # Фрейм отсоединился или ушёл на другую страницу.
            raise StaleRef(ref) from e

        element = handle.as_element()
        if element is None:
            await handle.dispose()
            raise StaleRef(ref)

        try:
            connected = await element.evaluate("el => el.isConnected")
        except PlaywrightError as e:
            raise StaleRef(ref) from e
        if not connected:
            raise StaleRef(ref)

        return element
