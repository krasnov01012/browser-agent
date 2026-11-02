/*
 * Модель «Modular K» (v03): семь металлических модулей с реальными щелями, свет из щелей и световые
 * вставки балок, обводка-«трассировка» при включении, строительные линии и пролетающие детали.
 * Геометрия — modular.ts. Хореография повторяет ролик владельца (см. scene.ts):
 *   модули влетают из-за камеры → зависают «взрыв-схемой» под строительными линиями → стыкуются →
 *   по контурам пробегает свет → остаются светящиеся щели.
 */
import {
  AdditiveBlending,
  BoxGeometry,
  BufferGeometry,
  Color,
  EdgesGeometry,
  Euler,
  ExtrudeGeometry,
  Float32BufferAttribute,
  Group,
  Line,
  LineBasicMaterial,
  LineLoop,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  PlaneGeometry,
  Shape,
  Texture,
  Vector2,
  Vector3,
} from 'three';
import { toWorld } from './geometry';
import { constructionLines, gapSeams, inlays, modules, nodePoint, type ModuleDef } from './modular';
import { bandGlow, radialGlow, scratchedMetal } from './textures';
import type { Vec2 } from './types';
import { ease, range } from '../motion';

export const CORAL = new Color('#ff6548');
const HOT = new Color('#ffc4a3');

export interface BuildOptions {
  /** Зеркальное отражение на полу: темнее, без строительных линий и пролетающих деталей. */
  ghost: boolean;
}

export interface KModel {
  root: Group;
  apply(t: number): void;
  /** Точки для коралловых источников света (в координатах модели); у отражения — null. */
  lights: { node: Vec2; spill: Vec2[] } | null;
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

const W = (p: Vec2): Vec2 => toWorld(p);

/** Плита по контуру с плоской фаской (как фрезерованная кромка); центрирована по z. */
function slab(points: Vec2[], thickness: number, bevel = 0.026): ExtrudeGeometry {
  const shape = new Shape(points.map((p) => new Vector2(p[0], p[1])));
  const bt = Math.min(bevel, thickness / 2 - 0.002);
  const geo = new ExtrudeGeometry(shape, {
    depth: thickness - bt * 2,
    bevelEnabled: true,
    bevelThickness: bt,
    bevelSize: bevel,
    bevelOffset: -bevel,
    bevelSegments: 1,
    curveSegments: 1,
  });
  geo.translate(0, 0, -(thickness / 2 - bt));
  geo.computeVertexNormals();
  return geo;
}

/** Мягкое затемнение к узлу (окклюзия в стыке): множитель цвета 0.7–1. */
function shade(geo: BufferGeometry): void {
  const [nx, ny] = W(nodePoint);
  const pos = geo.getAttribute('position');
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const t = Math.min(1, Math.hypot(pos.getX(i) - nx, pos.getY(i) - ny) / 3);
    const v = 0.7 + 0.3 * t * t * (3 - 2 * t);
    colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = v;
  }
  geo.setAttribute('color', new Float32BufferAttribute(colors, 3));
}

let metalMaps: ReturnType<typeof scratchedMetal> | null = null;
const mapClones = new Map<string, Texture[]>();

/** Матовый потёртый металл. Карты общие, у каждого направления шлифовки — свой поворот UV. */
function metal(angle: number, tint: string, ghost: boolean): MeshPhysicalMaterial {
  metalMaps ??= scratchedMetal();
  const key = angle.toFixed(2);
  let maps = mapClones.get(key);
  if (!maps) {
    maps = [metalMaps.map, metalMaps.roughness, metalMaps.bump].map((src) => {
      const t = src.clone();
      t.needsUpdate = true;
      t.repeat.set(0.42, 0.42);
      t.rotation = angle;
      return t;
    });
    mapClones.set(key, maps);
  }
  const c = new Color(tint);
  if (ghost) c.multiplyScalar(0.5);
  return new MeshPhysicalMaterial({
    color: c,
    map: maps[0]!,
    vertexColors: true,
    metalness: 1,
    roughness: 1,
    roughnessMap: maps[1]!,
    bumpMap: ghost ? null : maps[2]!,
    bumpScale: 1.2,
    envMapIntensity: ghost ? 0.55 : 1.05,
  });
}

