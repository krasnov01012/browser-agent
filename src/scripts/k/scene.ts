/*
 * Three.js-сцена Architectural K: сборка, коралловый узел, «тихая» реакция на курсор и прокрутку.
 *
 * Хореография (≈7 с, контент страницы доступен с первой миллисекунды):
 *   0.4–2.6 с  опора поднимается и фиксируется
 *   1.2–3.4 с  верхняя балка заходит сверху справа
 *   1.8–4.0 с  нижняя балка заходит снизу справа
 *   4.0–5.4 с  загорается узел, швы прочерчиваются от узла наружу
 *   4.6–7.0 с  блик проходит по металлу, знак встаёт фронтально — состояние покоя
 * Покой: наклон за курсором ±4–5° с демпфированием, при прокрутке знак уходит вглубь.
 */
import {
  AdditiveBlending,
  BoxGeometry,
  CircleGeometry,
  Color,
  DirectionalLight,
  DoubleSide,
  ExtrudeGeometry,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  NeutralToneMapping,
  PerspectiveCamera,
  PlaneGeometry,
  PMREMGenerator,
  PointLight,
  Scene,
  Shape,
  SphereGeometry,
  BackSide,
  Vector2,
  WebGLRenderer,
  type Texture,
} from 'three';
import { contours, depth, joint, seams, toWorld } from './geometry';
import { brushedRoughness, lineGlow, radialGlow } from './textures';
import type { KSceneOptions, Vec2 } from './types';
import { clamp, ease, lerp, range } from '../motion';

const CORAL = new Color('#ff6548');
const VIEW_HEIGHT = 1000 / 165; // кадр = квадрат 1000×1000 из geometry.json
const FOV = 24;
const DEG = Math.PI / 180;
const DURATION = 7;

interface Part {
  mesh: Mesh;
  material: MeshPhysicalMaterial;
  rest: { x: number; y: number; z: number };
  from: { x: number; y: number; z: number; rz: number; ry: number };
  window: [number, number];
}

/** Студийное окружение для отражений: тёмная комната, софтбоксы и одна коралловая полоса. */
function buildEnvironment(renderer: WebGLRenderer): Texture {
  const env = new Scene();
  const room = new Mesh(new SphereGeometry(20, 32, 16), new MeshBasicMaterial({ color: 0x23262d, side: BackSide }));
  env.add(room);

  const panel = (w: number, h: number, color: Color, intensity: number, pos: [number, number, number], lookAt: [number, number, number] = [0, 0, 0]) => {
    const m = new Mesh(new PlaneGeometry(w, h), new MeshBasicMaterial({ color: color.clone().multiplyScalar(intensity), side: DoubleSide }));
    m.position.set(...pos);
    m.lookAt(...lookAt);
    env.add(m);
  };
  const white = new Color('#fffdf8');
  panel(16, 9, white, 3.4, [-5, 8, 9]); //      ключевой софтбокс сверху слева
  panel(14, 6, white, 1.6, [6, 3, 11]); //      фронтальная заливка справа
  panel(2, 18, white, 5, [10, 0, 1]); //        вертикальная контровая полоса справа
  panel(18, 4, white, 0.9, [0, -9, 5]); //      мягкий нижний рефлекс
  panel(6, 0.8, new Color('#ff6548'), 1.6, [-9, -4, 4]); // узкая коралловая полоса: тёплый рефлекс на фасках
  panel(10, 10, new Color('#9aa3c7'), 0.5, [4, 6, -10]); //  холодный задний рефлекс «стали»

  const pmrem = new PMREMGenerator(renderer);
  const target = pmrem.fromScene(env, 0.035);
  pmrem.dispose();
  room.geometry.dispose();
  return target.texture;
}

function extrude(points: Vec2[], halfDepth: number): ExtrudeGeometry {
  const pts = points.map(toWorld);
  const shape = new Shape();
  shape.moveTo(pts[0]![0], pts[0]![1]);
  for (const p of pts.slice(1)) shape.lineTo(p[0], p[1]);
  shape.closePath();
  const bevelThickness = 0.032;
  const bevelSize = 0.02;
  const geo = new ExtrudeGeometry(shape, {
    depth: halfDepth * 2 - bevelThickness * 2,
    bevelEnabled: true,
    bevelThickness,
    bevelSize,
    bevelOffset: -bevelSize, // силуэт совпадает с контуром v02 точно, фаска уходит внутрь
    bevelSegments: 3,
    curveSegments: 1,
  });
  geo.translate(0, 0, -(halfDepth - bevelThickness));
  geo.computeVertexNormals();
  return geo;
}

