/*
 * Контракт приёма заявок — общий для короткой формы и Project Architect.
 * Бэкенд ещё не выбран (D23 PROPOSED); фронтенд отправляет ровно этот JSON
 * на PUBLIC_LEADS_ENDPOINT. Требования к серверу — docs/brief/06_FORMS.md.
 */
import type { Locale } from '@/i18n';

export type ReplyChannel = 'telegram' | 'email';

export interface BriefData {
  types: string[];
  other: string;
  capabilities: string[];
  capabilityNotes: string;
  stage: string;
  materials: string[];
  timing: string;
  support: string;
  notes: string;
}

export interface LeadPayload {
  kind: 'quick' | 'brief';
  locale: Locale;
  name: string;
  reply_channel: ReplyChannel;
  reply_value: string;
  description: string;
  brief?: BriefData;
  /** Несекретный контекст CTA: откуда пришёл посетитель (service_ai, seshat_case…). */
  source?: string;
  intent?: string;
  /** Версия текста согласия — сервер хранит её вместе с заявкой. */
  consent_version: string;
  /** Один ключ на заполнение формы: повторная отправка не создаёт дубль. */
  idempotency_key: string;
  /** Сигналы для серверной антиспам-оценки; клиент сам ничего не блокирует. */
  client: { elapsed_ms: number; hp: string };
}

export type SubmitResult =
  | { status: 'accepted'; id?: string }
  | { status: 'not_configured' }
  | { status: 'rejected'; fields?: string[] }
  | { status: 'error' };

export const CONSENT_VERSION = 'draft-2026-10';

export const validators = {
  name: (v: string): boolean => v.trim().length >= 2 && v.trim().length <= 80,
  telegram: (v: string): boolean => /^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(v.trim()),
  email: (v: string): boolean => /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) && v.length <= 254,
  message: (v: string): boolean => v.trim().length >= 20 && v.length <= 5000,
};

export function normalizeTelegram(v: string): string {
  const s = v.trim();
  return s.startsWith('@') ? s : `@${s}`;
}

/**
 * Отправка. Успех показывается только после ответа сервера 2xx с accepted —
 * «принято» ≠ «доставлено администратору», и интерфейс так и говорит.
 */
export async function submitLead(payload: LeadPayload, endpoint: string | undefined): Promise<SubmitResult> {
  if (!endpoint) return { status: 'not_configured' };
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': payload.idempotency_key },
      body: JSON.stringify(payload),
      credentials: 'omit',
    });
    if (res.status === 422) {
      const body = (await res.json().catch(() => ({}))) as { fields?: string[] };
      return { status: 'rejected', fields: body.fields };
    }
    if (!res.ok) return { status: 'error' };
    const body = (await res.json().catch(() => ({}))) as { accepted?: boolean; id?: string };
    return body.accepted ? { status: 'accepted', id: body.id } : { status: 'error' };
  } catch {
    return { status: 'error' };
  }
}
