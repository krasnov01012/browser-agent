import { ru } from './ru';
import { en } from './en';

export const locales = ['ru', 'en'] as const;
export type Locale = (typeof locales)[number];

/** Язык по умолчанию для корня `/` — НЕ РЕШЁН (docs/OPEN_QUESTIONS.md), пока ru. */
export const defaultLocale: Locale = 'ru';

const dictionaries = { ru, en } as const;

export function t(locale: Locale) {
  return dictionaries[locale];
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (locales as readonly string[]).includes(value);
}

/** Путь страницы без префикса языка: '/work/seshat/' → '/ru/work/seshat/'. */
export function localizePath(path: string, locale: Locale): string {
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `/${locale}${clean === '/' ? '/' : clean}`;
}

/** Убирает префикс языка: '/en/work/mark/' → '/work/mark/'. */
export function stripLocale(pathname: string): string {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length && isLocale(parts[0])) parts.shift();
  return `/${parts.join('/')}${parts.length ? '/' : ''}`;
}

export function otherLocale(locale: Locale): Locale {
  return locale === 'ru' ? 'en' : 'ru';
}

export const localeMeta: Record<Locale, { htmlLang: string; ogLocale: string; label: string }> = {
  ru: { htmlLang: 'ru', ogLocale: 'ru_RU', label: 'Русский' },
  en: { htmlLang: 'en', ogLocale: 'en_US', label: 'English' },
};

export type Dict = typeof ru;
