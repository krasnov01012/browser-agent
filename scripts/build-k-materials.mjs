/*
 * Материалы 3D-знака из открытых CC0-источников → лёгкие файлы для сайта (src/assets/k/, Vite даёт им хэш в имени):
 *   studio-rgbe.png   — студийное HDRI-окружение: Poly Haven «studio_small_09» (CC0, polyhaven.com,
 *                       1K: dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/studio_small_09_1k.hdr),
 *                       уменьшено и «затемнено»: стены и пол уходят в тень, софтбоксы остаются яркими —
 *                       так металл отражает студию с полосами света, как на предметной съёмке стали.
 *                       Формат — RGBE в непрозрачном PNG двойной ширины: слева мантиссы RGB, справа экспонента
 *                       (в канале R). PNG отдаёт любой хостинг и превью-артефакт (.hdr — нет); без альфа-канала
 *                       браузер не портит значения предумножением. Декодер — src/scripts/k/materials.ts.
 *   steel-color.webp  — альбедо шлифованной стали ambientCG «Metal009» (CC0, ambientcg.com), в оттенках серого;
 *   steel-rough.webp  — её шероховатость;  steel-normal.webp — нормали (OpenGL).
 * Исходники в репозиторий не кладём (≈7 МБ): скачать 1K-версии с сайтов и передать пути.
 *
 *   Карты стали: ambientcg.com/get?file=Metal009_1K-JPG.zip (распаковать, нужны только *.jpg).
 *
 * Запуск: node scripts/build-k-materials.mjs <источник.hdr> <папка Metal009_1K-JPG> [--w 512] [--k 0.8] [--p 1.2]
 *   --w ширина HDR (высота = w/2), --k и --p — «колено» и крутизна затемнения: L' = L·(L/(L+k))^p.
 */
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const [src, maps, ...rest] = process.argv.slice(2);
if (!src || !maps) {
  console.error('usage: node scripts/build-k-materials.mjs <src.hdr> <Metal009 dir> [--w 512] [--k 0.8] [--p 1.2]');
  process.exit(1);
}
const opt = (name, def) => {
  const i = rest.indexOf(`--${name}`);
  return i >= 0 ? Number(rest[i + 1]) : def;
};
const W = opt('w', 512);
const H = W / 2;
const K = opt('k', 0.8);
const P = opt('p', 1.2);
const MAX = opt('max', 40);
const OUT = 'src/assets/k';
mkdirSync(OUT, { recursive: true });

// ——— HDR: чтение → уменьшение → затемнение → RGBE ———
const { HDRLoader } = await import('three/examples/jsm/loaders/HDRLoader.js');
const { FloatType } = await import('three');
const loader = new HDRLoader();
loader.setDataType(FloatType);
const buf = readFileSync(src);
const hdr = loader.parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const sw = hdr.width;
const sh = hdr.height;
const fx = sw / W;
const fy = sh / H;
const out = new Float32Array(W * H * 3);
for (let y = 0; y < H; y++) {
  for (let x = 0; x < W; x++) {
    let r = 0;
    let g = 0;
    let b = 0;
    let n = 0;
    for (let yy = Math.floor(y * fy); yy < Math.floor((y + 1) * fy); yy++) {
      for (let xx = Math.floor(x * fx); xx < Math.floor((x + 1) * fx); xx++) {
        const i = (yy * sw + xx) * 4;
        r += hdr.data[i];
        g += hdr.data[i + 1];
        b += hdr.data[i + 2];
        n++;
      }
    }
    r /= n;
    g /= n;
    b /= n;
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    // Затемнение средних тонов + лёгкое обесцвечивание (нейтральная сталь без цветного «отлива»)
    const f = lum > 0 ? Math.min(MAX / lum, Math.pow(lum / (lum + K), P)) : 0;
    const o = (y * W + x) * 3;
    out[o] = (lum + (r - lum) * 0.5) * f;
    out[o + 1] = (lum + (g - lum) * 0.5) * f;
    out[o + 2] = (lum + (b - lum) * 0.5) * f;
  }
}

function rgbe(r, g, b) {
  const v = Math.max(r, g, b);
  if (v < 1e-32) return [0, 0, 0, 0];
  const e = Math.ceil(Math.log2(v) + 1e-9);
  const s = 256 / Math.pow(2, e);
  return [Math.min(255, Math.floor(r * s)), Math.min(255, Math.floor(g * s)), Math.min(255, Math.floor(b * s)), e + 128];
}

// Пиксели PNG: [мантисса RGB | экспонента] — ширина 2W, альфа всегда 255
const png = new Uint8ClampedArray(2 * W * H * 4);
for (let y = 0; y < H; y++) {
  for (let x = 0; x < W; x++) {
    const o = (y * W + x) * 3;
    const [r, g, b, e] = rgbe(out[o], out[o + 1], out[o + 2]);
    const m = (y * 2 * W + x) * 4;
    const x2 = m + W * 4;
    png.set([r, g, b, 255], m);
    png.set([e, e, e, 255], x2);
  }
}

// ——— Карты стали: JPG → WebP через canvas Chromium ———
const { chromium } = require('playwright');
const browser = await chromium.launch();
const page = await browser.newPage();
const envB64 = await page.evaluate(
  ({ data, w, h }) => {
    const c = document.createElement('canvas');
    c.width = w;
    c.height = h;
    c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(data), w, h), 0, 0);
    return c.toDataURL('image/png').split(',')[1];
  },
  { data: [...png], w: 2 * W, h: H },
);
const envBin = Buffer.from(envB64, 'base64');
writeFileSync(join(OUT, 'studio-rgbe.png'), envBin);
console.log(`studio-rgbe.png ${2 * W}×${H}: ${(envBin.length / 1024).toFixed(0)} КБ (k=${K}, p=${P})`);
const jobs = [
  ['Color', 'steel-color.webp', true, 0.82],
  ['Roughness', 'steel-rough.webp', true, 0.86],
  ['NormalGL', 'steel-normal.webp', false, 0.9],
];
for (const [kind, name, gray, quality] of jobs) {
  const file = readFileSync(join(maps, `Metal009_1K-JPG_${kind}.jpg`)).toString('base64');
  const b64 = await page.evaluate(
    async ({ file, gray, quality }) => {
      const img = new Image();
      img.src = 'data:image/jpeg;base64,' + file;
      await img.decode();
      const c = document.createElement('canvas');
      c.width = img.width;
      c.height = img.height;
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0);
      if (gray) {
        const d = ctx.getImageData(0, 0, c.width, c.height);
        for (let i = 0; i < d.data.length; i += 4) {
          const v = Math.round(0.2126 * d.data[i] + 0.7152 * d.data[i + 1] + 0.0722 * d.data[i + 2]);
          d.data[i] = d.data[i + 1] = d.data[i + 2] = v;
        }
        ctx.putImageData(d, 0, 0);
      }
      return c.toDataURL('image/webp', quality).split(',')[1];
    },
    { file, gray, quality },
  );
  const bin = Buffer.from(b64, 'base64');
  writeFileSync(join(OUT, name), bin);
  console.log(`${name}: ${(bin.length / 1024).toFixed(0)} КБ`);
}
await browser.close();
