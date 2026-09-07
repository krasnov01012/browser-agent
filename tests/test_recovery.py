"""Детектор зацикливания и подсказки при сериях ошибок."""

from __future__ import annotations

from agent.core.recovery import (
    BLOCKED_THRESHOLD,
    ERROR_STREAK_THRESHOLD,
    LOOP_THRESHOLD,
    LOOP_WINDOW,
    SAME_TOOL_THRESHOLD,
    STALE_STATE_THRESHOLD,
    Recovery,
    budget_notice,
    plural,
    signature,
)


def click(ref: str) -> tuple[str, dict]:
    return "click", {"ref": ref}


def test_two_repeats_are_not_a_loop():
    r = Recovery()
    for _ in range(2):
        r.observe(*click("e5"), failed=False)
    assert r.notice() == ""


def test_three_repeats_in_a_row_are():
    r = Recovery()
    for _ in range(3):
        r.observe(*click("e5"), failed=False)
    assert "ВНИМАНИЕ" in r.notice()


def test_alternating_cycle_is_caught():
    """ADR-025: «клик → Escape → тот же клик» — самый дорогой вид зацикливания.

    Подряд одинаковых действий здесь нет ни разу, а прогон vacancies потерял
    на такой карусели 19 шагов из 40.
    """
    r = Recovery()
    r.observe(*click("e152"), failed=False)
    r.observe("press_key", {"key": "Escape"}, failed=False)
    r.observe(*click("e152"), failed=False)
    r.observe("press_key", {"key": "Escape"}, failed=False)
    assert r.notice() == ""
    r.observe(*click("e152"), failed=False)
    assert "ВНИМАНИЕ" in r.notice()


def test_repeats_outside_the_window_are_forgotten():
    r = Recovery()
    r.observe(*click("e1"), failed=False)
    r.observe(*click("e1"), failed=False)
    for ref in range(LOOP_WINDOW):
        r.observe(*click(f"x{ref}"), failed=False)
    r.observe(*click("e1"), failed=False)
    assert r.notice() == ""


def test_long_carousel_is_caught():
    """ADR-032: возвраты к одной панели на шагах 5, 8 и 12 — тоже цикл.

    Между возвратами агент успевает потыкать в содержимое панели, поэтому
    в окно из шести шагов три повтора не укладываются. Прогон `vacancies`
    потерял на этом двадцать шагов, а детектор промолчал.
    """
    r = Recovery()
    r.observe(*click("e31"), failed=False)
    r.observe(*click("e26"), failed=True)
    r.observe("press_key", {"key": "Escape"}, failed=False)
    r.observe(*click("e31"), failed=False)
    r.observe(*click("e97"), failed=False)
    r.observe(*click("e90"), failed=True)
    r.observe("press_key", {"key": "Escape"}, failed=False)
    assert "ходите по кругу" not in r.notice()
    r.observe(*click("e31"), failed=False)
    assert "ВНИМАНИЕ" in r.notice()


def test_the_same_loop_is_not_flagged_every_step():
    r = Recovery()
    for _ in range(LOOP_THRESHOLD):
        r.observe(*click("e5"), failed=False)
    assert "ВНИМАНИЕ" in r.notice()
    r.observe(*click("e5"), failed=False)
    assert r.notice() == ""


def test_an_ignored_loop_is_flagged_again():
    """ADR-034: подсказка, сказанная один раз за прогон, молчит именно тогда,
    когда её проигнорировали.

    Прогон `vacancies` отработал детектором на третьем `scroll down` и умолк.
    Агент открутил ещё девять таких же шагов до конца бюджета — детектор
    не окликнул его ни разу.
    """
    r = Recovery()
    for _ in range(LOOP_THRESHOLD):
        r.observe("scroll", {"direction": "down"}, failed=False)
    assert "ВНИМАНИЕ" in r.notice()

    for _ in range(LOOP_THRESHOLD - 1):
        r.observe("scroll", {"direction": "down"}, failed=False)
        assert r.notice() == ""

    r.observe("scroll", {"direction": "down"}, failed=False)
    assert "ВНИМАНИЕ" in r.notice()


def test_rewording_the_same_search_is_caught():
    """ADR-039: перебор формулировок по подписи неотличим от разных действий.

    В прогоне с Gmail агент подряд искал «Спам», «спам», «Spam», «СПАМ» —
    подписи все разные, детектор циклов молчал, а страница не менялась ни разу.
    """
    r = Recovery()
    for query in ("Спам", "спам", "Spam", "СПАМ"):
        r.observe("find_in_page", {"query": query}, failed=False, changed=False)
    notice = r.notice()
    assert "find_in_page" in notice
    assert "Перебор формулировок" in notice


def test_productive_calls_of_one_tool_are_normal_work():
    """Десять кликов подряд по разным кнопкам — это работа, а не буксование."""
    r = Recovery()
    for i in range(SAME_TOOL_THRESHOLD + 3):
        r.observe(*click(f"e{i}"), failed=False, changed=True)
    assert r.notice() == ""