function metal(rough: Texture, angle: number, tint: string, roughness: number): MeshPhysicalMaterial {
  const map = rough.clone();
  map.needsUpdate = true;
  map.center.set(0.5, 0.5);
  map.rotation = angle;
  map.repeat.set(1.6, 1.6);
  return new MeshPhysicalMaterial({
    color: new Color(tint),
    metalness: 1,
    roughness,
    roughnessMap: map,
    anisotropy: 0.55,
    anisotropyRotation: angle,
    clearcoat: 0.4,
    clearcoatRoughness: 0.22,
    envMapIntensity: 1.25,
  });
}

/** Полоса шва: тонкая светящаяся линия + мягкий ореол. Растёт от узла наружу. */
function seam(a: Vec2, b: Vec2, z: number, glowTex: Texture) {
  const [ax, ay] = toWorld(a);
  const [bx, by] = toWorld(b);
  const len = Math.hypot(bx - ax, by - ay);
  const angle = Math.atan2(by - ay, bx - ax);

  const pivot = new Group();
  pivot.position.set(ax, ay, z);
  pivot.rotation.z = angle;

  const core = new Mesh(
    new PlaneGeometry(len, 0.02).translate(len / 2, 0, 0),
    new MeshBasicMaterial({ color: CORAL.clone().multiplyScalar(1.25), toneMapped: false, transparent: true }),
  );
  const halo = new Mesh(
    new PlaneGeometry(len + 0.2, 0.34).translate(len / 2, 0, 0.002),
    new MeshBasicMaterial({ map: glowTex, color: CORAL, transparent: true, opacity: 0.55, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
  );
  pivot.add(core, halo);
  return { pivot, core, halo };
}

export class KScene {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(FOV, 1, 0.1, 100);
  private root = new Group(); //   прокрутка и курсор
  private model = new Group(); //  сборка
  private parts: Part[] = [];
  private seamParts: ReturnType<typeof seam>[] = [];
  private jointCore: Mesh;
  private jointGlow: Mesh;
  private jointLight: PointLight;
  private chevron: Mesh[] = [];

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

    const key = new DirectionalLight(0xffffff, 1.6);
    key.position.set(-3, 5, 6);
    this.scene.add(key);

    // — Детали знака —
    const rough = brushedRoughness();
    const glowTex = lineGlow();
    const beamAngle = Math.atan2(toWorld(contours.upper[1])[1] - toWorld(contours.upper[0])[1], toWorld(contours.upper[1])[0] - toWorld(contours.upper[0])[0]);

    const stem = new Mesh(extrude(contours.stem, depth.stem), metal(rough, Math.PI / 2, '#e9e9e6', 0.42));
    const upper = new Mesh(extrude(contours.upper, depth.beam), metal(rough, beamAngle, '#e2e3e2', 0.44));
    const lower = new Mesh(extrude(contours.lower, depth.beam), metal(rough, -beamAngle, '#d6d8da', 0.46));

    // Верхняя балка чуть глубже нижней: в узле нижняя лежит сверху (как в SVG v02), без мерцания.
    this.parts = [
      { mesh: stem, material: stem.material as MeshPhysicalMaterial, rest: { x: 0, y: 0, z: 0 }, from: { x: -0.2, y: -3.4, z: -1.2, rz: 0.06, ry: -0.5 }, window: [0.4, 2.6] },
      { mesh: upper, material: upper.material as MeshPhysicalMaterial, rest: { x: 0, y: 0, z: -0.022 }, from: { x: 2.6, y: 2.4, z: -1.6, rz: -0.22, ry: 0.6 }, window: [1.2, 3.4] },
      { mesh: lower, material: lower.material as MeshPhysicalMaterial, rest: { x: 0, y: 0, z: 0 }, from: { x: 2.8, y: -2.6, z: -1.4, rz: 0.24, ry: 0.5 }, window: [1.8, 4.0] },
    ];
    for (const p of this.parts) this.model.add(p.mesh);

    // — Швы и узел —
    const upperFront = depth.beam - 0.022 + 0.004;
    const lowerFront = depth.beam + 0.004;
    this.seamParts = [seam(seams.upper[0], seams.upper[1], upperFront, glowTex), seam(seams.lower[0], seams.lower[1], lowerFront, glowTex)];
    for (const s of this.seamParts) this.model.add(s.pivot);

    const [jx, jy] = toWorld(joint);
    // Яркость ×1.15: красный канал упирается в 1, но оттенок остаётся коралловым, а не персиковым.
    this.jointCore = new Mesh(new CircleGeometry(0.062, 40), new MeshBasicMaterial({ color: CORAL.clone().multiplyScalar(1.15), toneMapped: false, transparent: true }));
    // Точка узла лежит перед ореолом: аддитивное свечение не выбеливает фирменный коралл.
    this.jointCore.position.set(jx, jy, depth.stem + 0.014);
    this.jointGlow = new Mesh(
      new PlaneGeometry(1.5, 1.5),
      new MeshBasicMaterial({ map: radialGlow(), color: CORAL, transparent: true, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
    );
    this.jointGlow.position.set(jx, jy, depth.stem + 0.006);
    this.jointLight = new PointLight(CORAL, 0, 1.8, 2);
    this.jointLight.position.set(jx + 0.18, jy, 0.42);
    this.model.add(this.jointCore, this.jointGlow, this.jointLight);

    // Шеврон в узле (M 365 481 L 383 500 L 365 519 из SVG v02).
    const chevronMat = new MeshBasicMaterial({ color: CORAL.clone().multiplyScalar(1.15), toneMapped: false, transparent: true });
    for (const [a, b] of [
      [[365, 481], [383, 500]],
      [[383, 500], [365, 519]],
    ] as [Vec2, Vec2][]) {
      const [ax, ay] = toWorld(a);
      const [bx, by] = toWorld(b);
      const len = Math.hypot(bx - ax, by - ay);
      const bar = new Mesh(new BoxGeometry(len, 0.016, 0.004), chevronMat);
      bar.position.set((ax + bx) / 2, (ay + by) / 2, depth.stem + 0.012);
      bar.rotation.z = Math.atan2(by - ay, bx - ax);
      this.chevron.push(bar);
      this.model.add(bar);
    }

    this.root.add(this.model);
    this.scene.add(this.root);

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
    // Кадр всегда вмещает квадрат 1000×1000 — синхронно с SVG-чертежом под холстом.
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
    for (const p of this.parts) {
      const q = ease.outQuint(range(t, p.window[0], p.window[1]));
      const inv = 1 - q;
      p.mesh.position.set(p.rest.x + p.from.x * inv, p.rest.y + p.from.y * inv, p.rest.z + p.from.z * inv);
      p.mesh.rotation.set(0, p.from.ry * inv, p.from.rz * inv);
      const fade = range(t, p.window[0], p.window[0] + 0.7);
      p.material.transparent = fade < 1;
      p.material.opacity = fade;
    }

    // Узел и швы
    const ignite = ease.outCubic(range(t, 4.0, 4.9));
    const flicker = t < 5 ? 1 + Math.sin(t * 38) * 0.08 * (1 - ignite) : 1;
    (this.jointCore.material as MeshBasicMaterial).opacity = ignite;
    this.jointCore.scale.setScalar(0.4 + 0.6 * ignite);
    (this.jointGlow.material as MeshBasicMaterial).opacity = ignite * 0.85 * flicker;
    this.jointGlow.scale.setScalar(0.6 + 0.4 * ignite + 0.35 * (1 - range(t, 4.4, 5.6)) * ignite);
    this.jointLight.intensity = 0.9 * ignite * flicker;
    for (const bar of this.chevron) (bar.material as MeshBasicMaterial).opacity = range(t, 4.3, 4.8);

    const draw = ease.inOutCubic(range(t, 4.2, 5.4));
    for (const s of this.seamParts) {
      s.pivot.scale.set(Math.max(0.0001, draw), 1, 1);
      (s.core.material as MeshBasicMaterial).opacity = range(t, 4.2, 4.5);
      (s.halo.material as MeshBasicMaterial).opacity = 0.5 * draw;
    }

    // Блик по металлу и выход во фронтальный ракурс
    const settle = ease.inOutCubic(range(t, 0.4, 6.6));
    // Блик проходит по металлу, но без пересвета: диапазон поворота окружения ограничен.
    this.scene.environmentRotation.y = lerp(-0.5, 0.1, ease.inOutCubic(range(t, 3.6, 7)));
    this.model.rotation.set(lerp(0.1, 0, settle), lerp(-0.42, 0, settle), 0);
    this.model.position.z = lerp(-0.6, 0, settle);
  }
}
