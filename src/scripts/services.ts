/*
 * Каталог услуг. Desktop: строка активирует общую панель справа (клик, клавиатура,
 * наведение с небольшой задержкой). Mobile: аккордеон — панель раскрывается под строкой.
 */
const desktop = matchMedia('(min-width: 1024px)');
const finePointer = matchMedia('(hover: hover) and (pointer: fine)');

export function initServices(): void {
  const root = document.querySelector<HTMLElement>('[data-services]');
  if (!root) return;
  const items = [...root.querySelectorAll<HTMLElement>('[data-svc-item]')];

  const activate = (item: HTMLElement | null, toggle = false): void => {
    for (const it of items) {
      const on = it === item && !(toggle && !desktop.matches && it.hasAttribute('data-active'));
      it.toggleAttribute('data-active', on);
      it.querySelector('[data-svc-trigger]')?.setAttribute('aria-expanded', String(on));
    }
  };

  let hoverTimer = 0;
  for (const item of items) {
    const trigger = item.querySelector<HTMLButtonElement>('[data-svc-trigger]');
    trigger?.addEventListener('click', () => activate(item, true));
    trigger?.addEventListener('pointerenter', () => {
      if (!desktop.matches || !finePointer.matches) return;
      clearTimeout(hoverTimer);
      hoverTimer = window.setTimeout(() => activate(item), 90);
    });
    trigger?.addEventListener('pointerleave', () => clearTimeout(hoverTimer));
  }

  // На desktop всегда открыта ровно одна панель.
  desktop.addEventListener('change', (e) => {
    if (e.matches && !items.some((i) => i.hasAttribute('data-active'))) activate(items[0] ?? null);
  });

  // Ссылки «#service-…» (направления в Hero) открывают нужную услугу.
  const fromHash = (hash: string): void => {
    const item = items.find((i) => `#${i.id}` === hash);
    if (item) activate(item);
  };
  document.addEventListener('click', (e) => {
    const link = (e.target as Element | null)?.closest<HTMLAnchorElement>('a[href^="#service-"]');
    if (link) fromHash(new URL(link.href).hash);
  });
  if (location.hash.startsWith('#service-')) fromHash(location.hash);
}
