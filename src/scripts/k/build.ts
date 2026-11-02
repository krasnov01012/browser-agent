/*
 * Модель Architectural K для сцены: полая рама опоры с внутренней механикой, рамные балки с фасетками,
 * узел с болтами и коралловым свечением. Силуэт точно совпадает с контурами v02 (geometry.json),
 * но детали собраны как «инженерный объект», а не плоская призма — как на утверждённом концепте.
 *
 * Сборка: каждая деталь стартует рассыпанной (контур-чертёж → выравнивание → сборка → фиксация → свет),
 * окна детали заданы в секундах хореографии (0–7 с, см. scene.ts).
 */
import {
  AdditiveBlending,
  CircleGeometry,
  Color,
  CylinderGeometry,
  EdgesGeometry,
  Euler,
  ExtrudeGeometry,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  Path,
  PlaneGeometry,
  Shape,
  Texture,
  Vector2,
  Vector3,
} from 'three';
import { contours, joint, seams, toWorld } from './geometry';
import { brushedRoughness, lineGlow, radialGlow } from './textures';
import type { Vec2 } from './types';
import { ease, range } from '../motion';

export const CORAL = new Color('#ff6548');

/** Параметры, которыми сцена настраивает экземпляр (основной или зеркальный). */
export interface BuildOptions {
  /** Зеркальное отражение на полу: темнее, без блеска и огней. */
  ghost: boolean;
}

interface Part {
  mesh: Mesh;
  material: MeshPhysicalMaterial;
  rest: Vector3;
  from: Vector3;
  spin: Vector3;
  window: [number, number];
  outline: LineSegments;
  accent: boolean;
}

export interface KModel {
  root: Group;
  /** Состояние модели в момент t хореографии (секунды). */
  apply(t: number): void;
  /** Свет узла для сцены (в экземпляре-призраке null). */
  lights: { joint: Vec2 } | null;
}

// — Вспомогательное —

function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Сдвиг выпуклого многоугольника внутрь на d (пересечение смещённых прямых). */
function inset(pts: Vec2[], d: number): Vec2[] {
  const n = pts.length;
  let area = 0;
  pts.forEach((p, i) => {
    const q = pts[(i + 1) % n]!;
    area += p[0] * q[1] - q[0] * p[1];
  });
  const sign = area > 0 ? 1 : -1;
  const lines = pts.map((p, i) => {
    const q = pts[(i + 1) % n]!;
    const dx = q[0] - p[0];
    const dy = q[1] - p[1];
    const len = Math.hypot(dx, dy);
    return { px: p[0] + ((-dy / len) * sign) * d, py: p[1] + ((dx / len) * sign) * d, dx, dy };
  });
  return pts.map((_, i) => {
    const a = lines[(i - 1 + n) % n]!;
    const b = lines[i]!;
    const det = a.dx * b.dy - a.dy * b.dx;
    const t = ((b.px - a.px) * b.dy - (b.py - a.py) * b.dx) / det;
    return [a.px + a.dx * t, a.py + a.dy * t] as Vec2;
  });
}

/** Плита по контуру (в мировых координатах) с фасками; центрирована по z на 0. */
function slab(outer: Vec2[], thickness: number, bevel: number, hole?: Vec2[]): ExtrudeGeometry {
  const shape = new Shape(outer.map((p) => new Vector2(p[0], p[1])));
  if (hole) shape.holes.push(new Path(hole.map((p) => new Vector2(p[0], p[1]))));
  const bt = Math.min(bevel, thickness / 2 - 0.002);
  const geo = new ExtrudeGeometry(shape, {
    depth: thickness - bt * 2,
    bevelEnabled: true,
    bevelThickness: bt,
    bevelSize: bevel,
    bevelOffset: -bevel,
    bevelSegments: 3,
    curveSegments: 1,
  });
  geo.translate(0, 0, -(thickness / 2 - bt));
  geo.computeVertexNormals();
  return geo;
}

const rect = (x0: number, y0: number, x1: number, y1: number): Vec2[] => [
  [x0, y0],
  [x1, y0],
  [x1, y1],
  [x0, y1],
];

