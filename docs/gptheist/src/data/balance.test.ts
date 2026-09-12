import { describe, expect, it } from 'vitest';
import { generateBalanceHistory } from './balance';

const OPTS = { seed: 9, startEth: 0.0156, endEth: 0.0189, nowMin: 163 };

describe('generateBalanceHistory', () => {
  it('is deterministic for a given seed', () => {
    expect(generateBalanceHistory(OPTS)).toEqual(generateBalanceHistory(OPTS));
  });

  it('starts and ends exactly on the pinned balances', () => {
    const pts = generateBalanceHistory(OPTS);
    expect(pts[0]?.eth).toBe(0.0156);
    expect(pts[pts.length - 1]?.eth).toBe(0.0189);
    expect(pts[pts.length - 1]?.min).toBe(163);
  });

  it('stays inside the chart y-extent and moves forward in time', () => {
    const pts = generateBalanceHistory(OPTS);
    for (let i = 0; i < pts.length; i += 1) {
      const p = pts[i];
      expect(p).toBeDefined();
      if (!p) continue;
      expect(p.eth).toBeGreaterThanOrEqual(0);
      expect(p.eth).toBeLessThanOrEqual(0.025);
      if (i > 0) expect(p.min).toBeGreaterThanOrEqual((pts[i - 1] as { min: number }).min);
    }
  });

  it('is not a straight line (the walk is organic)', () => {
    const pts = generateBalanceHistory(OPTS);
    const values = new Set(pts.map((p) => p.eth));
    expect(values.size).toBeGreaterThan(10);
  });
});
