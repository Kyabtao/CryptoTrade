import { describe, expect, it } from 'vitest';
import { hashSeed, mulberry32, randomFrom } from './prng';

describe('mulberry32', () => {
  it('is deterministic for a given seed', () => {
    const a = mulberry32(1234);
    const b = mulberry32(1234);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });

  it('produces different streams for different seeds', () => {
    expect(mulberry32(1)()).not.toEqual(mulberry32(2)());
  });

  it('stays inside [0, 1) over a long run', () => {
    const rng = mulberry32(99);
    for (let i = 0; i < 20_000; i += 1) {
      const v = rng();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe('randomFrom', () => {
  it('respects float and int bounds (inclusive)', () => {
    const r = randomFrom(7);
    for (let i = 0; i < 5_000; i += 1) {
      const f = r.float(-1, 1);
      expect(f).toBeGreaterThanOrEqual(-1);
      expect(f).toBeLessThan(1);

      const n = r.int(3, 6);
      expect([3, 4, 5, 6]).toContain(n);
    }
  });

  it('reproduces a gaussian stream exactly', () => {
    const a = randomFrom(42);
    const b = randomFrom(42);
    const xs = Array.from({ length: 50 }, () => a.gaussian());
    const ys = Array.from({ length: 50 }, () => b.gaussian());
    expect(xs).toEqual(ys);
  });

  it('generates gaussians that are roughly standard normal', () => {
    const r = randomFrom(2024);
    const n = 40_000;
    let sum = 0;
    let squares = 0;
    for (let i = 0; i < n; i += 1) {
      const v = r.gaussian();
      sum += v;
      squares += v * v;
    }
    const mean = sum / n;
    const variance = squares / n - mean * mean;
    expect(Math.abs(mean)).toBeLessThan(0.05);
    expect(Math.abs(variance - 1)).toBeLessThan(0.1);
  });

  it('shuffle permutes without losing or duplicating items', () => {
    const r = randomFrom(5);
    const source = [1, 2, 3, 4, 5, 6, 7, 8];
    const out = r.shuffle(source);
    expect([...out].sort((a, b) => a - b)).toEqual(source);
    // The input array must be left untouched.
    expect(source).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it('pick draws only from the provided list', () => {
    const r = randomFrom(11);
    const pool = ['TOKY', 'PALM', 'RIO'] as const;
    for (let i = 0; i < 200; i += 1) {
      expect(pool).toContain(r.pick(pool));
    }
  });

  it('throws rather than returning undefined on an empty pool', () => {
    expect(() => randomFrom(1).pick([])).toThrow(/empty list/);
  });

  it('index stays within bounds', () => {
    const r = randomFrom(3);
    for (let i = 0; i < 1_000; i += 1) {
      const n = r.index(10);
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThan(10);
    }
  });
});

describe('hashSeed', () => {
  it('is stable and unsigned 32-bit', () => {
    const a = hashSeed('ridge:1363');
    expect(a).toBe(hashSeed('ridge:1363'));
    expect(Number.isInteger(a)).toBe(true);
    expect(a).toBeGreaterThanOrEqual(0);
    expect(a).toBeLessThanOrEqual(0xffffffff);
  });

  it('separates nearby names', () => {
    expect(hashSeed('ridge:1363')).not.toBe(hashSeed('ridge:1364'));
  });
});
