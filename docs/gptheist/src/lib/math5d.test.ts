import { describe, expect, it } from 'vitest';
import {
  norm5,
  penteractEdges,
  penteractVertices,
  project5to2,
  PENTERACT_BOUND,
  rotate5,
  rotationAt,
  rotationDegAt,
} from './math5d';

describe('penteract geometry', () => {
  it('has 32 vertices of ±1', () => {
    const v = penteractVertices();
    expect(v).toHaveLength(32);
    for (const vec of v) for (const c of vec) expect(Math.abs(c)).toBe(1);
  });

  it('has exactly 80 edges, 16 per axis', () => {
    const e = penteractEdges();
    expect(e).toHaveLength(80);
    const perAxis = [0, 0, 0, 0, 0];
    for (const edge of e) perAxis[edge.axis] = (perAxis[edge.axis] ?? 0) + 1;
    expect(perAxis).toEqual([16, 16, 16, 16, 16]);
  });

  it('rotation preserves the 5-D norm', () => {
    for (const v of penteractVertices().slice(0, 8)) {
      const r = rotate5(v, 0.7, 0.3);
      expect(norm5(r)).toBeCloseTo(norm5(v), 8);
    }
  });

  it('projection is finite and bounded by PENTERACT_BOUND', () => {
    for (const v of penteractVertices()) {
      const [x, y] = project5to2(rotate5(v, 1.1, 0.4));
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
      expect(Math.abs(x)).toBeLessThanOrEqual(PENTERACT_BOUND + 1e-9);
      expect(Math.abs(y)).toBeLessThanOrEqual(PENTERACT_BOUND + 1e-9);
    }
  });
});

describe('rotation', () => {
  it('starts at the reference 263° and stays in range', () => {
    expect(rotationDegAt(0)).toBe(263);
    expect(rotationDegAt(10_000)).toBeGreaterThanOrEqual(0);
    expect(rotationDegAt(10_000)).toBeLessThan(360);
  });

  it('advances over time', () => {
    expect(rotationDegAt(5000)).not.toBe(rotationDegAt(0));
  });

  it('returns radians consistent with the degree readout', () => {
    const { a } = rotationAt(0);
    expect(a).toBeCloseTo((263 * Math.PI) / 180, 6);
  });
});
