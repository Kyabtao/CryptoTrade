import { randomFrom } from '../lib/prng';
import { AGENTS } from './agents';
import type { AgentCode } from '../types';

export type ChordData = {
  /** 10x10 handoff counts, indexed by AGENTS order. */
  matrix: number[][];
  codes: AgentCode[];
};

/**
 * A seeded 10x10 handoff matrix. The diagonal is zero (nobody hands to
 * themselves) and flows are sparse-ish so the chord reads like the reference:
 * a web of grey ribbons with a few strong passes.
 */
export function generateChordMatrix(seed = 111): ChordData {
  const codes = AGENTS.map((a) => a.code);
  const rng = randomFrom(seed);
  const n = codes.length;
  const matrix: number[][] = Array.from({ length: n }, () => Array.from({ length: n }, () => 0));

  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j < n; j += 1) {
      if (i === j) continue;
      // Sparse: only some pairs hand off, weighted toward a few hot routes.
      if (rng.chance(0.45)) {
        const row = matrix[i] as number[];
        row[j] = rng.chance(0.2) ? rng.int(4, 9) : rng.int(1, 3);
      }
    }
  }
  return { matrix, codes };
}
