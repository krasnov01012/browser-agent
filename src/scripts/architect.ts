/*
 * Project Architect: 4 шага, свободная навигация назад/по рельсу, пропуск шагов,
 * динамические возможности по выбранному типу, редактируемая сводка.
 * Данные живут только в памяти страницы — никакого автосохранения.
 */
import type { BriefData } from '@/lib/leads';
import { registerBrief } from './contact';
import { reducedMotion } from './motion';

export function initArchitect(): void {
  const form = document.querySelector<HTMLFormElement>('[data-architect]');
  if (!form) return;

  const steps = [...form.querySelectorAll<HTMLElement>('[data-step]')];
  const railSteps = [...form.querySelectorAll<HTMLButtonElement>('[data-goto]')];
  const prev = form.querySelector<HTMLButtonElement>('[data-prev]')!;
  const next = form.querySelector<HTMLButtonElement>('[data-next]')!;
  const skip = form.querySelector<HTMLButtonElement>('[data-skip]')!;
  const counter = form.querySelector<HTMLElement>('[data-step-now]')!;
  const summary = form.querySelector<HTMLTextAreaElement>('[data-summary]')!;
  const capEmpty = form.querySelector<HTMLElement>('[data-cap-empty]')!;
  let current = 0;
  let summaryEdited = false;

  const values = (name: string): string[] =>
    [...form.querySelectorAll<HTMLInputElement>(`[name="${name}"]:checked`)].map((i) => i.dataset.label ?? i.value);
  const value = (name: string): string => values(name)[0] ?? '';
  const text = (name: string): string => (form.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${name}"]`)?.value ?? '').trim();

  const collect = (): BriefData => ({
    types: [...form.querySelectorAll<HTMLInputElement>('[name="types"]:checked')].map((i) => i.value),
    other: text('other'),
    capabilities: values('capabilities'),
    capabilityNotes: text('capabilityNotes'),
    stage: value('stage'),
    materials: values('materials'),
    timing: value('timing'),
    support: value('support'),
    notes: text('notes'),
  });

  /** Человекочитаемая сводка — её же получает сервер в поле description. */
  const compose = (): string => {
    const d = summary.dataset;
    const lines: string[] = [];
    const typeLabels = values('types');
    const push = (heading: string | undefined, v: string): void => {
      if (v) lines.push(`${heading}: ${v}`);
    };
    push(d.hType, [...typeLabels, text('other')].filter(Boolean).join(', '));
    push(d.hCapabilities, [...values('capabilities'), text('capabilityNotes')].filter(Boolean).join(', '));
    push(d.hStage, value('stage'));
    push(d.hMaterials, values('materials').join(', '));
    push(d.hTiming, value('timing'));
    push(d.hSupport, value('support'));
    push(d.hNotes, text('notes'));
    return lines.join('\n');
  };

  const syncCapabilities = (): void => {
    const types = collect().types;
    let any = false;
    form.querySelectorAll<HTMLElement>('[data-cap-group]').forEach((g) => {
      const on = types.includes(g.dataset.capGroup ?? '');
      g.hidden = !on;
      any ||= on;
    });
    capEmpty.hidden = any;
  };

  const go = (index: number, focus = true): void => {
    current = Math.max(0, Math.min(steps.length - 1, index));
    steps.forEach((s, i) => (s.hidden = i !== current));
    railSteps.forEach((b, i) => {
      if (i === current) b.setAttribute('aria-current', 'step');
      else b.removeAttribute('aria-current');
      b.toggleAttribute('data-done', i < current);
    });
    counter.textContent = String(current + 1);
    prev.hidden = current === 0;
    const last = current === steps.length - 1;
    next.hidden = last;
    skip.hidden = last;
    if (current === 1) syncCapabilities();
    if (last && !summaryEdited) summary.value = compose();
    if (last && !summary.value) summary.placeholder = summary.dataset.empty ?? '';
    if (focus) {
      const heading = steps[current]?.querySelector<HTMLElement>('legend, .arch__q');
      heading?.setAttribute('tabindex', '-1');
      heading?.focus({ preventScroll: true });
      const top = form.getBoundingClientRect().top;
      if (top < 0 || top > innerHeight * 0.5) form.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' });
    }
  };

  next.addEventListener('click', () => go(current + 1));
  skip.addEventListener('click', () => go(current + 1));
  prev.addEventListener('click', () => go(current - 1));
  railSteps.forEach((b, i) => b.addEventListener('click', () => go(i)));
  form.addEventListener('change', (e) => {
    if ((e.target as HTMLInputElement).name === 'types') syncCapabilities();
  });
  summary.addEventListener('input', () => (summaryEdited = true));
  // Enter в однострочных полях не отправляет форму раньше времени.
  form.addEventListener('keydown', (e) => {
    const target = e.target as HTMLElement;
    if (e.key === 'Enter' && target instanceof HTMLInputElement && target.type === 'text' && current < steps.length - 1) {
      e.preventDefault();
      go(current + 1);
    }
  });
  form.addEventListener('lead-accepted', () => {
    summaryEdited = false;
    go(0, false);
  });

  registerBrief(form, collect);
  go(0, false);
}
