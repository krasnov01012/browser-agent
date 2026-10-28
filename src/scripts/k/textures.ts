/*
 * Процедурные текстуры знака: шлифованный металл и мягкое свечение шва.
 * Генерируются на canvas при загрузке — ни одного внешнего файла изображения.
 */
import { CanvasTexture, LinearSRGBColorSpace, RepeatWrapping, SRGBColorSpace } from 'three';

/** Детерминированный псевдослучайный генератор — одинаковая «шлифовка» при каждой загрузке. */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Карта шероховатости шлифованного металла: тонкие продольные риски.
 * Значения около базовой шероховатости ±, вдоль оси X текстуры.
 */
export function brushedRoughness(size = 512): CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(size, size);
  const rand = mulberry32(1337);

  const rows = new Float32Array(size);
  for (let y = 0; y < size; y++) rows[y] = rand();
  // Сглаживаем по вертикали, чтобы риски шли пучками разной ширины.
  for (let pass = 0; pass < 2; pass++) {
    for (let y = 1; y < size - 1; y++) rows[y] = (rows[y - 1]! + rows[y]! * 2 + rows[y + 1]!) / 4;
  }

  for (let y = 0; y < size; y++) {
    let streak = 0;
    for (let x = 0; x < size; x++) {
      // Длинные риски: медленно меняющийся шум вдоль строки.
      streak = streak * 0.96 + (rand() - 0.5) * 0.08;
      // Значения 0.72–1.0: множитель базовой шероховатости, риски заметны, но не «полосят».
      const v = 0.86 + (rows[y]! - 0.5) * 0.28 + streak * 0.6 + (rand() - 0.5) * 0.04;
      const c = Math.max(0, Math.min(255, Math.round(v * 255)));
      const i = (y * size + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = c;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  const tex = new CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  tex.colorSpace = LinearSRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** Свечение вдоль линии: гауссов профиль поперёк и мягкие концы. */
export function lineGlow(width = 256, height = 64): CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(width, height);
  for (let y = 0; y < height; y++) {
    const dy = (y / (height - 1)) * 2 - 1;
    const across = Math.exp(-(dy * dy) / 0.045) * 0.9 + Math.exp(-(dy * dy) / 0.32) * 0.35;
    for (let x = 0; x < width; x++) {
      const dx = x / (width - 1);
      const ends = Math.min(1, dx / 0.08, (1 - dx) / 0.08);
      // Сильнее у узла (dx = 0), к концу балки — затухание: свет «исходит» из соединения.
      const fromJoint = 1 - 0.72 * Math.pow(dx, 0.8);
      const a = Math.max(0, across * ends * fromJoint);
      const i = (y * width + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = 255;
      img.data[i + 3] = Math.round(a * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  return tex;
}

/** Радиальное свечение узла. */
export function radialGlow(size = 128): CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.12, 'rgba(255,255,255,0.7)');
  g.addColorStop(0.4, 'rgba(255,255,255,0.16)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  return tex;
}
