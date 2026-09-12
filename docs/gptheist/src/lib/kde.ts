/**
 * Kernel density estimation for the Tail Probability Ridge.
 *
 * A ridge is a stack of per-session density curves. Each session's samples are
 * smoothed with a Gaussian kernel over a fixed σ-grid; D3 is not needed here —
 * the math is small and easier to test in isolation.
 */

const INV_SQRT_2PI = 1 / Math.sqrt(2 * Math.PI);

/** Standard normal pdf. */
export function phi(x: number): number {
  return INV_SQRT_2PI * Math.exp(-0.5 * x * x);
}

/**
 * Gaussian-kernel density estimate of `samples` evaluated at each grid point.
 * `bandwidth` is in the same units as the samples (σ for the ridge).
 */
export function kde(
  samples: readonly number[],
  bandwidth: number,
  grid: readonly number[]
): number[] {
  if (samples.length === 0) return grid.map(() => 0);
  const h = Math.max(1e-6, bandwidth);
  const n = samples.length;
  return grid.map((g) => {
    let acc = 0;
    for (let i = 0; i < n; i += 1) {
      acc += phi((g - (samples[i] ?? 0)) / h);
    }
    return acc / (n * h);
  });
}

/** Trapezoid integral — used to sanity-check that a density is a density. */
export function integrate(xs: readonly number[], ys: readonly number[]): number {
  let acc = 0;
  for (let i = 1; i < xs.length; i += 1) {
    const dx = (xs[i] ?? 0) - (xs[i - 1] ?? 0);
    acc += 0.5 * dx * ((ys[i] ?? 0) + (ys[i - 1] ?? 0));
  }
  return acc;
}

/** Abramowitz–Stegun erf approximation (|error| < 1.5e-7) — plenty for tails. */
export function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-ax * ax);
  return sign * y;
}

/** Standard normal CDF. */
export function normalCdf(x: number, mean = 0, sd = 1): number {
  return 0.5 * (1 + erf((x - mean) / (sd * Math.SQRT2)));
}
