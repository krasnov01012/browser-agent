/*
 * Проверка «влезают ли слова»: ищет текстовые узлы, вылезающие за ширину экрана.
 * body { overflow-x: clip } прячет такое переполнение от scrollWidth, поэтому меряем
 * сами строки (Range.getBoundingClientRect). Ширины — самые узкие телефоны и планшет.
 *   node scripts/qa-text-fit.mjs
 */
import { createRequire } from 'node:module';
import { serveDist } from './serve-dist.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const port = 4391;
const server = await serveDist(port);
const pages = ['/ru/', '/en/', '/ru/work/seshat/', '/en/work/seshat/', '/ru/work/mark/', '/en/work/mark/', '/ru/privacy/'];
const widths = [320, 360, 390, 768, 1024, 1280, 1440];
const browser = await chromium.launch();
let problems = 0;
try {
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height: 800 }, reducedMotion: 'reduce' });
    for (const path of pages) {
      await page.goto(`http://localhost:${port}${path}`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      const bad = await page.evaluate(() => {
        const out = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const vw = document.documentElement.clientWidth;
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (!node.textContent.trim()) continue;
          const el = node.parentElement;
          if (!el || el.closest('[aria-hidden="true"], .visually-hidden, .site-footer__mark, [hidden], svg')) continue;
          const style = getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden') continue;
          const r = document.createRange();
          r.selectNodeContents(node);
          for (const rect of r.getClientRects()) {
            if (rect.width && (rect.right > vw + 1 || rect.left < -1)) {
              out.push(`${node.textContent.trim().slice(0, 40)} → ${Math.round(rect.right - vw)}px`);
              break;
            }
          }
        }
        return out;
      });
      if (bad.length) {
        problems += bad.length;
        console.log(`✗ ${width} ${path}\n   ${bad.join('\n   ')}`);
      }
    }
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
console.log(problems ? `${problems} overflowing text nodes` : '✓ all text fits at ' + widths.join('/'));
process.exit(problems ? 1 : 0);