def test_rewording_notice_is_repeated_if_ignored():
    r = Recovery()
    for i in range(SAME_TOOL_THRESHOLD):
        r.observe("find_in_page", {"query": f"q{i}"}, failed=False, changed=False)
    assert "Перебор формулировок" in r.notice()

    r.observe("find_in_page", {"query": "ещё"}, failed=False, changed=False)
    assert r.notice() == ""

    for i in range(SAME_TOOL_THRESHOLD - 1):
        r.observe("find_in_page", {"query": f"z{i}"}, failed=False, changed=False)
    assert "Перебор формулировок" in r.notice()


def test_literal_repeats_are_left_to_the_loop_detector():
    """Одна беда — один абзац: два предупреждения об одном обесценивают оба."""
    r = Recovery()
    for _ in range(SAME_TOOL_THRESHOLD):
        r.observe("find_in_page", {"query": "спам"}, failed=False, changed=False)
    notice = r.notice()
    assert "ходите по кругу" in notice
    assert "Перебор формулировок" not in notice


def test_unchanging_page_is_a_dead_end():
    """Порог считает переходы, а не снимки: три шага без изменений — четыре
    одинаковых отпечатка подряд."""
    r = Recovery()
    for i in range(STALE_STATE_THRESHOLD):
        r.observe(*click(f"e{i}"), failed=False, state_key="одно и то же")
    assert r.notice() == ""

    r.observe(*click("e99"), failed=False, state_key="одно и то же")
    assert "состояние страницы не меняется" in r.notice()


def test_a_changing_page_resets_the_dead_end_counter():
    r = Recovery()
    for i in range(STALE_STATE_THRESHOLD + 1):
        r.observe(*click(f"e{i}"), failed=False, state_key="одно и то же")
    r.observe(*click("e99"), failed=False, state_key="другое")
    assert "состояние страницы не меняется" not in r.notice()


def test_dead_end_notice_is_repeated_if_ignored():
    """ADR-034 распространяется и на этот детектор: молчать после первого раза
    значит замолчать ровно тогда, когда подсказку проигнорировали."""
    r = Recovery()
    for i in range(STALE_STATE_THRESHOLD + 1):
        r.observe(*click(f"e{i}"), failed=False, state_key="замерло")
    assert "состояние страницы не меняется" in r.notice()

    r.observe(*click("e50"), failed=False, state_key="замерло")
    assert "состояние страницы не меняется" not in r.notice()

    for i in range(STALE_STATE_THRESHOLD - 1):
        r.observe(*click(f"e6{i}"), failed=False, state_key="замерло")
    assert "состояние страницы не меняется" in r.notice()


def test_error_streak_notice():
    """Действия разные — сработать должен именно счётчик ошибок, а не детектор циклов."""
    r = Recovery()
    for i in range(ERROR_STREAK_THRESHOLD - 1):
        r.observe(*click(f"e{i}"), failed=True)
    assert r.notice() == ""
    r.observe(*click("e99"), failed=True)
    assert "неудачных действий" in r.notice()


def test_success_resets_the_error_streak():
    r = Recovery()
    for i in range(ERROR_STREAK_THRESHOLD):
        r.observe(*click(f"e{i}"), failed=True)
    r.observe("goto", {"url": "https://e.test/"}, failed=False)
    assert "неудачных действий" not in r.notice()


def test_single_overlay_is_not_worth_a_word():
    """Баннер, куки, подсказка — перекрытие само по себе рядовое событие."""
    r = Recovery()
    r.observe(*click("e26"), failed=True, kind="covered")
    assert "перекрытие" not in r.notice()


def test_repeated_overlays_become_a_diagnosis():
    r = Recovery()
    for i in range(BLOCKED_THRESHOLD):
        r.observe(*click(f"e{i}"), failed=True, kind="covered")
    notice = r.notice()
    assert "перекрытие" in notice
    assert "Донастройка" in notice


def test_overlay_notice_is_said_once():
    r = Recovery()
    for i in range(BLOCKED_THRESHOLD + 3):
        r.observe(*click(f"e{i}"), failed=True, kind="covered")
        if i == BLOCKED_THRESHOLD - 1:
            assert "перекрытие" in r.notice()
    assert "перекрытие" not in r.notice()


def test_other_failures_do_not_count_as_overlays():
    r = Recovery()
    for i in range(BLOCKED_THRESHOLD):
        r.observe(*click(f"e{i}"), failed=True, kind="timeout")
    assert "перекрытие" not in r.notice()


def test_signature_ignores_key_order():
    assert signature("click", {"a": 1, "b": 2}) == signature("click", {"b": 2, "a": 1})


def test_plural_agrees_in_russian():
    assert plural(1, "шаг", "шага", "шагов") == "шаг"
    assert plural(3, "шаг", "шага", "шагов") == "шага"
    assert plural(7, "шаг", "шага", "шагов") == "шагов"
    assert plural(11, "шаг", "шага", "шагов") == "шагов"
    assert plural(21, "шаг", "шага", "шагов") == "шаг"


def test_budget_notice_appears_only_near_the_end():
    assert budget_notice(0.5, 20) == ""
    assert "БЮДЖЕТ" in budget_notice(0.9, 4)
