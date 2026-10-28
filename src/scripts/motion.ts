/** Общие утилиты движения. */

export const reducedMotion = (): boolean => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const clamp = (v: number, min = 0, max = 1): number => Math.min(max, Math.max(min, v));

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

/** Нормированный прогресс t в окне [start, end]. */
export const range = (t: number, start: number, end: number): number => clamp((t - start) / (end - start));

export const ease = {
  outExpo: (t: number): number => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  outCubic: (t: number): number => 1 - Math.pow(1 - t, 3),
  inOutCubic: (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outQuint: (t: number): number => 1 - Math.pow(1 - t, 5),
  /** «Механическая» кривая: быстрый ход и мягкая фиксация без отскока. */
  mech: (t: number): number => {
    const a = 1 - Math.pow(1 - t, 4);
    return a;
  },
};
