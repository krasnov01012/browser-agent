/*
 * Рендер растровых ассетов из настоящей 3D-сцены K (а не из отдельного макета):
 *   public/media/k/k-render.png        — знак в покое, прозрачный фон, 1000×1000; затем
 *                                        python3 -c "from PIL import Image; Image.open('public/media/k/k-render.png').save('public/media/k/k-render.webp', quality=86, method=6)"
 *                                        → k-render.webp (fallback без WebGL), png удалить
 *   public/media/og/krasnoff-og.png    — карточка для соцсетей 1200×630
 *   public/media/k/apple-touch-icon.png — 180×180
 * Требует dist/ (npm run build). Запуск: npm run assets:k
 */
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile, cp, rm } from 'node:fs/promises';
import { serveDist } from './serve-dist.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const port = 4397;
const server = await serveDist(port);
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

await mkdir('public/media/k', { recursive: true });
await mkdir('public/media/og', { recursive: true });

try {
  // 1) Знак: сцена в покое (reduced-motion), фон прозрачный, без чертежа и подписей.
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1200 }, reducedMotion: 'reduce', deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`http://localhost:${port}/en/`, { waitUntil: 'networkidle' });
  await page.addStyleTag({
    content: `html,body,.hero{background:transparent!important}.hero::before,.k-blueprint,.k-stage__hud,.site-header,.hero__text,.hero__caps{display:none!important}
      .k-stage{position:fixed!important;left:0;top:0;width:1000px!important;height:1000px;margin:0!important}`,
  });
  await page.waitForFunction(() => document.querySelector('[data-k-stage]')?.getAttribute('data-state') === 'live');
  await page.waitForTimeout(1500);
  await page.locator('.k-stage__canvas').screenshot({ path: 'public/media/k/k-render.png', omitBackground: true });
  await ctx.close();

  // 2) OG-карточка: рендер знака + словесная часть, шрифты сайта.
  const tmp = 'dist/__og';
  await mkdir(tmp, { recursive: true });
  await cp('node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2', `${tmp}/geist.woff2`);
  await cp('node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2', `${tmp}/plex.woff2`);
  await cp('public/media/k/k-render.png', `${tmp}/k.png`);
  await writeFile(
    `${tmp}/index.html`,
    `<!doctype html><meta charset="utf-8"><style>
      @font-face{font-family:G;src:url(geist.woff2) format('woff2');font-weight:100 900}
      @font-face{font-family:P;src:url(plex.woff2) format('woff2')}
      html,body{margin:0;width:1200px;height:630px;background:#0B0D11;color:#F3F0E9;font-family:G;overflow:hidden}
      .g{position:absolute;inset:0;background:radial-gradient(40% 60% at 76% 50%,rgba(255,101,72,.08),transparent 70%)}
      .l{position:absolute;inset:0;background:linear-gradient(#777C93,#777C93) 0 96px/100% 1px no-repeat,linear-gradient(#777C93,#777C93) 0 534px/100% 1px no-repeat;opacity:.18}
      img{position:absolute;right:30px;top:-15px;width:660px;height:660px}
      .t{position:absolute;left:72px;top:150px;width:600px}
      .k{font-family:P;font-size:16px;letter-spacing:.14em;color:#9CA0B3;text-transform:uppercase;display:flex;gap:14px;align-items:center}
      .k:before{content:'';width:28px;height:1px;background:#FF6548}
      h1{margin:28px 0 0;font-size:92px;line-height:.9;letter-spacing:-.045em;font-weight:650;text-transform:uppercase}
      h1 i{font-style:normal;color:#FF6548}
      .w{position:absolute;left:72px;bottom:56px;font-size:22px;font-weight:620;letter-spacing:.24em}
      .w span{display:block;margin-top:8px;font-size:12px;letter-spacing:.52em;color:#9CA0B3;font-weight:500}
    </style><div class="g"></div><div class="l"></div><img src="k.png">
    <div class="t"><div class="k">Custom software engineering</div><h1>Software.<br>Built<br>for you<i>.</i></h1></div>
    <div class="w">KRASNOFF<span>DEVELOPMENT</span></div>`,
  );
  const og = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await og.goto(`http://localhost:${port}/__og/`, { waitUntil: 'networkidle' });
  await og.evaluate(() => document.fonts.ready);
  await og.screenshot({ path: 'public/media/og/krasnoff-og.png' });

  // 3) Иконка для iOS из favicon.svg.
  const svg = await readFile('public/favicon.svg', 'utf8');
  const icon = await browser.newPage({ viewport: { width: 180, height: 180 } });
  await icon.setContent(`<style>html,body{margin:0;background:#0B0D11}svg{width:180px;height:180px;display:block}</style>${svg.replace('rx="12"', 'rx="0"')}`);
  await icon.screenshot({ path: 'public/media/k/apple-touch-icon.png' });
  await rm(tmp, { recursive: true, force: true });
} finally {
  await browser.close();
  server.close();
}
console.log('rendered: k-render.png, krasnoff-og.png, apple-touch-icon.png');