/** Вершинное затемнение к узлу (окклюзия в стыке) — множитель к цвету материала. */
function shade(geo: ExtrudeGeometry | CylinderGeometry): void {
  const [jx, jy] = toWorld(joint);
  const pos = geo.getAttribute('position');
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const d = Math.hypot(pos.getX(i) - jx, pos.getY(i) - jy);
    const t = Math.min(1, d / 3.6);
    const v = 0.42 + 0.58 * t * t * (3 - 2 * t);
    colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = v;
  }
  geo.setAttribute('color', new Float32BufferAttribute(colors, 3));
}

const mapCache = new Map<string, Texture>();
let roughBase: Texture | null = null;

function metal(angle: number, tint: string, roughness: number, ghost: boolean): MeshPhysicalMaterial {
  roughBase ??= brushedRoughness();
  const key = angle.toFixed(2);
  let map = mapCache.get(key);
  if (!map) {
    map = roughBase.clone();
    map.needsUpdate = true;
    map.center.set(0.5, 0.5);
    map.rotation = angle;
    map.repeat.set(1.6, 1.6);
    mapCache.set(key, map);
  }
  const c = new Color(tint);
  if (ghost) c.multiplyScalar(0.55);
  return new MeshPhysicalMaterial({
    color: c,
    vertexColors: true,
    metalness: 1,
    roughness,
    roughnessMap: map,
    anisotropy: ghost ? 0 : 0.5,
    anisotropyRotation: angle,
    clearcoat: ghost ? 0 : 0.35,
    clearcoatRoughness: 0.25,
    envMapIntensity: ghost ? 0.7 : 1.1,
  });
}