/** Светящаяся линия-ломаная: ядро + ореол по каждому отрезку, прорисовывается по длине. */
class GlowPath {
  readonly group = new Group();
  private segs: { pivot: Group; core: MeshBasicMaterial; halo: MeshBasicMaterial; len: number; start: number }[] = [];
  private total = 0;

  constructor(points: Vec2[], z: number, opts: { core: number; halo: number; haloZ?: number; tex: Texture; closed?: boolean }) {
    const pts = opts.closed ? [...points, points[0]!] : points;
    for (let i = 0; i < pts.length - 1; i++) {
      const [ax, ay] = pts[i]!;
      const [bx, by] = pts[i + 1]!;
      const len = Math.hypot(bx - ax, by - ay);
      const pivot = new Group();
      pivot.position.set(ax, ay, z);
      pivot.rotation.z = Math.atan2(by - ay, bx - ax);
      // Ядро «горячее» (почти белое с оранжевым), ореол — фирменный коралл: так светится щель в ролике
      const core = new MeshBasicMaterial({ color: HOT, transparent: true, opacity: 0, toneMapped: false, depthWrite: false });
      const halo = new MeshBasicMaterial({ map: opts.tex, color: CORAL, transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false });
      pivot.add(new Mesh(new PlaneGeometry(len + opts.core, opts.core).translate(len / 2, 0, 0), core));
      const haloMesh = new Mesh(new PlaneGeometry(len + opts.halo * 0.6, opts.halo).translate(len / 2, 0, (opts.haloZ ?? z) - z), halo);
      haloMesh.renderOrder = 4;
      pivot.add(haloMesh);
      this.group.add(pivot);
      this.segs.push({ pivot, core, halo, len, start: this.total });
      this.total += len;
    }
  }

  /** progress 0..1 — прорисовано по длине; intensity — общая яркость. */
  set(progress: number, intensity: number, haloK = 0.75): void {
    const head = progress * this.total;
    for (const s of this.segs) {
      const local = Math.min(1, Math.max(0, (head - s.start) / s.len));
      s.pivot.visible = local > 0 && intensity > 0.001;
      s.pivot.scale.x = Math.max(0.0001, local);
      s.core.opacity = intensity;
      s.halo.opacity = intensity * haloK;
    }
  }
}

interface Part {
  mesh: Mesh;
  material: MeshPhysicalMaterial;
  rest: Vector3;
  from: Vector3;
  exploded: Vector3;
  spin: Vector3;
  tilt: Vector3;
  /** [появление, «взрыв-схема», начало стыковки, конец стыковки] */
  t: [number, number, number, number];
  edges: LineSegments;
}

// — Сборка модели —

