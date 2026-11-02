/*
 * Реалистичные материалы знака: студийное HDRI-окружение и карты шлифованной стали
 * (открытые CC0-источники, подготовлены scripts/build-k-materials.mjs — источники и лицензии там же).
 * Грузятся параллельно с инициализацией сцены; при ошибке сцена остаётся на процедурных картах.
 */
import { LinearSRGBColorSpace, PMREMGenerator, RepeatWrapping, SRGBColorSpace, TextureLoader, type Texture, type WebGLRenderer } from 'three';
import { HDRLoader } from 'three/examples/jsm/loaders/HDRLoader.js';
import studioUrl from '@/assets/k/studio.hdr?url';
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

export async function loadStudio(renderer: WebGLRenderer): Promise<StudioAssets> {
  const textures = new TextureLoader();
  const [hdr, map, roughness, normal] = await Promise.all([
    new HDRLoader().loadAsync(asset(studioUrl)),
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
