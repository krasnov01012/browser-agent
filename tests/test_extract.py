"""Выбор между «статьёй» и всем видимым текстом, и память между сессиями."""

from __future__ import annotations

from pathlib import Path

from agent.browser.extract import _plausible, _tidy
from agent.core.memory import RECALL_LIMIT, Memory


def test_listing_page_falls_back_to_visible_text():
    """ADR-028: со страницы результатов hh.ru приходило 1447 символов из 27898."""
    assert not _plausible("а" * 1447, "б" * 27898)


def test_article_extraction_is_trusted():
    assert _plausible("а" * 194368, "б" * 106584)
    assert _plausible("а" * 2309, "б" * 4501)


def test_empty_extraction_is_never_trusted():
    assert not _plausible("", "б" * 100)


def test_short_page_without_visible_text_is_trusted():
    assert _plausible("а" * 10, "")


def test_tidy_squeezes_whitespace():
    assert _tidy("а\n\n\n\nб   в  \n") == "а\n\nб в"


def test_memory_keeps_facts_between_runs(tmp_path: Path):
    first = Memory(tmp_path)
    first.remember_all(["hh.ru просит войти перед откликом"], task="вакансии")
    first.save()

    second = Memory(tmp_path)
    assert len(second) == 1
    assert "hh.ru просит войти" in second.recall()


def test_memory_does_not_duplicate(tmp_path: Path):
    memory = Memory(tmp_path)
    memory.remember_all(["один и тот же факт"], task="а")
    memory.remember_all(["один и тот же факт"], task="б")
    assert len(memory) == 1


def test_recall_is_capped(tmp_path: Path):
    memory = Memory(tmp_path)
    memory.remember_all([f"факт {i}" for i in range(RECALL_LIMIT * 2)], task="а")
    assert memory.recall().count("— факт") == RECALL_LIMIT


def test_recall_warns_that_facts_may_be_stale(tmp_path: Path):
    memory = Memory(tmp_path)
    memory.remember_all(["кнопка отклика внизу карточки"], task="а")
    assert "проверяйте" in memory.recall()


def test_disabled_memory_stays_silent(tmp_path: Path):
    memory = Memory(tmp_path, enabled=False)
    memory.remember_all(["факт"], task="а")
    memory.save()
    assert memory.recall() == ""
    assert not (tmp_path / "facts.json").exists()


def test_broken_file_does_not_crash_the_run(tmp_path: Path):
    (tmp_path / "facts.json").write_text("{это не json", encoding="utf-8")
    assert len(Memory(tmp_path)) == 0
