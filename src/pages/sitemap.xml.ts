/*
 * sitemap.xml: только индексируемые страницы, у каждой — alternate-ссылки RU/EN.
 * Кейсы попадают в карту, лишь когда включён PUBLIC_INDEX_CASES=1 (факты проверены).
 */
import type { APIRoute } from 'astro';
import { locales, localizePath } from '@/i18n';

export const GET: APIRoute = ({ site }) => {
  const base = site ?? new URL('https://krasnoff.example');
  const paths = ['/', '/privacy/', '/consent/'];
  if (import.meta.env.PUBLIC_INDEX_CASES === '1') paths.push('/work/seshat/', '/work/mark/');
  const abs = (p: string, l: (typeof locales)[number]) => new URL(localizePath(p, l), base).href;

  const urls = paths.flatMap((p) =>
    locales.map((l) => {
      const alts = locales.map((a) => `    <xhtml:link rel="alternate" hreflang="${a}" href="${abs(p, a)}"/>`).join('\n');
      return `  <url>\n    <loc>${abs(p, l)}</loc>\n${alts}\n    <xhtml:link rel="alternate" hreflang="x-default" href="${abs(p, 'en')}"/>\n  </url>`;
    }),
  );
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls.join('\n')}\n</urlset>\n`;
  return new Response(xml, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
