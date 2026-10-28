/*
 * Оркестрация сцены K в Hero: проверка WebGL, ленивая загрузка Three.js,
 * fallback на SVG, видимость, курсор, прокрутка, техническая подпись.
 *
 * Состояния [data-state] на .k-stage:
 *   pending  — чертёж прорисовывается, 3D ещё грузится (текст Hero уже доступен)
 *   live     — WebGL отрисовал первый кадр
 *   fallback — нет WebGL / ошибка / потеря контекста → статичный SVG-знак
 */
import type { KScene } from './scene';
import { reducedMotion } from '../motion';

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') ?? c.getContext('webgl'));
  } catch {
    return false;
  }
}

export async function initKStage(): Promise<void> {
  const stage = document.querySelector<HTMLElement>('[data-k-stage]');
  const canvas = stage?.querySelector<HTMLCanvasElement>('canvas');
  const hero = stage?.closest<HTMLElement>('[data-hero]');
  if (!stage || !canvas || !hero) return;

  const still = reducedMotion();
  const hud = {
    assembly: stage.querySelector<HTMLElement>('[data-hud-assembly]'),
    tilt: stage.querySelector<HTMLElement>('[data-hud-tilt]'),
  };

  const fallback = (reason: string): void => {
    stage.dataset.state = 'fallback';
    stage.dataset.reason = reason;
  };

  if (!webglAvailable()) return fallback('no-webgl');

  // Если 3D не показало кадр за 6 с (медленная сеть/устройство) — показываем статичный знак.
  const timeout = window.setTimeout(() => {
    if (stage.dataset.state === 'pending') fallback('timeout');
  }, 6000);

  let scene: KScene;
  try {
    const { KScene } = await import('./scene');
    const coarse = matchMedia('(pointer: coarse)').matches;
    let lastHud = 0;
    scene = new KScene({
      canvas,
      still,
      lowPower: coarse || innerWidth < 768,
      onFirstFrame: () => {
        window.clearTimeout(timeout);
        if (stage.dataset.state !== 'fallback') stage.dataset.state = 'live';
      },
      onState: ({ assembly, tiltX, tiltY }) => {
        const now = performance.now();
        // Финальное значение (100%) показываем всегда, остальное — не чаще ~16 раз/с.
        if (now - lastHud < 60 && assembly < 1) return;
        lastHud = now;
        if (hud.assembly) hud.assembly.textContent = `${String(Math.round(assembly * 100)).padStart(3, '0')}%`;
        if (hud.tilt) hud.tilt.textContent = `${fmt(tiltX)}° ${fmt(tiltY)}°`;
      },
    });
  } catch (error) {
    window.clearTimeout(timeout);
    console.warn('[k] WebGL init failed, using SVG mark', error);
    return fallback('init-error');
  }

  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    fallback('context-lost');
    scene.dispose();
  });

  const ro = new ResizeObserver(([entry]) => {
    if (!entry) return;
    const { width, height } = entry.contentRect;
    scene.resize(width, height);
  });
  ro.observe(canvas);

  new IntersectionObserver(([entry]) => scene.setVisible(!!entry?.isIntersecting), { rootMargin: '80px' }).observe(stage);
  document.addEventListener('visibilitychange', () => scene.setVisible(!document.hidden));

  if (!still) {
    // Курсор: нормированное положение относительно центра сцены.
    const finePointer = matchMedia('(pointer: fine)').matches;
    if (finePointer) {
      addEventListener(
        'pointermove',
        (e) => {
          const r = stage.getBoundingClientRect();
          scene.setPointer(((e.clientX - (r.left + r.width / 2)) / innerWidth) * 2, ((e.clientY - (r.top + r.height / 2)) / innerHeight) * 2);
        },
        { passive: true },
      );
      document.documentElement.addEventListener('pointerleave', () => scene.setPointer(0, 0));
    }

    // Прокрутка: знак уходит вглубь по мере ухода Hero; ранний скролл досрочно завершает сборку.
    const onScroll = (): void => {
      const r = hero.getBoundingClientRect();
      const progress = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height)));
      scene.setScroll(progress);
      if (scrollY > 40) scene.hurry();
    };
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('keydown', () => scene.hurry(), { once: true });
    onScroll();
  }

  stage.dataset.mode = still ? 'still' : 'motion';
  scene.start();
}

function fmt(v: number): string {
  const s = v >= 0 ? '+' : '−';
  return `${s}${Math.abs(v).toFixed(1)}`;
}
