/*
 * Реалистичные материалы знака: студийное HDRI-окружение и карты шлифованной стали
 * (открытые CC0-источники, подготовлены scripts/build-k-materials.mjs — источники и лицензии там же).
 * Грузятся параллельно с инициализацией сцены; при ошибке сцена остаётся на процедурных картах.
 */
import {
  DataTexture,
  DataUtils,
  EquirectangularReflectionMapping,
  HalfFloatType,
  LinearFilter,
  LinearSRGBColorSpace,
  PMREMGenerator,
  RepeatWrapping,
  RGBAFormat,
  SRGBColorSpace,
  TextureLoader,
  type Texture,
  type WebGLRenderer,
} from 'three';
import studioUrl from '@/assets/k/studio-rgbe.png?url';
import colorUrl from '@/assets/k/steel-color.webp?url';
import roughUrl from '@/assets/k/steel-rough.webp?url';
import normalUrl from '@/assets/k/steel-normal.webp?url';

export interface SteelMaps {
  map: Texture;
  roughness: Texture;
  normal: Texture;
}

export interface StudioAssets {
  environment: Texture;
  steel: SteelMaps;
}

/** Адрес ассета относительно самого модуля — работает и на сайте, и в копии-превью. */
const asset = (url: string): string => new URL(url, import.meta.url).href;

/**
 * HDRI из PNG: левая половина — мантиссы RGB, правая — экспонента RGBE (см. build-k-materials.mjs).
 * PNG непрозрачный, поэтому getImageData отдаёт байты без предумножения альфой.
 */
async function loadRgbePng(url: string): Promise<DataTexture> {
  const img = new Image();
  img.src = url;
  await img.decode();
  const w = img.width / 2;
  const h = img.height;
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, img.width, h).data;
  const data = new Uint16Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const m = (y * img.width + x) * 4;
      const e = px[m + w * 4]!;
      const f = e ? 2 ** (e - 136) : 0; // RGBE: значение = мантисса · 2^(E − 128 − 8)
      const o = (y * w + x) * 4;
      data[o] = DataUtils.toHalfFloat(px[m]! * f);
      data[o + 1] = DataUtils.toHalfFloat(px[m + 1]! * f);
      data[o + 2] = DataUtils.toHalfFloat(px[m + 2]! * f);
      data[o + 3] = DataUtils.toHalfFloat(1);
    }
  }
  const tex = new DataTexture(data, w, h, RGBAFormat, HalfFloatType);
  tex.mapping = EquirectangularReflectionMapping;
  tex.colorSpace = LinearSRGBColorSpace;
  tex.minFilter = tex.magFilter = LinearFilter;
  tex.flipY = true;
  tex.needsUpdate = true;
  return tex;
}

export async function loadStudio(renderer: WebGLRenderer): Promise<StudioAssets> {
  const textures = new TextureLoader();
  const [hdr, map, roughness, normal] = await Promise.all([
    loadRgbePng(asset(studioUrl)),
    textures.loadAsync(asset(colorUrl)),
    textures.loadAsync(asset(roughUrl)),
    textures.loadAsync(asset(normalUrl)),
  ]);

  const pmrem = new PMREMGenerator(renderer);
  const environment = pmrem.fromEquirectangular(hdr).texture;
  pmrem.dispose();
  hdr.dispose();

  const maxAniso = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  for (const t of [map, roughness, normal]) {
    t.wrapS = t.wrapT = RepeatWrapping;
    t.anisotropy = maxAniso;
    t.colorSpace = t === map ? SRGBColorSpace : LinearSRGBColorSpace;
  }
  return { environment, steel: { map, roughness, normal } };
}
