/*
 * Геометрия Architectural K v02.
 * Источник истины — design/k-v02/geometry.json (контуры в пространстве SVG 1000×1000).
 * Отображение в 3D — то же, что в architectural-k.glb: x' = (x − 500) / 165, y' = (500 − y) / 165.
 *
 * Почему не грузим GLB напрямую: в нём призмы из 12 вершин без нормалей и фасок,
 * а балки лежат в одной плоскости и мерцают (z-fighting) в зоне узла.
 * Поэтому собираем те же контуры с фасками и разносим балки по глубине на 0.02.
 * Подробности и сравнение — docs/DECISIONS.md, ADR-004.
 */
import type { Vec2 } from './types';

export const SCALE = 165;
export const toWorld = ([x, y]: Vec2): Vec2 => [(x - 500) / SCALE, (500 - y) / SCALE];

export const contours = {
  stem: [
    [246, 125],
    [363, 125],
    [363, 875],
    [246, 875],
  ],
  upper: [
    [363, 470],
    [675, 125],
    [827, 125],
    [426, 526],
  ],
  lower: [
    [363, 530],
    [426, 474],
    [827, 875],
    [675, 875],
  ],
} satisfies Record<string, Vec2[]>;

/** Коралловые швы — те же линии, что в architectural-k-primary.svg. */
export const seams = {
  upper: [
    [379, 474],
    [803, 135],
  ],
  lower: [
    [379, 526],
    [803, 865],
  ],
} satisfies Record<string, [Vec2, Vec2]>;

/** Узел: центр кораллового сигнала (circle cx=368 cy=500 в SVG). */
export const joint: Vec2 = [368, 500];

/** Глубина деталей (полутолщина в мировых единицах) — как в GLB. */
export const depth = {
  stem: 0.15,
  beam: 0.13,
};

/** Реальные параметры для технических подписей в Hero. */
export function describe(): { beamAngle: number; stemWidth: number; height: number } {
  const [a, b] = [contours.upper[0], contours.upper[1]];
  const angle = (Math.atan2(a[1] - b[1], b[0] - a[0]) * 180) / Math.PI;
  return {
    beamAngle: Math.round(angle * 10) / 10,
    stemWidth: contours.stem[1][0] - contours.stem[0][0],
    height: contours.stem[2][1] - contours.stem[1][1],
  };
}