export function buildK({ ghost }: BuildOptions): KModel {
  const root = new Group();
  const random = rng(20261102);
  const gk = ghost ? 0.4 : 1;
  const band = bandGlow();
  const parts: Part[] = [];
  const front = new Map<ModuleDef['id'], number>();

  // ═══ Модули ═══
  modules.forEach((m, i) => {
    const pts = m.points.map(W);
    const geo = slab(pts, m.depth);
    shade(geo);
    geo.computeBoundingBox();
    const c = geo.boundingBox!.getCenter(new Vector3());
    geo.translate(-c.x, -c.y, -c.z);
    const material = metal(m.brush, m.id.startsWith('A') ? '#dcdddf' : '#d2d4d6', ghost);
    const mesh = new Mesh(geo, material);
    mesh.position.copy(c);
    root.add(mesh);
    front.set(m.id, m.depth / 2);

    // Влёт из-за камеры: с края кадра и «перед» знаком, с сильным вращением
    const side = c.x >= 0 ? 1 : -1;
    const from = new Vector3(side * (1.4 + random() * 1.4), (random() - 0.5) * 3.2, 2.5 + random() * 2);
    // «Взрыв-схема»: модули зависают чуть отодвинутыми от центра и выдвинутыми к камере
    const exploded = new Vector3(c.x * 0.32 + (random() - 0.5) * 0.25, c.y * 0.3 + (random() - 0.5) * 0.25, 0.5 + random() * 0.6);
    const spin = new Vector3((random() - 0.5) * 5, (random() - 0.5) * 5, (random() - 0.5) * 3);
    const tilt = new Vector3((random() - 0.5) * 0.35, (random() - 0.5) * 0.5, (random() - 0.5) * 0.18);
    const s = 0.25 + i * 0.13;
    const c0 = 3.3 + i * 0.09;
    const edges = new LineSegments(
      new EdgesGeometry(geo, 25),
      new LineBasicMaterial({ color: 0xf3f0e9, transparent: true, opacity: 0, depthWrite: false }),
    );
    mesh.add(edges);
    parts.push({ mesh, material, rest: c.clone(), from, exploded, spin, tilt, t: [s, 2.3 + i * 0.07, c0, c0 + 0.5], edges });
  });

  // ═══ Свет: щели опоры (изнутри), вставки балок (на лицевой стороне), обводка модулей ═══
  const stemFront = 0.31;
  const gaps = gapSeams.map((p) => new GlowPath(p.map(W), 0.1, { core: 0.022, halo: 0.17, haloZ: stemFront + 0.02, tex: band }));
  const inlayPaths = inlays.map(({ id, points }) => new GlowPath(points.map(W), front.get(id)! + 0.004, { core: 0.018, halo: 0.16, tex: band }));
  const outlines = modules.map((m) => new GlowPath(m.points.map(W), m.depth / 2 + 0.006, { core: 0.014, halo: 0.14, tex: band, closed: true }));
  for (const g of [...gaps, ...inlayPaths, ...outlines]) root.add(g.group);

  // Узел: мягкое свечение в пазу между балками
  const [nx, ny] = W(nodePoint);
  const nodeGlow = new Mesh(
    new PlaneGeometry(1.5, 1.1),
    new MeshBasicMaterial({ map: radialGlow(), color: CORAL, transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false, toneMapped: false }),
  );
  nodeGlow.position.set(nx, ny, 0.2);
  root.add(nodeGlow);

  // ═══ Строительные линии этапа «выравнивание» и пролетающие детали (только у основной модели) ═══
  const lines: { obj: Line; mat: LineBasicMaterial; delay: number }[] = [];
  const debris: { mesh: Mesh; a: Vector3; b: Vector3; spin: Vector3; t: [number, number] }[] = [];
  let ring: LineLoop | null = null;
  if (!ghost) {
    constructionLines.forEach(([a, b], i) => {
      const [ax, ay] = W(a);
      const [bx, by] = W(b);
      const geo = new BufferGeometry().setFromPoints([new Vector3(ax, ay, 0.36), new Vector3(bx, by, 0.36)]);
      const mat = new LineBasicMaterial({ color: CORAL, transparent: true, opacity: 0, depthWrite: false });
      const obj = new Line(geo, mat);
      root.add(obj);
      lines.push({ obj, mat, delay: i * 0.1 });
    });
    const pts: Vector3[] = [];
    for (let i = 0; i < 128; i++) {
      const a = (i / 128) * Math.PI * 2;
      pts.push(new Vector3(nx + Math.cos(a) * 2.5, ny + Math.sin(a) * 2.5, 0.36));
    }
    ring = new LineLoop(new BufferGeometry().setFromPoints(pts), new LineBasicMaterial({ color: 0x9aa0b4, transparent: true, opacity: 0, depthWrite: false }));
    root.add(ring);

    const debrisMat = metal(0, '#bfc1c4', false);
    for (let i = 0; i < 14; i++) {
      const sx = 0.06 + random() * 0.22;
      const mesh = new Mesh(new BoxGeometry(sx, sx * (0.4 + random() * 2.4), 0.06 + random() * 0.2), debrisMat.clone());
      shade(mesh.geometry);
      const a = new Vector3((random() - 0.5) * 5, (random() - 0.5) * 3.6, 4 + random() * 2);
      const b = new Vector3(a.x * 1.6 + (random() - 0.5) * 2, a.y * 1.6 + (random() - 0.5) * 2, -6 - random() * 4);
      const s = 0.2 + random() * 1.6;
      debris.push({ mesh, a, b, spin: new Vector3(random() * 6, random() * 6, random() * 4), t: [s, s + 1.4 + random() * 0.8] });
      root.add(mesh);
    }
  }

  const euler = new Euler();
  const tmp = new Vector3();

  function apply(t: number): void {
    // — Модули —
    for (const p of parts) {
      const [s, e, c0, c1] = p.t;
      const fly = ease.outCubic(range(t, s, e));
      const dock = ease.inOutCubic(range(t, c0, c1));
      tmp.lerpVectors(p.from, p.exploded, fly);
      // На «взрыв-схеме» модуль медленно дрейфует, пока не начнётся стыковка
      tmp.z += 0.12 * Math.sin((t - s) * 1.3) * (1 - dock) * fly;
      p.mesh.position.set(p.rest.x + tmp.x * (1 - dock), p.rest.y + tmp.y * (1 - dock), p.rest.z + tmp.z * (1 - dock));
      const inv = 1 - fly;
      euler.set(
        (p.spin.x * inv + p.tilt.x * fly) * (1 - dock),
        (p.spin.y * inv + p.tilt.y * fly) * (1 - dock),
        (p.spin.z * inv + p.tilt.z * fly) * (1 - dock),
      );
      p.mesh.rotation.copy(euler);
      const fade = range(t, s, s + 0.45);
      p.material.transparent = fade < 1;
      p.material.opacity = fade;
      p.mesh.visible = fade > 0;
      (p.edges.material as LineBasicMaterial).opacity = 0.45 * range(t, s, s + 0.3) * (1 - range(t, e - 0.6, e + 0.4)) * gk;
    }

    // — Строительные линии: прорисовка на «взрыв-схеме», уход при стыковке —
    for (const l of lines) {
      const draw = ease.outCubic(range(t, 2.1 + l.delay, 2.9 + l.delay));
      l.obj.visible = draw > 0;
      l.mat.opacity = 0.75 * draw * (1 - range(t, 4.2, 5.0));
    }
    if (ring) {
      const draw = ease.inOutCubic(range(t, 2.2, 3.4));
      ring.geometry.setDrawRange(0, Math.round(128 * draw));
      (ring.material as LineBasicMaterial).opacity = 0.45 * (1 - range(t, 4.3, 5.1));
    }

    // — Пролетающие детали —
    for (const d of debris) {
      const k = range(t, d.t[0], d.t[1]);
      d.mesh.visible = k > 0 && k < 1;
      d.mesh.position.lerpVectors(d.a, d.b, ease.inOutCubic(k));
      d.mesh.rotation.set(d.spin.x * k, d.spin.y * k, d.spin.z * k);
      const m = d.mesh.material as MeshPhysicalMaterial;
      m.transparent = true;
      m.opacity = Math.min(range(k, 0, 0.15), 1 - range(k, 0.7, 1));
    }

    // — Свет: пробег по контурам → светящиеся щели —
    const trace = ease.inOutCubic(range(t, 4.25, 5.15));
    const traceFade = 1 - ease.inOutCubic(range(t, 5.3, 6.4));
    for (const o of outlines) o.set(trace, 0.95 * traceFade * gk, 0.6);
    const seam = ease.inOutCubic(range(t, 4.8, 5.8));
    const flicker = t < 5.4 ? 1 + Math.sin(t * 43) * 0.08 * (1 - seam) : 1;
    for (const g of gaps) g.set(seam, flicker * gk, 0.8);
    for (const g of inlayPaths) g.set(seam, flicker * gk, 0.7);
    (nodeGlow.material as MeshBasicMaterial).opacity = 0.55 * seam * flicker * gk;
  }

  const spill: Vec2[] = [W([600, 330]), W([560, 700]), W([343, 420]), W([230, 560])];
  return { root, apply, lights: ghost ? null : { node: [nx, ny], spill } };
}
