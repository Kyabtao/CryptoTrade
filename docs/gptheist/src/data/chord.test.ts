import { describe, expect, it } from 'vitest';
import { generateChordMatrix } from './chord';

describe('generateChordMatrix', () => {
  it('is deterministic', () => {
    expect(generateChordMatrix(111)).toEqual(generateChordMatrix(111));
  });

  it('is 10x10 with a zero diagonal and non-negative ints', () => {
    const { matrix, codes } = generateChordMatrix(111);
    expect(codes).toHaveLength(10);
    expect(matrix).toHaveLength(10);
    for (let i = 0; i < 10; i += 1) {
      expect(matrix[i]).toHaveLength(10);
      for (let j = 0; j < 10; j += 1) {
        const v = matrix[i]?.[j] ?? -1;
        expect(Number.isInteger(v)).toBe(true);
        expect(v).toBeGreaterThanOrEqual(0);
        if (i === j) expect(v).toBe(0);
      }
    }
  });

  it('has some flow (ribbons to draw)', () => {
    const { matrix } = generateChordMatrix(111);
    const total = matrix.flat().reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThan(20);
  });
});
