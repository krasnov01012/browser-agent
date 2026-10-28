// @ts-check
import { defineConfig } from 'astro/config';

// Домен ещё не выбран (docs/OPEN_QUESTIONS.md). SITE_URL задаётся при сборке —
// от него зависят canonical, hreflang и og:url.
const site = process.env.SITE_URL ?? 'https://krasnoff.example';

export default defineConfig({
  site,
  trailingSlash: 'always',
  build: { format: 'directory', inlineStylesheets: 'auto' },
  prefetch: { prefetchAll: false, defaultStrategy: 'hover' },
  devToolbar: { enabled: false },
  vite: {
    build: { assetsInlineLimit: 2048 },
  },
});
