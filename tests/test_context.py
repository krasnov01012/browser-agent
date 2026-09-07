"""Компакция истории, scratchpad и разбор ref."""

from __future__ import annotations

import pytest

from agent.browser.refs import InvalidRef, RefRegistry
from agent.core.context import KEEP_VERBATIM, Conversation, Scratchpad, Step
from agent.llm import ToolCall


def step(index: int, result: str) -> Step:
    return Step(
        index=index, call=ToolCall(id=f"c{index}", name="click", arguments={}), result=result
    )


def test_recent_steps_keep_their_full_result():
    talk = Conversation(task="задача")
    for i in range(1, 6):
        talk.record(step(i, f"подробный результат {i} " + "х" * 300))
    rendered = "\n".join(m.content for m in talk.build(system_prompt="s", state_text="—"))
    assert "подробный результат 5 " + "х" * 300 in rendered


def test_old_steps_shrink_to_one_line():
    talk = Conversation(task="задача")
    for i in range(1, 6):
        talk.record(step(i, f"подробный результат {i} " + "х" * 300))
    rendered = "\n".join(m.content for m in talk.build(system_prompt="s", state_text="—"))
    assert "шаг 1: click — подробный результат 1" in rendered
    assert "подробный результат 1 " + "х" * 300 not in rendered


def test_every_step_leaves_a_trace():
    talk = Conversation(task="задача")
    for i in range(1, 9):
        talk.record(step(i, f"результат {i}"))
    messages = talk.build(system_prompt="s", state_text="—")
    assistant = [m for m in messages if m.role == "assistant"]
    assert len(assistant) == 8
    assert len([m for m in messages if m.role == "tool"]) == 8


def test_scratchpad_survives_compaction():
    """Находки должны переживать сжатие — ради этого scratchpad и живёт вне истории."""
    talk = Conversation(task="задача")
    talk.scratchpad.add("Вакансия 1 — Яндекс, 300 000 ₽")
    for i in range(1, 20):
        talk.record(step(i, f"результат {i}"))
    last = talk.build(system_prompt="s", state_text="—")[-1]
    assert "Вакансия 1 — Яндекс, 300 000 ₽" in last.content


def test_scratchpad_ignores_repeats_and_blanks():
    pad = Scratchpad()
    pad.add("факт")
    pad.add("  факт  ")
    pad.add("   ")
    assert len(pad) == 1


def test_state_text_goes_only_into_the_current_message():
    """Основание ADR-024: сравнивать дельту модели не с чем."""
    talk = Conversation(task="задача")
    for i in range(1, 6):
        talk.record(step(i, f"результат {i}"))
    messages = talk.build(system_prompt="s", state_text="УНИКАЛЬНОЕ-СОСТОЯНИЕ")
    assert "УНИКАЛЬНОЕ-СОСТОЯНИЕ" in messages[-1].content
    assert sum("УНИКАЛЬНОЕ-СОСТОЯНИЕ" in m.content for m in messages) == 1


def test_a_step_without_a_tool_call_is_still_reported_back():
    talk = Conversation(task="задача")
    talk.record(Step(index=1, call=None, result="Вы не вызвали инструмент"))
    rendered = "\n".join(m.content for m in talk.build(system_prompt="s", state_text="—"))
    assert "Вы не вызвали инструмент" in rendered


def test_history_keeps_exactly_the_promised_number_verbatim():
    talk = Conversation(task="задача")
    for i in range(1, 11):
        talk.record(step(i, f"РЕЗУЛЬТАТ-{i}-" + "х" * 300))
    rendered = "\n".join(m.content for m in talk.build(system_prompt="s", state_text="—"))
    full = sum(f"РЕЗУЛЬТАТ-{i}-" + "х" * 300 in rendered for i in range(1, 11))
    assert full == KEEP_VERBATIM


@pytest.mark.parametrize("given", ["e12", "[e12]", " e12 ", "[e12] ", "[[e12]]"])
def test_ref_is_accepted_in_the_form_the_snapshot_prints_it(given: str):
    """ADR-023: 14 вызовов подряд отклонено из-за скобок, которые видит только парсер."""
    assert RefRegistry.normalize(given) == "e12"


def test_unknown_ref_error_shows_valid_ones():
    error = InvalidRef("e999", ["e1", "e2", "e3"])
    assert "e999" in error.for_model()
    assert "e1, e2, e3" in error.for_model()
