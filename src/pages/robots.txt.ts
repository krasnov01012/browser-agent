/*
 * robots.txt зависит от режима сборки: пока PUBLIC_INDEXING != 1 — индексация закрыта целиком.
 * Для запуска: PUBLIC_INDEXING=1 при сборке (docs/INDEXING.md).
 */
import type { APIRoute } from 'astro';

export const GET: APIRoute = ({ site }) => {
  const open = import.meta.env.PUBLIC_INDEXING === '1';
  const body = open
    ? ['User-agent: *', 'Allow: /', '', `Sitemap: ${new URL('/sitemap.xml', site).href}`, ''].join('\n')
    : '# Предварительная сборка: индексация закрыта.\nUser-agent: *\nDisallow: /\n';
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
