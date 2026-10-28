// @ts-check
import { defineConfig } from 'astro/config';
import { execSync } from 'node:child_process';

// Домен ещё не выбран (docs/OPEN_QUESTIONS.md). SITE_URL задаётся при сборке —
// от него зависят canonical, hreflang и og:url.
const site = process.env.SITE_URL ?? 'https://krasnoff.example';

// Метка сборки для подвала: дата + короткий хеш коммита (без хеша вне git).
let commit = '';
try {
  commit = execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
} catch {
  commit = '';
}
const buildId = [new Date().toISOString().slice(0, 10), commit].filter(Boolean).join(' · ');

export default defineConfig({
  site,
  trailingSlash: 'always',
  build: { format: 'directory', inlineStylesheets: 'auto' },
  prefetch: { prefetchAll: false, defaultStrategy: 'hover' },
  devToolbar: { enabled: false },
  vite: {
    build: { assetsInlineLimit: 2048 },
    define: { 'import.meta.env.BUILD_ID': JSON.stringify(buildId) },
  },
});
