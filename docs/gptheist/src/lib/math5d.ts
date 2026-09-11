/**
 * 5-D geometry for the Strategy Lattice: the penteract (5-cube) has 32 vertices
 * (±1 in five axes) and 80 edges (pairs differing in exactly one axis). We
 * rotate it in two 5-D planes and orthographically project 5D → 2D. D3 is not
 * needed; this is pure, testable linear algebra.
 */

export type Vec5 = [number, number, number, number, number];
export type Vec2 = [number, number];

/** The 32 vertices of the 5-cube, in stable binary order. */
export function penteractVertices(): Vec5[] {
  const out: Vec5[] = [];
  for (let i = 0; i < 32; i += 1) {
    const v: number[] = [];
    for (let b = 0; b < 5; b += 1) v.push(i & (1 << b) ? 1 : -1);
    out.push(v as Vec5);
  }
  return out;
}

export type PenteractEdge = { a: number; b: number; axis: number };

/** The 80 edges: vertex pairs differing in exactly one bit (= one axis). */
export function penteractEdges(): PenteractEdge[] {
  const edges: PenteractEdge[] = [];
  for (let i = 0; i < 32; i += 1) {
    for (let axis = 0; axis < 5; axis += 1) {
      const j = i ^ (1 << axis);
      if (i < j) edges.push({ a: i, b: j, axis });
    }
  }
  return edges;
}

function rotatePlane(v: Vec5, p: 0 | 1 | 2 | 3 | 4, q: 0 | 1 | 2 | 3 | 4, angle: number): Vec5 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const out = [...v] as Vec5;
  out[p] = v[p] * c - v[q] * s;
  out[q] = v[p] * s + v[q] * c;
  return out;
}

/** Rotate in two 5-D planes: (0,1) by `a` and (2,3) by `b`. */
export function rotate5(v: Vec5, a: number, b: number): Vec5 {
  return rotatePlane(rotatePlane(v, 0, 1, a), 2, 3, b);
}

/** Fixed symmetric 5D→2D projection (petal angles 2πk/5). */
export function project5to2(v: Vec5): Vec2 {
  let x = 0;
  let y = 0;
  for (let k = 0; k < 5; k += 1) {
    const ang = (2 * Math.PI * k) / 5;
    x += (v[k] ?? 0) * Math.cos(ang);
    y += (v[k] ?? 0) * Math.sin(ang);
  }
  return [x / 2, y / 2];
}

/** Euclidean norm — rotation must preserve it. */
export function norm5(v: Vec5): number {
  return Math.sqrt(v.reduce((acc, c) => acc + c * c, 0));
}

const BASE_DEG = 263;
const SPEED_DEG_PER_S = 4;

/**
 * Worst-case projected coordinate over a full turn, so the SVG can scale with a
 * fixed factor and never clips mid-rotation. Computed once at module load.
 */
export const PENTERACT_BOUND: number = (() => {
  let m = 1;
  for (let d = 0; d < 360; d += 10) {
    const a = (d * Math.PI) / 180;
    for (const v of penteractVertices()) {
      const [x, y] = project5to2(rotate5(v, a, a * 0.6));
      m = Math.max(m, Math.abs(x), Math.abs(y));
    }
  }
  return m;
})();

/** Live rotation readout in whole degrees, 0–359. */
export function rotationDegAt(ms: number): number {
  const t = ms / 1000;
  return Math.round((BASE_DEG + t * SPEED_DEG_PER_S) % 360);
}

/** The two plane angles (radians) for a given timestamp. */
export function rotationAt(ms: number): { a: number; b: number } {
  const deg = rotationDegAt(ms);
  const a = (deg * Math.PI) / 180;
  return { a, b: a * 0.6 };
}
