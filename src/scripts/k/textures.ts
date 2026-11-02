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

/** Свечение полосы постоянной яркости по длине: гауссов профиль поперёк, мягкие концы. */
export function bandGlow(width = 256, height = 64): CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(width, height);
  for (let y = 0; y < height; y++) {
    const dy = (y / (height - 1)) * 2 - 1;
    const across = Math.exp(-(dy * dy) / 0.03) * 0.85 + Math.exp(-(dy * dy) / 0.25) * 0.4;
    for (let x = 0; x < width; x++) {
      const dx = x / (width - 1);
      const ends = Math.min(1, dx / 0.04, (1 - dx) / 0.04);
      const i = (y * width + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = 255;
      img.data[i + 3] = Math.round(Math.max(0, across * ends) * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  return tex;
}

/**
 * Матовый металл с потёртостями (как в ролике): пятна оттенка, мелкие царапины, лёгкая шлифовка.
 * Возвращает три согласованные карты: цвет (sRGB), шероховатость и рельеф (линейные).
 * UV лицевых граней — мировые координаты, поэтому repeat задаётся в «единицах знака».
 */
export function scratchedMetal(size = 1024): { map: CanvasTexture; roughness: CanvasTexture; bump: CanvasTexture } {
  const rand = mulberry32(4242);
  const mk = (): [HTMLCanvasElement, CanvasRenderingContext2D] => {
    const c = document.createElement('canvas');
    c.width = c.height = size;
    return [c, c.getContext('2d')!];
  };
  const [albedo, a] = mk();
  const [rough, r] = mk();
  const [bump, b] = mk();

  a.fillStyle = 'rgb(206,207,209)';
  a.fillRect(0, 0, size, size);
  r.fillStyle = 'rgb(150,150,150)'; // ≈0.59
  r.fillRect(0, 0, size, size);
  b.fillStyle = 'rgb(128,128,128)';
  b.fillRect(0, 0, size, size);

  // Пятна: мягкие тёмные и светлые области — металл «живой», а не ровно-серый.
  for (let i = 0; i < 40; i++) {
    const x = rand() * size;
    const y = rand() * size;
    const rad = 120 + rand() * 300;
    const dark = rand() < 0.55;
    const alpha = 0.02 + rand() * 0.05;
    for (const [ctx, col] of [
      [a, dark ? `rgba(60,62,66,${alpha})` : `rgba(255,255,255,${alpha * 0.7})`],
      [r, dark ? `rgba(220,220,220,${alpha})` : `rgba(90,90,90,${alpha})`],
    ] as [CanvasRenderingContext2D, string][]) {
      const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
      g.addColorStop(0, col);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.fillRect(x - rad, y - rad, rad * 2, rad * 2);
    }
  }

  // Шлифовка: тонкие продольные риски (едва заметны).
  for (let y = 0; y < size; y += 1) {
    if (rand() > 0.35) continue;
    const alpha = rand() * 0.06;
    a.fillStyle = `rgba(${rand() < 0.5 ? '255,255,255' : '40,42,46'},${alpha})`;
    a.fillRect(0, y, size, 1);
  }

  // Царапины: короткие светлые штрихи под случайными углами — блестят (ниже шероховатость), чуть вдавлены.
  for (let i = 0; i < 1100; i++) {
    const x = rand() * size;
    const y = rand() * size;
    const len = 6 + Math.pow(rand(), 2.2) * 160;
    const ang = rand() * Math.PI * 2;
    const x2 = x + Math.cos(ang) * len;
    const y2 = y + Math.sin(ang) * len;
    const alpha = 0.04 + rand() * 0.16;
    a.strokeStyle = `rgba(245,246,248,${alpha})`;
    r.strokeStyle = `rgba(70,70,70,${alpha})`;
    b.strokeStyle = `rgba(40,40,40,${alpha})`;
    for (const ctx of [a, r, b]) {
      ctx.lineWidth = rand() < 0.85 ? 1 : 2;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
  }

  const wrap = (c: HTMLCanvasElement, srgb: boolean): CanvasTexture => {
    const t = new CanvasTexture(c);
    t.wrapS = t.wrapT = RepeatWrapping;
    t.colorSpace = srgb ? SRGBColorSpace : LinearSRGBColorSpace;
    t.anisotropy = 8;
    return t;
  };
  return { map: wrap(albedo, true), roughness: wrap(rough, false), bump: wrap(bump, false) };
}
