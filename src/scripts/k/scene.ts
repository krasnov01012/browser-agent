/*
 * Three.js-сцена «Modular K»: студия, сборка из модулей, свет из щелей, отражение на полу,
 * «тихая» реакция на курсор и прокрутку. Сама модель — build.ts, геометрия — modular.ts.
 *
 * Хореография (≈7 с по ролику владельца; контент страницы доступен с первой миллисекунды):
 *   0.2–2.8 с  модули и мелкие детали влетают из-за камеры, вращаясь
 *   2.1–3.4 с  «взрыв-схема»: модули зависают, прочерчиваются оранжевые строительные линии
 *   3.3–4.3 с  стыковка модулей
 *   4.25–5.2 с по контурам всех модулей пробегает свет
 *   4.8–6.4 с  контуры гаснут, остаются светящиеся щели и вставки; знак встаёт в ракурс покоя
 * Покой: наклон за курсором ±4–5° с демпфированием, при прокрутке знак уходит вглубь.
 */
import {
  AdditiveBlending,
  BackSide,
  Color,
  DirectionalLight,
  DoubleSide,
  Group,
  Mesh,
  MeshBasicMaterial,
  NeutralToneMapping,
  PerspectiveCamera,
  PlaneGeometry,
  PMREMGenerator,
  PointLight,
  Scene,
  SphereGeometry,
  Vector2,
  WebGLRenderer,
  type Texture,
} from 'three';
import { toWorld, contours } from './geometry';
import { buildK, CORAL, type KModel } from './build';
import { radialGlow } from './textures';
import type { KSceneOptions } from './types';
import { clamp, ease, lerp, range } from '../motion';

const VIEW_HEIGHT = 1000 / 165; // кадр = квадрат 1000×1000 из geometry.json
const FOV = 24;
const DEG = Math.PI / 180;
const DURATION = 7;
/** Масштаб и вертикальный сдвиг знака в кадре: снизу остаётся место под отражение. */
const SCALE = 0.86;
const OFFSET_Y = 0.78;
/** Ракурс покоя (как в ролике): камера чуть справа и сверху — видны торцы модулей и толщина балок. */
const REST_YAW = -0.22;
const REST_PITCH = 0.07;

/** Студийное окружение: тёмная комната, острые софтбоксы — контрастные блики на гранях. */
function buildEnvironment(renderer: WebGLRenderer): Texture {
  const env = new Scene();
  const room = new Mesh(new SphereGeometry(20, 32, 16), new MeshBasicMaterial({ color: 0x15171c, side: BackSide }));
  env.add(room);

  const panel = (w: number, h: number, color: Color, intensity: number, pos: [number, number, number]) => {
    const m = new Mesh(new PlaneGeometry(w, h), new MeshBasicMaterial({ color: color.clone().multiplyScalar(intensity), side: DoubleSide }));
    m.position.set(...pos);
    m.lookAt(0, 0, 0);
    env.add(m);
  };
  const white = new Color('#fffdf8');
  panel(16, 7, white, 3.0, [-5, 9, 8]); //       ключевой софтбокс сверху слева
  panel(10, 5, white, 1.3, [7, 3, 11]); //       фронтальная заливка справа
  panel(1.6, 20, white, 4.2, [10, 0, 1]); //     вертикальная контровая полоса справа
  panel(1.6, 20, white, 2.6, [-10, 0, -2]); //   контровая полоса слева
  panel(18, 3, white, 0.8, [0, -9, 5]); //       мягкий нижний рефлекс
  panel(6, 0.8, new Color('#ff6548'), 1.8, [-9, -4, 4]); // тёплый рефлекс на фасках
  panel(10, 10, new Color('#9aa3c7'), 0.5, [4, 6, -10]); //  холодный задний рефлекс «стали»

  const pmrem = new PMREMGenerator(renderer);
  const target = pmrem.fromScene(env, 0.03);
  pmrem.dispose();
  room.geometry.dispose();
  return target.texture;
}

