import { randomFrom } from '../lib/prng';
import type { BalancePoint } from '../types';

export type BalanceHistoryOptions = {
  seed: number;
  startEth: number;
  endEth: number;
  /** Minutes since session start that the realised series covers. */
  nowMin: number;
  /** Sampling interval in minutes. */
  stepMin?: number;
};

/**
 * A seeded random walk from `startEth` to `endEth` over `[0, nowMin]`.
 *
 * The walk is a *Brownian bridge*: a plain gaussian walk is re-anchored so it
 * lands exactly on `endEth`, which keeps the chart honest (it must end at the
 * live balance) while the middle stays organic. Values are clamped to the
 * chart's y-extent so the path never escapes the plot.
 */
export function generateBalanceHistory(opts: BalanceHistoryOptions): BalancePoint[] {
  const step = opts.stepMin ?? 4;
  const count = Math.max(2, Math.floor(opts.nowMin / step) + 1);
  const rng = randomFrom(opts.seed);

  // Unanchored walk.
  const walk: number[] = [0];
  for (let i = 1; i < count; i += 1) {
    walk.push((walk[i - 1] ?? 0) + rng.gaussian());
  }
  const walkEnd = walk[count - 1] ?? 0;

  const points: BalancePoint[] = [];
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    const min = Math.round(t * opts.nowMin);
    // Bridge: remove the walk's own drift, then add the linear start→end drift.
    const wobble = (walk[i] ?? 0) - walkEnd * t;
    const amplitude = 0.0009 * Math.sin(Math.PI * t); // pin both ends
    let eth = opts.startEth + (opts.endEth - opts.startEth) * t + wobble * amplitude;
    eth = Math.min(0.025, Math.max(0.0002, eth));
    points.push({ min, eth });
  }

  // Guarantee the exact endpoints the KPI and axis depend on.
  const first = points[0];
  const last = points[points.length - 1];
  if (first) first.eth = opts.startEth;
  if (last) {
    last.min = opts.nowMin;
    last.eth = opts.endEth;
  }
  return points;
}
