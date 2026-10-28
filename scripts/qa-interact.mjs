/*
 * Проверка интерактива в реальном браузере: меню, каталог услуг, вкладки, форма,
 * мастер брифа, конвейер MARK, переключатель языка. Требует dist/ (npm run build).
 *   node scripts/qa-interact.mjs
 */
import { createRequire } from 'node:module';
import { serveDist } from './serve-dist.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const port = 4398;
const server = await serveDist(port);
const base = `http://localhost:${port}`;
const results = [];
const check = (name, ok, info = '') => results.push({ check: name, ok: ok ? 'PASS' : 'FAIL', info });

const browser = await chromium.launch();
try {
  // — Desktop —
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`${base}/ru/`, { waitUntil: 'networkidle' });

  await page.click('#service-ai [data-svc-trigger]');
  await page.waitForTimeout(500);
  check('services: click activates panel', await page.locator('#service-ai').evaluate((el) => el.hasAttribute('data-active')));
  check('services: aria-expanded', (await page.getAttribute('#service-ai [data-svc-trigger]', 'aria-expanded')) === 'true');

  await page.click('#service-ai .svc__cta');
  await page.waitForTimeout(1600);
  check('service CTA passes context to form', await page.locator('#panel-quick [data-context]').isVisible(), await page.locator('#panel-quick [data-context-label]').innerText());

  await page.click('#panel-quick button[type="submit"]');
  await page.waitForTimeout(200);
  const invalid = await page.locator('#panel-quick [aria-invalid="true"]').count();
  check('form: empty submit shows errors', invalid >= 3, `${invalid} invalid fields`);

  await page.fill('#quick-name', 'Тест');
  await page.fill('#quick-contact', '@test_user');
  await page.fill('#quick-message', 'Нужна CRM для небольшого интернет-магазина с интеграцией склада.');
  await page.check('#panel-quick input[name="consent"]', { force: true });
  await page.click('#panel-quick button[type="submit"]');
  await page.waitForTimeout(400);
  const tone = await page.getAttribute('#panel-quick [data-form-status]', 'data-tone');
  check('form: without endpoint shows honest "not connected"', tone === 'warn', tone ?? 'none');

  await page.click('#panel-quick label:has(input[value="email"])');
  await page.fill('#quick-contact', 'not-an-email');
  await page.click('#panel-quick button[type="submit"]');
  await page.waitForTimeout(200);
  check('form: email channel validates email', (await page.getAttribute('#quick-contact', 'aria-invalid')) === 'true');

  // Мастер брифа
  await page.click('#tab-brief');
  check('intake: brief tab opens', await page.locator('#panel-brief').isVisible());
  await page.click('[data-architect] .chip:has(input[value="ai"])');
  await page.click('[data-architect] [data-next]');
  check('architect: capabilities for AI visible', await page.locator('[data-cap-group="ai"]').isVisible());
  await page.click('[data-cap-group="ai"] .chip >> nth=0');
  await page.click('[data-architect] [data-next]');
  await page.click('[data-architect] .chip:has(input[name="stage"]) >> nth=0');
  await page.click('[data-architect] [data-next]');
  const summary = await page.inputValue('[data-summary]');
  check('architect: summary composed from choices', summary.includes('AI') && summary.split('\n').length >= 3, summary.replaceAll('\n', ' | '));
  check('architect: no price fields anywhere', (await page.locator('text=/бюджет|budget|₽|\\$/i').count()) === 0);

  // Язык
  const langHref = await page.getAttribute('[data-lang-switch]', 'href');
  check('lang switch keeps route', langHref === '/en/', langHref ?? '');

  // MARK конвейер
  await page.goto(`${base}/en/work/mark/`, { waitUntil: 'networkidle' });
  await page.click('#m-stage-match');
  check('mark: stage 4 panel visible', await page.locator('#m-panel-match').isVisible());
  await page.focus('#m-stage-match');
  await page.keyboard.press('ArrowRight');
  check('mark: ArrowRight moves to stage 5', (await page.getAttribute('#m-stage-deliver', 'aria-selected')) === 'true');
  await page.keyboard.press('Home');
  check('mark: Home returns to stage 1', (await page.getAttribute('#m-stage-capture', 'aria-selected')) === 'true');

  // Seshat вкладки
  await page.goto(`${base}/ru/work/seshat/`, { waitUntil: 'networkidle' });
  await page.click('#s-exp-tab-reflect');
  check('seshat: reflect tab', await page.locator('#s-exp-panel-reflect').isVisible());
  await page.click('#s-arch-tab-engineering');
  check('seshat: engineering view', await page.locator('#s-arch-engineering').isVisible());
  check('no page errors (desktop)', errors.length === 0, errors.join(' | '));

  // — Mobile —
  const m = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await m.goto(`${base}/ru/`, { waitUntil: 'networkidle' });
  await m.click('[data-menu-toggle]');
  check('mobile menu opens', await m.locator('#site-menu').isVisible());
  check('main is inert while menu open', await m.locator('#main').evaluate((el) => el.hasAttribute('inert')));
  await m.keyboard.press('Escape');
  check('Escape closes menu', !(await m.locator('#site-menu').isVisible()));
  await m.click('#service-infra [data-svc-trigger]');
  await m.waitForTimeout(300);
  check('mobile accordion opens under row', await m.locator('#svc-panel-infra').isVisible());

  // — No JS —
  const ctx = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 800 } });
  const nj = await ctx.newPage();
  await nj.goto(`${base}/ru/work/mark/`);
  check('no-JS: all pipeline stages readable', (await nj.locator('.m-pipe__panel:visible').count()) === 5);
  await nj.goto(`${base}/ru/`);
  check('no-JS: K poster visible', await nj.locator('.k-stage__poster').evaluate((el) => getComputedStyle(el).opacity === '1'));
} finally {
  await browser.close();
  server.close();
}
console.table(results);
process.exit(results.some((r) => r.ok === 'FAIL') ? 1 : 0);
