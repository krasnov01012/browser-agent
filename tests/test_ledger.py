"""Реестр совершённых действий — счётчик, переживающий компакцию истории."""

from __future__ import annotations

from agent.core.ledger import MAX_LINES, Ledger


def test_nothing_done_says_nothing():
    assert Ledger().notice() == ""


def test_repeats_are_counted():
    """ADR-039: ровно тот вопрос, на который агент не смог ответить сам —
    сколько откликов он уже отправил."""
    ledger = Ledger()
    for _ in range(3):
        ledger.add("button «Откликнуться»")
    notice = ledger.notice()
    assert "«button «Откликнуться»» ×3" in notice
    assert len(ledger) == 3


def test_different_actions_are_kept_apart():
    ledger = Ledger()
    ledger.add("button «Отправить»")
    ledger.add("button «Отправить»")
    ledger.add("link «Вакансии»")
    notice = ledger.notice()
    assert "«button «Отправить»» ×2" in notice
    assert "«link «Вакансии»» ×1" in notice


def test_the_list_does_not_grow_without_bound():
    """Реестр идёт в контекст каждый шаг — расти ему нельзя."""
    ledger = Ledger()
    for i in range(MAX_LINES + 5):
        ledger.add(f"кнопка {i}")
    notice = ledger.notice()
    assert "и ещё 5 других" in notice


def test_the_most_frequent_survive_the_cut():
    """Отсечка по частоте, а не по свежести: реестр отвечает «сколько раз»."""
    ledger = Ledger()
    for i in range(MAX_LINES + 3):
        ledger.add(f"разовый клик {i}")
    for _ in range(4):
        ledger.add("button «Удалить навсегда»")
    assert "«button «Удалить навсегда»» ×4" in ledger.notice()


def test_blank_labels_are_ignored():
    ledger = Ledger()
    ledger.add("")
    ledger.add("   ")
    assert ledger.notice() == ""
