/*
 * Визуальная проверка: скриншоты страниц на контрольных ширинах + горизонтальное
 * переполнение + ошибки консоли. Требует собранный dist/ (npm run build).
 *
 *   node scripts/qa-screenshots.mjs                 # все страницы, 1440/1280/768/390
 *   node scripts/qa-screenshots.mjs /ru/ 1440       # одна страница, одна ширина
 *   QA_REDUCED=1 node scripts/qa-screenshots.mjs    # с prefers-reduced-motion
 *
 * Результаты — в qa/ (не коммитится).
 */
import { createRequire } from 'node:module';
import { serveDist } from './serve-dist.mjs';
import { mkdirSync } from 'node:fs';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const [, , onlyPath, onlyWidth] = process.argv;
const pages = onlyPath ? [onlyPath] : ['/ru/', '/en/', '/ru/work/seshat/', '/en/work/seshat/', '/ru/work/mark/', '/en/work/mark/'];
const widths = onlyWidth ? [Number(onlyWidth)] : [1440, 1280, 768, 390];
const heights = { 1440: 900, 1280: 800, 768: 1024, 390: 844, 360: 780 };
const reduced = process.env.QA_REDUCED === '1';
const port = 4399;

mkdirSync('qa', { recursive: true });
const server = await serveDist(port);

const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const report = [];
try {
  for (const path of pages) {
    for (const width of widths) {
      const ctx = await browser.newContext({
        viewport: { width, height: heights[width] ?? 900 },
        deviceScaleFactor: 1,
        reducedMotion: reduced ? 'reduce' : 'no-preference',
      });
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
      await page.goto(`http://localhost:${port}${path}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(Number(process.env.QA_WAIT ?? 8000));
      const name = `${path.replaceAll('/', '_').replace(/^_|_$/g, '') || 'root'}-${width}${reduced ? '-rm' : ''}`;
      await page.screenshot({ path: `qa/${name}-fold.png` });
      // Страница целиком — кадрами по высоте экрана: fullPage у Chromium ломается на высоте > 8k px,
      // а покадровая прокрутка заодно запускает появления так, как их видит человек.
      const total = await page.evaluate(() => document.documentElement.scrollHeight);
      const vh = heights[width] ?? 900;
      let part = 0;
      for (let y = 0; y < total; y += vh) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.waitForTimeout(900);
        await page.screenshot({ path: `qa/${name}-p${String(part++).padStart(2, '0')}.png` });
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      const kState = await page.evaluate(() => document.querySelector('[data-k-stage]')?.getAttribute('data-state') ?? null);
      report.push({ path, width, overflow, kState, errors });
      await ctx.close();
    }
  }
} finally {
  await browser.close();
  server.close();
}
console.table(report.map((r) => ({ ...r, errors: r.errors.join(' | ').slice(0, 120) })));
