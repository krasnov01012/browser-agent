"""Привязка аргументов, тексты ошибок и отчёт о клике по переключателю."""

from __future__ import annotations

import pytest

from agent.tools.errors import BadArguments, Covered, UnknownTool
from agent.tools.interaction import _toggle_report
from agent.tools.registry import ToolRegistry, make_tool, p_str


@make_tool(
    "sample",
    "тестовый",
    properties={"ref": p_str("ref"), "text": p_str("text")},
    required=["ref"],
)
async def sample(ctx: object, ref: str, text: str = "по умолчанию") -> None:  # pragma: no cover
    raise AssertionError("тело не вызывается — проверяется только привязка")


def bind(arguments: dict) -> dict:
    from agent.tools.registry import _bind

    return _bind(sample, arguments)


def test_extra_arguments_are_dropped_silently():
    """Модели любят добавлять поясняющие поля — падать из-за них расточительно."""
    assert bind({"ref": "e1", "почему": "так надо"}) == {"ref": "e1"}


def test_missing_required_argument_is_an_error():
    with pytest.raises(BadArguments) as e:
        bind({"text": "привет"})
    assert "ref" in e.value.for_model()


def test_null_in_an_optional_argument_is_treated_as_absence():
    """ADR: шесть шагов order_form ушло на scroll(ref="null")."""
    assert bind({"ref": "e1", "text": "null"}) == {"ref": "e1"}
    assert bind({"ref": "e1", "text": "None"}) == {"ref": "e1"}


def test_null_in_a_required_argument_is_kept_as_text():
    assert bind({"ref": "null"}) == {"ref": "null"}


def test_registry_rejects_duplicates():
    registry = ToolRegistry()
    registry.register(sample)
    with pytest.raises(ValueError):
        registry.register(sample)


def test_unknown_tool_lists_what_exists():
    registry = ToolRegistry()
    registry.register(sample)
    with pytest.raises(UnknownTool) as e:
        registry.get("клик")
    assert "sample" in e.value.for_model()


def test_covered_error_says_that_neighbours_will_not_help():
    text = Covered("e22", "<div> «Куки» (ref e91)").for_model()
    assert "e22" in text and "e91" in text
    assert "перебирать другие ref" in text


def test_checkbox_click_reports_the_new_state():
    text = _toggle_report(
        "e7",
        {"on": False, "kind": "checkbox", "label": "Бекон"},
        {"on": True, "kind": "checkbox", "label": "Бекон"},
    )
    assert "«Бекон»" in text and "отмечен" in text


def test_click_that_changed_nothing_says_so():
    """ADR-022: пять кликов по «Бекону» подряд и ни одного слова об этом."""
    same = {"on": True, "kind": "checkbox", "label": "Бекон"}
    text = _toggle_report("e7", same, same)
    assert "ничего не изменилось" in text
    assert "повторный клик снимет отметку" in text


def test_radio_is_not_advised_to_be_clicked_again():
    same = {"on": True, "kind": "radio", "label": "Большая"}
    text = _toggle_report("e5", same, same)
    assert "повторные клики ничего не дадут" in text


def test_click_on_a_plain_element_stays_terse():
    assert _toggle_report("e13", None, None) == "Клик по e13"
