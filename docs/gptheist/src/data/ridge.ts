import { kde } from '../lib/kde';
import { randomFrom } from '../lib/prng';

export type RidgeCurve = {
  session: number;
  /** Density curve, peak-normalised to 1 for consistent ridge heights. */
  curve: { x: number; y: number }[];
  /** Monte-Carlo P(sample > strike) for this session. */
  tailP: number;
};

export type RidgeData = {
  ridges: RidgeCurve[];
  /** Shared σ-grid the curves are evaluated on. */
  grid: number[];
  /** Strike position in σ units. */
  strike: number;
  /** The highlighted (topmost) session. */
  activeSession: number;
};

export const RIDGE_GRID: number[] = (() => {
  const out: number[] = [];
  for (let x = -3; x <= 3.0001; x += 0.075) out.push(Number(x.toFixed(3)));
  return out;
})();

export type RidgeOptions = {
  seed: number;
  count?: number;
  firstSession?: number;
  strike?: number;
};

/**
 * One ridge per session: samples drawn from a body normal plus a small
 * right-tail bump, smoothed with a Gaussian kernel. The tail bump is what makes
 * "price the tail" meaningful — P(>strike) is measured off the raw samples.
 */
export function generateRidgeData(opts: RidgeOptions): RidgeData {
  const count = opts.count ?? 24;
  const firstSession = opts.firstSession ?? 1340;
  const strike = opts.strike ?? 1.5;
  const rng = randomFrom(opts.seed);

  const ridges: RidgeCurve[] = [];
  for (let i = 0; i < count; i += 1) {
    const session = firstSession + i;
    // Tight bodies + a small bump beyond the strike: tails stay in the few-%
    // range the reference shows, yet every ridge has a visible pink tail.
    const mean = rng.normal(0.0, 0.12);
    const sd = rng.float(0.45, 0.75);
    const bumpMean = strike + rng.float(0.15, 0.5);
    const bumpSd = rng.float(0.2, 0.35);
    const bumpShare = rng.float(0.03, 0.08);

    const samples: number[] = [];
    const n = 220;
    for (let s = 0; s < n; s += 1) {
      samples.push(rng.chance(bumpShare) ? rng.normal(bumpMean, bumpSd) : rng.normal(mean, sd));
    }

    const raw = kde(samples, 0.18, RIDGE_GRID);
    const peak = Math.max(...raw, 1e-9);
    const curve = RIDGE_GRID.map((x, k) => ({ x, y: (raw[k] ?? 0) / peak }));
    const over = samples.filter((v) => v > strike).length;
    ridges.push({ session, curve, tailP: over / n });
  }

  return {
    ridges,
    grid: RIDGE_GRID,
    strike,
    activeSession: firstSession + count - 1,
  };
}