/** Точка на «ленте» между двумя длинными сторонами четырёхугольника (A по P1→P2, B по P0→P3). */
function lerp2(a: Vec2, b: Vec2, t: number): Vec2 {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Фасетка на балке: четырёхугольник между сечениями t0..t1 по длине. q = [A0, A1, B1, B0]-контур. */
function facet(q: [Vec2, Vec2, Vec2, Vec2], t0: number, t1: number): Vec2[] {
  // q[0]-q[1] — сторона A (начало→конец), q[3]-q[2] — сторона B
  const a0 = lerp2(q[0], q[1], t0);
  const a1 = lerp2(q[0], q[1], t1);
  const b0 = lerp2(q[3], q[2], t0);
  const b1 = lerp2(q[3], q[2], t1);
  return [a0, a1, b1, b0];
}

// — Сборка модели —

export function buildK({ ghost }: BuildOptions): KModel {
  const root = new Group();
  const random = rng(20261102);
  const parts: Part[] = [];
  const gk = ghost ? 0.4 : 1;
  const glowTex = lineGlow();
  const radial = radialGlow();

  const dark = (angle: number) => metal(angle, '#8d929d', 0.48, ghost);
  const steel = (angle: number, tone = '#e4e5e4') => metal(angle, tone, 0.42, ghost);

  /** Добавляет деталь: геометрия строится в мировых координатах, затем центрируется для вращения «на месте». */
  function add(
    geo: ExtrudeGeometry | CylinderGeometry,
    material: MeshPhysicalMaterial,
    window: [number, number],
    scatter: number,
    opts: { accent?: boolean; offset?: [number, number, number] } = {},
  ): Mesh {
    const o = opts.offset ?? [0, 0, 0];
    geo.translate(o[0], o[1], o[2]);
    shade(geo);
    geo.computeBoundingBox();
    const c = geo.boundingBox!.getCenter(new Vector3());
    geo.translate(-c.x, -c.y, -c.z);
    const mesh = new Mesh(geo, material);
    mesh.position.copy(c);
    const dir = new Vector3(random() * 2 - 0.6, random() * 2 - 1, random() * 1.6 - 1.2).normalize();
    const from = dir.multiplyScalar(scatter * (0.7 + random() * 0.6));
    const spin = new Vector3((random() - 0.5) * 2.4, (random() - 0.5) * 2.4, (random() - 0.5) * 2.0).multiplyScalar(Math.min(1, scatter / 2.2));
    const outline = new LineSegments(
      new EdgesGeometry(geo, 25),
      new LineBasicMaterial({ color: opts.accent ? CORAL : 0xf3f0e9, transparent: true, opacity: 0, depthWrite: false }),
    );
    mesh.add(outline);
    root.add(mesh);
    parts.push({ mesh, material, rest: c.clone(), from, spin, window, outline, accent: !!opts.accent });
    return mesh;
  }

  // ═══ Опора: полая рама ═══
  const [sx0] = toWorld(contours.stem[0]);
  const [sx1] = toWorld(contours.stem[1]);
  const [, syTop] = toWorld(contours.stem[0]);
  const [, syBot] = toWorld(contours.stem[2]);
  const sw = sx1 - sx0;
  const cx = (sx0 + sx1) / 2;
  const rail = 0.17;
  const stemD = 0.78;
  const vert = Math.PI / 2;

  let w = 0.3;
  const stemWin = (): [number, number] => {
    const s = w;
    w += 0.12;
    return [s, s + 2.3];
  };
  add(slab(rect(sx0, syBot, sx0 + rail, syTop), stemD, 0.03), steel(vert), stemWin(), 1.6);
  add(slab(rect(sx1 - rail, syBot, sx1, syTop), stemD, 0.03), steel(vert), stemWin(), 1.6);
  add(slab(rect(sx0, syTop - rail, sx1, syTop), stemD - 0.04, 0.03), steel(0), stemWin(), 1.9);
  add(slab(rect(sx0, syBot, sx1, syBot + rail), stemD - 0.04, 0.03), steel(0), stemWin(), 1.9);
  add(slab(rect(sx0 + 0.05, syBot + 0.1, sx1 - 0.05, syTop - 0.1), 0.06, 0.012), dark(vert), stemWin(), 2.2, { offset: [0, 0, -0.32] });

  // Поперечные рёбра жёсткости внутри рамы (вокруг узла окно свободно)
  for (const y of [-1.95, -1.4, -0.85, 0.85, 1.4, 1.95]) {
    add(slab(rect(sx0 + rail - 0.01, y - 0.02, sx1 - rail + 0.01, y + 0.02), 0.52, 0.008), dark(0), stemWin(), 2.4, { offset: [0, 0, -0.04] });
  }
  // Центральная тяга и вертикальная внутренняя пластина
  const rod = new CylinderGeometry(0.032, 0.032, syTop - syBot - 0.5, 18);
  add(rod, steel(0, '#bfc2c6'), stemWin(), 2.6, { offset: [cx, 0, -0.14] });
  add(slab(rect(cx + 0.045, syBot + 0.5, cx + 0.105, syTop - 0.5), 0.34, 0.01), dark(vert), stemWin(), 2.4, { offset: [0, 0, 0.06] });

  // Ромб-стяжка в узле (тёмный металл с коралловой кромкой)
  const diamond: Vec2[] = [
    [cx, 0.4],
    [cx + 0.2, 0],
    [cx, -0.4],
    [cx - 0.2, 0],
  ];
  add(slab(diamond, 0.14, 0.022), dark(0), [2.5, 4.3], 3.0, { accent: true, offset: [0, 0, 0.1] });

  // ═══ Нижняя балка: массивная плита с фасетками ═══
  const lowerPts = contours.lower.map(toWorld) as Vec2[];
  const lowerIn = inset(lowerPts, 0.07);
  const lowerAngle = Math.atan2(lowerPts[2]![1] - lowerPts[1]![1], lowerPts[2]![0] - lowerPts[1]![0]);
  const lowerT = 0.62;
  const lowerZ = 0.06;
  add(slab(lowerPts, lowerT, 0.034), steel(-lowerAngle), [1.0, 3.5], 2.2, { offset: [0, 0, lowerZ] });
  const lq: [Vec2, Vec2, Vec2, Vec2] = [lowerIn[1]!, lowerIn[2]!, lowerIn[3]!, lowerIn[0]!];
  add(slab(facet(lq, 0.1, 0.55), 0.1, 0.02), steel(lowerAngle, '#f0f0ee'), [2.3, 4.2], 2.8, { offset: [0, 0, lowerZ + lowerT / 2 + 0.03] });
  add(slab(facet(lq, 0.62, 0.98), 0.1, 0.02), dark(lowerAngle), [2.5, 4.4], 2.8, { offset: [0, 0, lowerZ + lowerT / 2 + 0.03] });

  // ═══ Верхняя балка: рама с внутренними пластинами ═══
  const upperPts = contours.upper.map(toWorld) as Vec2[];
  const upperHole = inset(upperPts, 0.1);
  const upperAngle = Math.atan2(upperPts[1]![1] - upperPts[0]![1], upperPts[1]![0] - upperPts[0]![0]);
  const upperT = 0.46;
  const upperZ = -0.06;
  add(slab(upperPts, upperT, 0.03, upperHole), steel(upperAngle), [1.4, 3.9], 2.2, { offset: [0, 0, upperZ] });
  add(slab(upperHole, 0.04, 0.01), dark(upperAngle), [1.6, 4.0], 2.4, { offset: [0, 0, upperZ - 0.17] });
  const uq: [Vec2, Vec2, Vec2, Vec2] = [inset(upperPts, 0.16)[0]!, inset(upperPts, 0.16)[1]!, inset(upperPts, 0.16)[2]!, inset(upperPts, 0.16)[3]!];
  // Контур upper: P0→P1 — внешняя длинная сторона, P3→P2 — внутренняя; A = P0→P1, B = P3→P2
  add(slab(facet(uq, 0.08, 0.5), 0.14, 0.018), steel(upperAngle, '#d9dadb'), [2.1, 4.1], 2.8, { offset: [0, 0, upperZ - 0.02] });
  add(slab(facet(uq, 0.57, 0.95), 0.14, 0.018), dark(-upperAngle), [2.3, 4.3], 2.8, { offset: [0, 0, upperZ - 0.02] });

  // ═══ Детали узла: болты и штифты ═══
  const bolt = (x: number, y: number, z: number, win: [number, number]) => {
    const g = new CylinderGeometry(0.045, 0.045, 0.035, 6);
    g.rotateX(vert);
    add(g, steel(0, '#c9ccd0'), win, 3.4, { offset: [x, y, z] });
  };
  let bw = 2.6;
  for (const y of [-2.0, -1.2, 1.2, 2.0]) {
    bolt(sx0 + rail / 2, y, stemD / 2 + 0.01, [bw, bw + 1.5]);
    bolt(sx1 - rail / 2, y, stemD / 2 + 0.01, [bw + 0.15, bw + 1.65]);
    bw += 0.12;
  }
  // Штифт, пронизывающий опору в узле, с головками
  for (const y of [0.55, -0.55]) {
    const pin = new CylinderGeometry(0.03, 0.03, sw - 0.1, 14);
    pin.rotateZ(vert);
    add(pin, steel(0, '#d4d6d9'), [bw, bw + 1.4], 3.2, { offset: [cx, y, 0.02] });
    bw += 0.1;
  }

  // ═══ Свет: швы, узел ═══
  const upperFront = upperZ + upperT / 2 + 0.006;
  const lowerFront = lowerZ + lowerT / 2 + 0.006;
  const stemFront = stemD / 2 + 0.006;
  const seamDefs: { a: Vec2; b: Vec2; z: number; k: number }[] = [
    { a: seams.upper[0], b: seams.upper[1], z: upperFront, k: 1 },
    { a: seams.lower[0], b: seams.lower[1], z: lowerFront, k: 1 },
    { a: seams.stemUp[0], b: seams.stemUp[1], z: stemFront, k: 0.7 },
    { a: seams.stemDown[0], b: seams.stemDown[1], z: stemFront, k: 0.7 },
  ];
  const seamParts: { pivot: Group; core: Mesh; halo: Mesh; k: number }[] = seamDefs.map(({ a, b, z, k }) => {
    const [ax, ay] = toWorld(a);
    const [bx, by] = toWorld(b);
    const len = Math.hypot(bx - ax, by - ay);
    const pivot = new Group();
    pivot.position.set(ax, ay, z);
    pivot.rotation.z = Math.atan2(by - ay, bx - ax);
    const core = new Mesh(
      new PlaneGeometry(len, 0.024).translate(len / 2, 0, 0),
      new MeshBasicMaterial({ color: CORAL.clone().multiplyScalar(1.25), toneMapped: false, transparent: true, opacity: 0 }),
    );
    const halo = new Mesh(
      new PlaneGeometry(len + 0.2, 0.56).translate(len / 2, 0, 0.003),
      new MeshBasicMaterial({ map: glowTex, color: CORAL, transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
    );
    pivot.add(core, halo);
    root.add(pivot);
    return { pivot, core, halo, k };
  });

  // Ядро узла, ореол и горизонтальная вспышка
  const [jx, jy] = toWorld(joint);
  const core = new Mesh(new CircleGeometry(0.07, 40), new MeshBasicMaterial({ color: CORAL.clone().multiplyScalar(1.2), toneMapped: false, transparent: true, opacity: 0 }));
  core.position.set(jx + 0.02, jy, lowerFront + 0.07);
  const glow = new Mesh(
    new PlaneGeometry(1.9, 1.9),
    new MeshBasicMaterial({ map: radial, color: CORAL, transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
  );
  glow.position.set(jx + 0.02, jy, lowerFront + 0.06);
  const flare = new Mesh(
    new PlaneGeometry(4.2, 0.5),
    new MeshBasicMaterial({ map: radial, color: new Color('#ff9a80'), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
  );
  flare.position.set(jx + 0.4, jy, lowerFront + 0.065);
  root.add(core, glow, flare);

  const euler = new Euler();
  function apply(t: number): void {
    for (const p of parts) {
      const q = ease.outQuint(range(t, p.window[0], p.window[1]));
      const inv = 1 - q;
      p.mesh.position.set(p.rest.x + p.from.x * inv, p.rest.y + p.from.y * inv, p.rest.z + p.from.z * inv);
      euler.set(p.spin.x * inv, p.spin.y * inv, p.spin.z * inv);
      p.mesh.rotation.copy(euler);
      const fade = range(t, p.window[0], p.window[0] + 0.7);
      p.material.transparent = fade < 1;
      p.material.opacity = fade;
      const line = p.outline.material as LineBasicMaterial;
      const hold = p.accent ? 1 : 1 - ease.inOutCubic(range(t, 3.8, 5.2));
      line.opacity = (p.accent ? 0.85 : 0.65) * range(t, p.window[0] - 0.25, p.window[0] + 0.4) * hold * gk;
    }

    const ignite = ease.outCubic(range(t, 4.1, 5.0));
    const draw = ease.inOutCubic(range(t, 4.3, 5.5));
    const flicker = t < 5.2 ? 1 + Math.sin(t * 41) * 0.09 * (1 - ignite) : 1;
    (core.material as MeshBasicMaterial).opacity = ignite * gk;
    core.scale.setScalar(0.4 + 0.6 * ignite);
    (glow.material as MeshBasicMaterial).opacity = ignite * 0.8 * flicker * gk;
    glow.scale.setScalar(0.6 + 0.4 * ignite + 0.35 * (1 - range(t, 4.5, 5.8)) * ignite);
    (flare.material as MeshBasicMaterial).opacity = ignite * 0.4 * flicker * gk;
    flare.scale.set(0.5 + 0.5 * ignite, 1, 1);
    for (const s of seamParts) {
      s.pivot.scale.set(Math.max(0.0001, draw), 1, 1);
      (s.core.material as MeshBasicMaterial).opacity = range(t, 4.3, 4.6) * s.k * gk;
      (s.halo.material as MeshBasicMaterial).opacity = 0.75 * draw * s.k * gk;
    }
  }

  return { root, apply, lights: ghost ? null : { joint: [jx, jy] } };
}

