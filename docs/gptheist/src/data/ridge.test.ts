import { describe, expect, it } from 'vitest';
import { generateRidgeData } from './ridge';

describe('generateRidgeData', () => {
  it('is deterministic for a seed', () => {
    expect(generateRidgeData({ seed: 5 })).toEqual(generateRidgeData({ seed: 5 }));
  });

  it('produces 24 sequential sessions ending at the active one', () => {
    const d = generateRidgeData({ seed: 5 });
    expect(d.ridges).toHaveLength(24);
    expect(d.ridges[0]?.session).toBe(1340);
    expect(d.activeSession).toBe(1363);
  });

  it('peak-normalises every curve and keeps tails plausible', () => {
    const d = generateRidgeData({ seed: 5 });
    for (const r of d.ridges) {
      const max = Math.max(...r.curve.map((p) => p.y));
      expect(max).toBeCloseTo(1, 5);
      expect(r.tailP).toBeGreaterThan(0);
      expect(r.tailP).toBeLessThan(0.15);
    }
  });
});
