/** Появление элементов при входе в область видимости. Без JS и при reduced-motion всё видно сразу. */
export function initReveal(): void {
  const root = document.documentElement;
  const nodes = document.querySelectorAll<HTMLElement>('[data-reveal], [data-lines], [data-draw]');
  if (!root.classList.contains('motion') || !('IntersectionObserver' in window)) {
    nodes.forEach((n) => n.classList.add('is-in'));
    return;
  }

  // Порядковый номер внутри группы — для каскада.
  document.querySelectorAll<HTMLElement>('[data-reveal-group]').forEach((group) => {
    group.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el, i) => el.style.setProperty('--reveal-i', String(i)));
  });

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-in');
        io.unobserve(entry.target);
      }
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.01 },
  );
  nodes.forEach((n) => io.observe(n));

  // Подстраховка: если вкладка открыта на середине страницы, ничего не должно остаться скрытым.
  addEventListener('load', () => {
    nodes.forEach((n) => {
      if (n.getBoundingClientRect().bottom < 0) n.classList.add('is-in');
    });
  });
}

/** Декоративные циклы ([data-play]) работают только пока сцена в кадре — экономим CPU/батарею. */
export function initPlayback(): void {
  const nodes = document.querySelectorAll<HTMLElement>('[data-play]');
  if (!nodes.length) return;
  if (!('IntersectionObserver' in window)) {
    nodes.forEach((n) => n.classList.add('is-playing'));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) e.target.classList.toggle('is-playing', e.isIntersecting && !document.hidden);
    },
    { rootMargin: '60px' },
  );
  nodes.forEach((n) => io.observe(n));
}
