/*
 * Доступные вкладки (WAI-ARIA Tabs): клик, стрелки/Home/End, ручная активация.
 * Вкладка с data-hash открывается по якорю (#architect) и по ссылкам на него.
 */
export function initTabs(): void {
  document.querySelectorAll<HTMLElement>('[data-tabs]').forEach((root) => {
    const tabs = [...root.querySelectorAll<HTMLButtonElement>('[role="tab"]')].filter((t) => t.closest('[data-tabs]') === root);

    const select = (tab: HTMLButtonElement, focus = false): void => {
      for (const t of tabs) {
        const on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        const panel = document.getElementById(t.getAttribute('aria-controls') ?? '');
        if (panel) panel.hidden = !on;
      }
      if (focus) tab.focus();
      root.dispatchEvent(new CustomEvent('tabchange', { detail: tab.dataset.tab }));
    };

    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', (e) => {
        const keys: Record<string, number> = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1 };
        if (!(e.key in keys)) return;
        e.preventDefault();
        const next = tabs[(keys[e.key]! + tabs.length) % tabs.length];
        if (next) select(next, true);
      });
    });

    const byHash = (hash: string): void => {
      const tab = tabs.find((t) => t.dataset.hash && `#${t.dataset.hash}` === hash);
      if (tab) select(tab);
    };
    if (location.hash) byHash(location.hash);
    addEventListener('hashchange', () => byHash(location.hash));
    document.addEventListener('click', (e) => {
      const a = (e.target as Element | null)?.closest<HTMLAnchorElement>('a[href*="#"]');
      if (a) byHash(new URL(a.href).hash);
    });
    // Обычные CTA «Обсудить проект» ведут к короткой заявке.
    document.addEventListener('click', (e) => {
      const a = (e.target as Element | null)?.closest<HTMLAnchorElement>('a[href$="#contact"]');
      if (a && tabs[0]) select(tabs[0]);
    });
  });
}
