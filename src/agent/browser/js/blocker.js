// Кто перекрывает элемент, по которому не удался клик.
//
// Возвращает описание перекрывающего узла и список интерактивных элементов
// внутри него — с теми подписями, которые видит человек. Что из этого нажать,
// решает агент: списка «кнопок закрытия» здесь нет и быть не может, иначе это
// превратится в подсказку по элементам (docs/CONSTRAINTS.md §2.3).
(el, opts) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || hit === el || el.contains(hit)) return null;

    const reg = window.__agentRegistry;
    const refOf = (n) => {
        if (!reg) return '';
        const ref = reg.byEl.get(n);
        return ref && reg.byRef.get(ref) === n ? ref : '';
    };
    const labelOf = (n) => (n.getAttribute('aria-label') || n.textContent || '')
        .replace(/\s+/g, ' ').trim();

    // Сам перекрывающий узел обычно не интерактивен и своего ref не имеет —
    // ищем ближайшего предка, который агент сможет назвать.
    let ref = '';
    let node = hit;
    for (let i = 0; node && i < opts.depth; i++, node = node.parentElement) {
        ref = refOf(node);
        if (ref) break;
    }

    // Управление внутри перекрывающего блока — то же перечисление generic-ролей,
    // что и в обходчике страницы, без единого признака конкретного сайта.
    const controls = [];
    for (const c of hit.querySelectorAll('a, button, input, select, textarea, [role], [tabindex]')) {
        const candidate = refOf(c);
        if (!candidate) continue;
        controls.push({ ref: candidate, label: labelOf(c).slice(0, 40) });
        if (controls.length >= opts.maxControls) break;
    }

    return { tag: hit.tagName.toLowerCase(), label: labelOf(hit).slice(0, 80), ref, controls };
}
