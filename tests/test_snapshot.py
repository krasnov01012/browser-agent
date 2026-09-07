"""Отрисовка состояния страницы: схлопывание, пометки изменений, шапка."""

from __future__ import annotations

from agent.browser.snapshot import Element, PageState


def el(ref: str, role: str = "button", name: str = "", **kw: object) -> Element:
    return Element(ref=ref, role=role, name=name, sig=f"{role}|DIV|0|", **kw)  # type: ignore[arg-type]


def state(elements: list[Element], url: str = "https://e.test/") -> PageState:
    return PageState(url=url, title="T", elements=elements)


def test_collapse_squashes_identical_neighbours():
    rows = state([el(f"e{i}", name="Откликнуться") for i in range(8)]).render()
    assert "× ещё 5 того же вида" in rows
    assert rows.count("Откликнуться") == 3


def test_collapse_keeps_distinct_names():
    """Одинаковая структура, разные подписи — схлопывать нельзя: выбирать не из чего."""
    rows = state([el(f"e{i}", role="link", name=f"Вакансия {i}") for i in range(8)]).render()
    for i in range(8):
        assert f"Вакансия {i}" in rows
    assert "× ещё" not in rows


def test_diff_marks_appearance_and_change():
    before = state([el("e1", name="Найти"), el("e2", role="textbox", name="Поиск")])
    after = state(
        [
            el("e1", name="Найти"),
            el("e2", role="textbox", name="Поиск", value="python"),
            el("e3", name="Очистить"),
        ]
    )
    text = after.diff(before)
    assert "Δ ~ [e2]" in text
    assert "Δ + [e3]" in text
    # Неизменившийся элемент остаётся в списке — модели нужен полный набор ref.
    assert "[e1]" in text


def test_diff_reports_disappearance():
    before = state([el("e1", name="Найти"), el("e9", name="Понятно")])
    after = state([el("e1", name="Найти")])
    text = after.diff(before)
    assert "Δ - [e9]" in text and "исчез" in text


def test_diff_on_unchanged_page_still_lists_everything():
    """ADR-024: дельта без базы бесполезна — состояние в истории не хранится."""
    page = state([el("e1", name="Найти"), el("e2", role="link", name="Дальше")])
    text = page.diff(state([el("e1", name="Найти"), el("e2", role="link", name="Дальше")]))
    assert "ничего не изменилось" in text
    assert "[e1]" in text and "[e2]" in text


def test_diff_after_navigation_is_a_full_snapshot():
    before = state([el("e1", name="Найти")], url="https://a.test/")
    after = state([el("e1", name="Далее")], url="https://b.test/")
    assert after.diff(before) == after.render()


def test_marked_element_survives_collapse():
    """Пометка на элементе внутри группы не должна пропасть вместе с ним."""
    rows = [el(f"e{i}", name="Откликнуться") for i in range(8)]
    before = state(list(rows))
    changed = [el(f"e{i}", name="Откликнуться") for i in range(8)]
    changed[5] = el("e5", name="Откликнуться", state={"disabled": True})
    text = state(changed).diff(before)
    assert "Δ ~ [e5]" in text


def test_header_shows_scroll_and_tabs():
    page = PageState(
        url="https://e.test/",
        title="Заголовок",
        elements=[el("e1", name="Кнопка")],
        scroll_y=500,
        scroll_height=2000,
        viewport=1000,
        offscreen=42,
    )
    text = page.render()
    assert "SCROLL 500 / 2000  (50%)" in text
    assert "↓ ещё ~42 элементов" in text


def test_render_of_element_shows_value_href_and_flags():
    line = Element(
        ref="e7",
        role="checkbox",
        name="Согласен",
        value="да",
        href="/next",
        state={"checked": True},
    ).render()
    assert line == '[e7] checkbox  "Согласен" = "да" → /next checked=true'


def test_fingerprint_is_stable_for_the_same_page():
    a = state([el("e1", name="Спам"), el("e2", name="Ещё")])
    b = state([el("e1", name="Спам"), el("e2", name="Ещё")])
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_notices_a_changed_label():
    before = state([el("e1", name="Ещё")])
    after = state([el("e1", name="Свернуть")])
    assert before.fingerprint() != after.fingerprint()


def test_fingerprint_notices_a_new_element():
    before = state([el("e1", name="Ещё")])
    after = state([el("e1", name="Ещё"), el("e2", name="Спам")])
    assert before.fingerprint() != after.fingerprint()


def test_fingerprint_notices_navigation():
    here = state([el("e1", name="Войти")], url="https://e.test/")
    there = state([el("e1", name="Войти")], url="https://e.test/inbox")
    assert here.fingerprint() != there.fingerprint()


def test_fingerprint_ignores_scroll_that_revealed_nothing():
    """ADR-039: прокрутка на десяток пикселей без единого нового элемента
    ничего для агента не изменила, а по scroll_y выглядела бы движением."""
    elements = [el("e1", name="Входящие")]
    before = PageState(url="https://e.test/", title="T", elements=elements, scroll_y=0)
    after = PageState(url="https://e.test/", title="T", elements=elements, scroll_y=9)
    assert before.fingerprint() == after.fingerprint()


def test_label_for_falls_back_to_the_value():
    page = state([el("e1", name=""), el("e2", name="Найти")])
    page.elements[0].value = "введённый текст"
    assert page.label_for("e1") == "введённый текст"
    assert page.label_for("e2") == "Найти"
    assert page.label_for("e404") == ""
