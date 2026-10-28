export type Vec2 = [number, number];

export interface KSceneState {
  /** 0..1 — прогресс сборки */
  assembly: number;
  /** Текущий наклон в градусах (для технической подписи) */
  tiltX: number;
  tiltY: number;
}

export interface KSceneOptions {
  canvas: HTMLCanvasElement;
  /** Статичный кадр без сборки и реакции на курсор (prefers-reduced-motion). */
  still: boolean;
  /** Пониженная плотность пикселей для слабых/мобильных устройств. */
  lowPower: boolean;
  onFirstFrame: () => void;
  onState?: (state: KSceneState) => void;
}
