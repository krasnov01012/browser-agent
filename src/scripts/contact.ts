/*
 * Формы заявки (короткая и бриф): переключение канала, валидация с доступными
 * ошибками, контекст CTA, идемпотентная отправка, честные состояния результата.
 */
import { CONSENT_VERSION, normalizeTelegram, submitLead, validators, type BriefData, type LeadPayload, type ReplyChannel } from '@/lib/leads';
import { clearLeadContext, readLeadContext, type LeadContext } from './intent';
import type { Locale } from '@/i18n';

interface FormMessages {
  success: string;
  telegramNote: string;
  error: string;
  notConfigured: string;
  summary: string;
}

/** Хук для мастера брифа: он отдаёт свои данные в момент отправки. */
export type BriefProvider = () => BriefData;
const briefProviders = new WeakMap<HTMLFormElement, BriefProvider>();
export function registerBrief(form: HTMLFormElement, provider: BriefProvider): void {
  briefProviders.set(form, provider);
}

export function initContactForms(): void {
  const section = document.querySelector<HTMLElement>('#contact');
  const endpoint = section?.dataset.endpoint || undefined;
  const locale = (section?.dataset.locale ?? document.documentElement.lang) as Locale;
  const messages = JSON.parse(section?.querySelector<HTMLScriptElement>('[data-form-messages]')?.textContent ?? '{}') as FormMessages;

  document.querySelectorAll<HTMLFormElement>('form[data-contact-form]').forEach((form) => {
    const kind = form.dataset.contactForm === 'brief' ? 'brief' : 'quick';
    const fields = form.querySelector<HTMLElement>('[data-lead-fields]');
    if (!fields) return;

    const contactInput = fields.querySelector<HTMLInputElement>('[name="reply_value"]')!;
    const contactLabel = fields.querySelector<HTMLElement>('[data-contact-label]')!;
    const contactError = fields.querySelector<HTMLElement>('[data-error-for="reply_value"]')!;
    const status = fields.querySelector<HTMLElement>('[data-form-status]')!;
    const submit = fields.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const submitLabel = submit.querySelector<HTMLElement>('[data-submit-label]')!;
    let startedAt = 0;
    let idempotencyKey = crypto.randomUUID();
    let context: LeadContext | null = readLeadContext();

    const channel = (): ReplyChannel =>
      (form.querySelector<HTMLInputElement>('[name="reply_channel"]:checked')?.value as ReplyChannel) ?? 'telegram';

    const syncChannel = (): void => {
      const ch = channel();
      contactLabel.textContent = contactLabel.dataset[ch] ?? '';
      contactInput.placeholder = contactInput.dataset[ch === 'email' ? 'placeholderEmail' : 'placeholderTelegram'] ?? '';
      contactInput.type = ch === 'email' ? 'email' : 'text';
      contactInput.autocomplete = ch === 'email' ? 'email' : 'off';
      contactInput.inputMode = ch === 'email' ? 'email' : 'text';
      if (contactInput.getAttribute('aria-invalid') === 'true') validateField('reply_value');
    };
    form.querySelectorAll('[name="reply_channel"]').forEach((r) => r.addEventListener('change', syncChannel));

    // — Контекст CTA (услуга/кейс) —
    const contextBox = fields.querySelector<HTMLElement>('[data-context]')!;
    const renderContext = (): void => {
      contextBox.hidden = !context?.label;
      const label = contextBox.querySelector<HTMLElement>('[data-context-label]');
      if (label) label.textContent = context?.label ?? '';
    };
    contextBox.querySelector('[data-context-clear]')?.addEventListener('click', () => {
      context = null;
      clearLeadContext();
      renderContext();
    });
    addEventListener('lead-context', (e) => {
      context = (e as CustomEvent<LeadContext>).detail;
      renderContext();
    });
    renderContext();

    // — Валидация —
    const errorFor = (name: string): HTMLElement | null => fields.querySelector(`[data-error-for="${name}"]`);
    const inputFor = (name: string): HTMLInputElement | HTMLTextAreaElement | null => form.querySelector(`[name="${name}"]`);

    const validateField = (name: string): boolean => {
      const input = inputFor(name);
      const err = errorFor(name);
      if (!input || !err) return true;
      let ok = true;
      let msg = err.dataset.msg ?? '';
      if (name === 'name') ok = validators.name(input.value);
      if (name === 'description') ok = validators.message(input.value);
      if (name === 'consent') ok = (input as HTMLInputElement).checked;
      if (name === 'reply_value') {
        const ch = channel();
        ok = ch === 'email' ? validators.email(input.value) : validators.telegram(input.value);
        msg = (ch === 'email' ? contactError.dataset.msgEmail : contactError.dataset.msgTelegram) ?? '';
      }
      input.setAttribute('aria-invalid', String(!ok));
      err.textContent = ok ? '' : msg;
      return ok;
    };

    const names = ['name', 'reply_value', ...(kind === 'quick' ? ['description'] : []), 'consent'];
    for (const name of names) {
      const input = inputFor(name);
      input?.addEventListener('blur', () => input.value && validateField(name));
      input?.addEventListener('input', () => input.getAttribute('aria-invalid') === 'true' && validateField(name));
      input?.addEventListener('change', () => name === 'consent' && validateField(name));
    }
    form.addEventListener('input', () => {
      if (!startedAt) startedAt = performance.now();
    }, { once: true });

    const setStatus = (tone: 'success' | 'warn' | 'error' | '', text: string, extra = ''): void => {
      status.dataset.tone = tone;
      status.replaceChildren();
      if (!text) return;
      const p = document.createElement('p');
      p.textContent = text;
      status.append(p);
      if (extra) {
        const small = document.createElement('p');
        small.className = 'label';
        small.textContent = extra;
        status.append(small);
      }
    };

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (submit.disabled) return;
      const results = names.map(validateField);
      if (results.includes(false)) {
        setStatus('error', messages.summary);
        form.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
        return;
      }

      const brief = briefProviders.get(form)?.();
      const description = (inputFor('description')?.value ?? '').trim();
      const ch = channel();
      const payload: LeadPayload = {
        kind,
        locale,
        name: inputFor('name')!.value.trim(),
        reply_channel: ch,
        reply_value: ch === 'telegram' ? normalizeTelegram(contactInput.value) : contactInput.value.trim(),
        description,
        brief,
        source: context?.source,
        intent: context?.intent,
        consent_version: CONSENT_VERSION,
        idempotency_key: idempotencyKey,
        client: { elapsed_ms: startedAt ? Math.round(performance.now() - startedAt) : 0, hp: inputFor('website')?.value ?? '' },
      };

      submit.disabled = true;
      submitLabel.textContent = submit.dataset.labelBusy ?? '';
      setStatus('', '');
      const result = await submitLead(payload, endpoint);
      submit.disabled = false;
      submitLabel.textContent = submit.dataset.label ?? '';

      if (result.status === 'accepted') {
        setStatus('success', messages.success, ch === 'telegram' ? messages.telegramNote : '');
        form.reset();
        syncChannel();
        idempotencyKey = crypto.randomUUID();
        context = null;
        clearLeadContext();
        renderContext();
        form.dispatchEvent(new CustomEvent('lead-accepted'));
      } else if (result.status === 'not_configured') {
        setStatus('warn', messages.notConfigured);
      } else if (result.status === 'rejected') {
        (result.fields ?? []).forEach((f) => inputFor(f)?.setAttribute('aria-invalid', 'true'));
        setStatus('error', messages.summary);
      } else {
        // Ключ идемпотентности сохраняется: повтор не создаст вторую заявку.
        setStatus('error', messages.error);
      }
    });

    syncChannel();
  });
}
