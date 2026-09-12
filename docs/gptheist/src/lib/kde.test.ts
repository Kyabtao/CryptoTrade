import { describe, expect, it } from 'vitest';
import { erf, integrate, kde, normalCdf, phi } from './kde';

const grid: number[] = [];
for (let x = -4; x <= 4.001; x += 0.05) grid.push(x);

describe('phi', () => {
  it('is the standard normal pdf', () => {
    expect(phi(0)).toBeCloseTo(0.39894, 4);
    expect(phi(1)).toBeCloseTo(0.24197, 4);
  });
});

describe('kde', () => {
  it('integrates to ~1 (it is a density)', () => {
    const samples = [0.1, -0.2, 0.3, 0, -0.1, 0.2, 0.05, -0.05];
    const ys = kde(samples, 0.2, grid);
    expect(integrate(grid, ys)).toBeCloseTo(1, 1);
  });

  it('peaks near the sample mass', () => {
    const samples = Array.from({ length: 200 }, (_, i) => 0.5 + ((i % 7) - 3) * 0.05);
    const ys = kde(samples, 0.15, grid);
    const maxI = ys.indexOf(Math.max(...ys));
    expect(Math.abs((grid[maxI] ?? 0) - 0.5)).toBeLessThan(0.2);
  });

  it('returns zeros for empty input', () => {
    expect(kde([], 0.2, [0, 1, 2])).toEqual([0, 0, 0]);
  });
});

describe('normalCdf / erf', () => {
  it('matches textbook values', () => {
    expect(normalCdf(0)).toBeCloseTo(0.5, 5);
    expect(normalCdf(1.96)).toBeCloseTo(0.975, 2);
    expect(normalCdf(-1.96)).toBeCloseTo(0.025, 2);
    expect(erf(0)).toBeCloseTo(0, 6);
  });
});
