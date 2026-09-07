"""Реестр ref: что происходит с элементом, уехавшим за край экрана.

Браузера здесь нет — вместо фрейма подставлена заглушка, отвечающая на тот
единственный вопрос, который реестр ему задаёт: жив ли узел с таким ref.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError

from agent.browser.refs import InvalidRef, RefRegistry


class FakeFrame:
    """Фрейм, который помнит выданные ref ровно как `window.__agentRegistry`."""

    def __init__(self, alive: set[str], *, broken: bool = False) -> None:
        self.alive = alive
        self.broken = broken
        self.asked: list[str] = []

    async def evaluate(self, _script: str, ref: str) -> bool:
        self.asked.append(ref)
        if self.broken:
            raise PlaywrightError("фрейм отсоединился")
        return ref in self.alive


async def test_ref_out_of_snapshot_is_found_on_the_page():
    """Поле поиска уехало вверх после прокрутки — но оно всё ещё на странице."""
    frame = FakeFrame({"e18"})
    registry = RefRegistry()
    registry.clear([frame])

    assert "e18" not in registry
    assert await registry._offscreen_entry("e18") == (frame, "e18")
    assert frame.asked == ["e18"]


async def test_found_ref_is_remembered():
    """Второй вызов того же ref не должен снова ходить в страницу."""
    frame = FakeFrame({"e18"})
    registry = RefRegistry()
    registry.clear([frame])

    await registry._offscreen_entry("e18")
    assert "e18" in registry


async def test_ref_of_removed_node_is_not_resurrected():
    frame = FakeFrame(set())
    registry = RefRegistry()
    registry.clear([frame])

    assert await registry._offscreen_entry("e18") is None


async def test_invented_ref_stays_invalid():
    """Выдуманное имя не должно даже доходить до страницы."""
    frame = FakeFrame({"e18"})
    registry = RefRegistry()
    registry.clear([frame])

    assert await registry._offscreen_entry("кнопка входа") is None
    assert frame.asked == []


async def test_frame_is_taken_by_number_from_the_same_snapshot():
    """`f1e5` ищется во втором фрейме — и только в нём.

    Иначе после перестановки фреймов `e5` соседа выдал бы себя за исходный
    элемент: локальные номера у фреймов свои и совпадают сплошь и рядом.
    """
    main, inner = FakeFrame({"e5"}), FakeFrame({"e5"})
    registry = RefRegistry()
    registry.clear([main, inner])

    assert await registry._offscreen_entry("f1e5") == (inner, "e5")
    assert main.asked == []


async def test_missing_frame_is_not_an_error():
    registry = RefRegistry()
    registry.clear([FakeFrame({"e5"})])

    assert await registry._offscreen_entry("f7e5") is None


async def test_broken_frame_is_not_an_error():
    """Фрейм мог отсоединиться между снимком и действием."""
    frame = FakeFrame({"e18"}, broken=True)
    registry = RefRegistry()
    registry.clear([frame])

    assert await registry._offscreen_entry("e18") is None


async def test_resolve_reports_invalid_ref_when_nothing_matches():
    registry = RefRegistry()
    registry.clear([FakeFrame(set())])

    with pytest.raises(InvalidRef) as caught:
        await registry.resolve("e18")
    assert "e18" in caught.value.for_model()


async def test_clear_forgets_the_frames_of_the_previous_snapshot():
    """Ref прошлого снимка не должен искаться во фреймах нового."""
    old = FakeFrame({"e18"})
    registry = RefRegistry()
    registry.clear([old])
    registry.clear()

    assert await registry._offscreen_entry("e18") is None
    assert old.asked == []
