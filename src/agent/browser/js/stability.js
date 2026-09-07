// Детектор покоя страницы.
//
// networkidle бесполезен на сайтах с аналитикой и поллингом — он не наступает
// никогда. Вместо него считаем мутации DOM и незавершённые запросы: страница
// «успокоилась», когда и того и другого нет заданное время.
//
// Устанавливается один раз на документ, дальше Python опрашивает состояние.

(() => {
  if (window.__agentStability) return window.__agentStability.snapshot();

  const state = {
    lastMutation: performance.now(),
    inflight: 0,
    installedAt: performance.now(),
  };

  // ── Мутации DOM ───────────────────────────────────────────────────

  const observer = new MutationObserver((records) => {
    // Изменения атрибутов у одного узла — обычно анимация или курсор.
    // Считаем покой нарушенным только при структурных правках или правках текста.
    for (const r of records) {
      if (r.type === 'childList' || r.type === 'characterData') {
        state.lastMutation = performance.now();
        return;
      }
    }
    // Массовая смена атрибутов тоже признак перерисовки.
    if (records.length > 3) state.lastMutation = performance.now();
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'hidden', 'aria-expanded', 'aria-hidden', 'disabled'],
  });

  // ── Незавершённые запросы ─────────────────────────────────────────

  const done = () => {
    state.inflight = Math.max(0, state.inflight - 1);
    state.lastMutation = performance.now();
  };

  const originalFetch = window.fetch;
  if (originalFetch) {
    window.fetch = function (...args) {
      state.inflight++;
      return originalFetch.apply(this, args).finally(done);
    };
  }

  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...args) {
    state.inflight++;
    let settled = false;
    const once = () => {
      if (settled) return;
      settled = true;
      done();
    };
    this.addEventListener('loadend', once);
    this.addEventListener('error', once);
    this.addEventListener('abort', once);
    return originalSend.apply(this, args);
  };

  state.snapshot = () => ({
    quietMs: Math.round(performance.now() - state.lastMutation),
    inflight: state.inflight,
    // Сколько документ вообще под наблюдением — чтобы отличить «тихо, потому
    // что всё загрузилось» от «тихо, потому что только что установились».
    observedMs: Math.round(performance.now() - state.installedAt),
    readyState: document.readyState,
  });

  window.__agentStability = state;
  return state.snapshot();
})();
