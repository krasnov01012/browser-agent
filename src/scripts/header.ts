/** Шапка: подложка после прокрутки, скрытие при движении вниз, мобильное меню, активный пункт. */
export function initHeader(): void {
  const header = document.querySelector<HTMLElement>('[data-header]');
  if (!header) return;

  let lastY = scrollY;
  const onScroll = (): void => {
    const y = scrollY;
    header.classList.toggle('is-scrolled', y > 24);
    if (Math.abs(y - lastY) > 6) {
      header.classList.toggle('is-hidden', y > lastY && y > window.innerHeight * 0.6);
      lastY = y;
    }
  };
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // — Мобильное меню —
  const toggle = header.querySelector<HTMLButtonElement>('[data-menu-toggle]');
  const menu = header.querySelector<HTMLElement>('[data-menu]');
  const main = document.getElementById('main');
  const footer = document.querySelector<HTMLElement>('.site-footer');

  const setOpen = (open: boolean, restoreFocus = true): void => {
    if (!toggle || !menu) return;
    menu.hidden = !open;
    header.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', (open ? toggle.dataset.labelClose : toggle.dataset.labelOpen) ?? '');
    document.documentElement.style.overflow = open ? 'hidden' : '';
    // Фон недоступен для фокуса и скринридеров, пока меню открыто.
    for (const el of [main, footer]) el?.toggleAttribute('inert', open);
    if (open) menu.querySelector<HTMLElement>('a')?.focus();
    else if (restoreFocus) toggle.focus();
  };

  toggle?.addEventListener('click', () => setOpen(menu ? menu.hidden === true : true));
  menu?.addEventListener('click', (e) => {
    if ((e.target as Element).closest('[data-menu-link]')) setOpen(false, false);
  });
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menu && !menu.hidden) setOpen(false);
  });
  matchMedia('(min-width: 1024px)').addEventListener('change', (e) => {
    if (e.matches && menu && !menu.hidden) setOpen(false, false);
  });

  // — Активный пункт навигации по видимой секции —
  const links = [...header.querySelectorAll<HTMLAnchorElement>('.site-nav__link')];
  const targets = links
    .map((a) => ({ a, el: document.getElementById(new URL(a.href).hash.slice(1)) }))
    .filter((x): x is { a: HTMLAnchorElement; el: HTMLElement } => !!x.el && new URL(x.a.href).pathname === location.pathname);
  if (!targets.length) return;
  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const hit = targets.find((x) => x.el === entry.target);
        hit?.a.classList.toggle('is-active', entry.isIntersecting);
      }
    },
    { rootMargin: '-45% 0px -50% 0px' },
  );
  for (const { el } of targets) io.observe(el);
}