export class KScene {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(FOV, 1, 0.1, 100);
  private root = new Group(); //   прокрутка и курсор
  private rig = new Group(); //    масштаб/сдвиг/ракурс
  private main: KModel;
  private mirror: KModel;
  private jointLight: PointLight;
  private spill: PointLight[] = [];
  private haze: Mesh;
  private floor: Mesh;

  private time = 0;
  private speed = 1;
  private last = 0;
  private raf = 0;
  private running = false;
  private visible = true;
  private firstFrame = false;

  private pointer = new Vector2();
  private tilt = new Vector2();
  private scroll = 0;
  private scrollSmooth = 0;

  constructor(private opts: KSceneOptions) {
    const { canvas, lowPower } = opts;
    this.renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance', premultipliedAlpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, lowPower ? 1.5 : 2));
    this.renderer.toneMapping = NeutralToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.setClearColor(0x000000, 0);

    this.scene.environment = buildEnvironment(this.renderer);
    this.scene.environmentRotation.set(0, -0.5, 0);

    const key = new DirectionalLight(0xffffff, 1.5);
    key.position.set(-3, 5, 6);
    const rim = new DirectionalLight(0xdfe3ea, 0.5);
    rim.position.set(6, 2, -4);
    this.scene.add(key, rim);

    // — Модель и её отражение на полу —
    this.main = buildK({ ghost: false });
    this.mirror = buildK({ ghost: true });
    const floorY = toWorld(contours.stem[2])[1];
    this.mirror.root.scale.y = -1;
    this.mirror.root.position.y = 2 * floorY;
    this.rig.add(this.main.root, this.mirror.root);
    this.rig.scale.setScalar(SCALE);
    this.rig.position.y = OFFSET_Y;
    this.root.add(this.rig);
    this.scene.add(this.root);

    // Огни узла и щелей (только у основной модели): тёплый свет из стыков ложится на соседний металл
    const { node, spill } = this.main.lights!;
    this.jointLight = new PointLight(CORAL, 0, 3.2, 2);
    this.jointLight.position.set(node[0] + 0.25, node[1], 0.9);
    this.rig.add(this.jointLight);
    for (const [x, y] of spill) {
      const l = new PointLight(CORAL, 0, 3.2, 2);
      l.position.set(x, y, 1.3);
      this.spill.push(l);
      this.rig.add(l);
    }

    const floorWorld = OFFSET_Y + floorY * SCALE;

    // Тёплый отсвет на полу и холодная дымка света сверху (атмосфера концепта)
    this.floor = new Mesh(
      new PlaneGeometry(6.2, 1.0),
      new MeshBasicMaterial({ map: radialGlow(), color: new Color('#ff9f84'), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
    );
    this.floor.position.set(0.5, floorWorld - 0.02, 0.2);
    this.floor.renderOrder = 5;
    this.scene.add(this.floor);

    this.haze = new Mesh(
      new PlaneGeometry(5.2, 5.2),
      new MeshBasicMaterial({ map: radialGlow(), color: new Color('#b9c6ff'), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
    );
    this.haze.position.set(-0.6, 2.2, -2.8);
    this.scene.add(this.haze);

    this.camera.position.set(0, 0, VIEW_HEIGHT / 2 / Math.tan((FOV / 2) * DEG));
    this.camera.lookAt(0, 0, 0);

    if (opts.still) this.time = DURATION;
    this.apply(this.time);
  }

  /** Размер холста в CSS-пикселях. */
  resize(width: number, height: number): void {
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    // Кадр всегда вмещает квадрат 1000×1000.
    const fit = Math.max(1, 1 / this.camera.aspect);
    this.camera.position.z = (VIEW_HEIGHT * fit) / 2 / Math.tan((FOV / 2) * DEG);
    this.camera.updateProjectionMatrix();
    this.wake();
  }

  setPointer(nx: number, ny: number): void {
    if (this.opts.still) return;
    this.pointer.set(clamp(nx, -1, 1), clamp(ny, -1, 1));
    this.wake();
  }

  setScroll(progress: number): void {
    this.scroll = clamp(progress);
    this.wake();
  }

  setVisible(visible: boolean): void {
    this.visible = visible;
    if (visible) this.wake();
  }

  /** Пользователь начал действовать во время сборки — плавно завершаем её за ~0.7 с. */
  hurry(): void {
    if (this.time >= DURATION) return;
    const remaining = DURATION - this.time;
    this.speed = Math.max(this.speed, remaining / 0.7);
    this.wake();
  }

  start(): void {
    this.wake();
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.renderer.dispose();
  }

  private wake(): void {
    if (this.running || !this.visible || document.hidden) return;
    this.running = true;
    this.last = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  private frame = (now: number): void => {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;

    if (this.time < DURATION) this.time = Math.min(DURATION, this.time + dt * this.speed);
    this.apply(this.time);

    // Демпфированное следование за курсором (≤ 4° по X, ≤ 5° по Y) — только в покое.
    const rest = range(this.time, 5.2, DURATION);
    const k = 1 - Math.pow(0.0025, dt);
    this.tilt.x = lerp(this.tilt.x, -this.pointer.y * 4 * rest, k);
    this.tilt.y = lerp(this.tilt.y, this.pointer.x * 5 * rest, k);
    this.scrollSmooth = lerp(this.scrollSmooth, this.scroll, 1 - Math.pow(0.0005, dt));

    const s = ease.inOutCubic(this.scrollSmooth);
    this.root.rotation.set(this.tilt.x * DEG + s * 0.32, this.tilt.y * DEG - s * 0.22, 0);
    this.root.position.set(s * 0.5, s * 0.9, -s * 3.2);

    this.renderer.render(this.scene, this.camera);
    if (!this.firstFrame) {
      this.firstFrame = true;
      this.opts.onFirstFrame();
    }
    this.opts.onState?.({ assembly: this.time / DURATION, tiltX: this.tilt.x, tiltY: this.tilt.y });

    const settled =
      this.time >= DURATION &&
      Math.abs(this.tilt.x + this.pointer.y * 4) < 0.01 &&
      Math.abs(this.tilt.y - this.pointer.x * 5) < 0.01 &&
      Math.abs(this.scrollSmooth - this.scroll) < 0.0005;

    if (settled || !this.visible || document.hidden) {
      this.running = false;
      return;
    }
    this.raf = requestAnimationFrame(this.frame);
  };

  /** Состояние сцены в момент t (секунды хореографии). */
  private apply(t: number): void {
    this.main.apply(t);
    this.mirror.apply(t);

    // Свет включается вместе со щелями (4.8–5.8 с), во время пробега по контурам — короткая вспышка
    const seam = ease.inOutCubic(range(t, 4.8, 5.8));
    const burst = Math.sin(Math.PI * range(t, 4.25, 6.0));
    const flicker = t < 5.4 ? 1 + Math.sin(t * 43) * 0.08 * (1 - seam) : 1;
    this.jointLight.intensity = (0.8 * seam + 0.6 * burst) * flicker;
    for (const l of this.spill) l.intensity = 0.25 * seam + 0.35 * burst;
    (this.floor.material as MeshBasicMaterial).opacity = 0.32 * ease.outCubic(range(t, 4.4, 6.4));
    (this.haze.material as MeshBasicMaterial).opacity = 0.11 * ease.outCubic(range(t, 0.2, 3.0));

    // Блик проходит по металлу и знак встаёт в ракурс покоя
    const settle = ease.inOutCubic(range(t, 0.3, 6.6));
    this.scene.environmentRotation.y = lerp(-0.5, 0.15, ease.inOutCubic(range(t, 3.6, 7)));
    this.rig.rotation.set(lerp(-0.12, REST_PITCH, settle), lerp(0.45, REST_YAW, settle), 0);
    this.rig.position.z = lerp(-0.8, 0, settle);
  }
}
