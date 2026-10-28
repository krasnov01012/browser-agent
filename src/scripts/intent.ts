/*
 * Контекст обращения: CTA из услуги или кейса передаёт в общую форму
 * только несекретный источник (source / intent), без персональных данных.
 */
export interface LeadContext {
  source: string;
  intent: string;
  label: string;
}

const KEY = 'krasnoff:lead-context';

export function setLeadContext(ctx: LeadContext): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(ctx));
  } catch {
    /* приватный режим — контекст просто не сохранится */
  }
  dispatchEvent(new CustomEvent<LeadContext>('lead-context', { detail: ctx }));
}

export function readLeadContext(): LeadContext | null {
  const params = new URLSearchParams(location.search);
  const source = params.get('source');
  if (source && /^[a-z0-9_]{2,40}$/.test(source)) {
    const intent = params.get('intent') ?? 'project';
    return { source, intent: /^[a-z0-9_]{2,40}$/.test(intent) ? intent : 'project', label: params.get('label')?.slice(0, 80) ?? source };
  }
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LeadContext) : null;
  } catch {
    return null;
  }
}

export function clearLeadContext(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* noop */
  }
}

/** Любой элемент с data-intent-source при клике назначает контекст формы. */
export function initIntents(): void {
  document.addEventListener('click', (event) => {
    const el = (event.target as Element | null)?.closest<HTMLElement>('[data-intent-source]');
    if (!el) return;
    setLeadContext({
      source: el.dataset.intentSource ?? 'site',
      intent: el.dataset.intent ?? 'project',
      label: el.dataset.intentLabel ?? '',
    });
  });
}
