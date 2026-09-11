/**
 * Deterministic pseudo-random number generation.
 *
 * Every generator in `src/data/` draws from here rather than `Math.random`,
 * so the desk renders identically on every load (and is trivially testable).
 * ESLint bans `Math.random` project-wide to keep it that way.
 */

/** A callable generator of deterministic floats in `[0, 1)`. */
export type Rng = () => number;

/**
 * mulberry32 — a small, fast, well-distributed 32-bit PRNG.
 * Good enough for visual mock data; not a cryptographic source.
 */
export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Helpers bound to one stream, so generators read naturally. */
export type Random = {
  /** Uniform float in `[min, max)`. */
  float: (min: number, max: number) => number;
  /** Uniform integer in `[min, max]`, inclusive. */
  int: (min: number, max: number) => number;
  /** True with probability `p`. */
  chance: (p: number) => boolean;
  /** Standard normal (mean 0, sd 1) via the Box–Muller transform. */
  gaussian: () => number;
  /** Normal with a given mean and standard deviation. */
  normal: (mean: number, sd: number) => number;
  /** Uniform pick from a non-empty list. */
  pick: <T>(items: readonly T[]) => T;
  /** `count` picks with replacement. */
  picks: <T>(items: readonly T[], count: number) => T[];
  /** New array in shuffled order (Fisher–Yates); input is not mutated. */
  shuffle: <T>(items: readonly T[]) => T[];
  /** Clamp-free integer index into a list of `length` items. */
  index: (length: number) => number;
};

export function randomFrom(seed: number): Random {
  const next = mulberry32(seed);

  // Box–Muller needs a spare: generate in pairs, hand back one at a time.
  let spare: number | null = null;
  const gaussian = (): number => {
    if (spare !== null) {
      const value = spare;
      spare = null;
      return value;
    }
    let u = 0;
    let v = 0;
    let s = 0;
    do {
      u = next() * 2 - 1;
      v = next() * 2 - 1;
      s = u * u + v * v;
    } while (s === 0 || s >= 1);
    const mul = Math.sqrt((-2 * Math.log(s)) / s);
    spare = v * mul;
    return u * mul;
  };

  // Generic helpers are declared (not written inline as arrow properties) so
  // each keeps its own type parameter; an object literal cannot introduce one.
  function pick<T>(items: readonly T[]): T {
    if (items.length === 0) throw new Error('pick(): cannot sample from an empty list');
    return items[Math.floor(next() * items.length)] as T;
  }

  function picks<T>(items: readonly T[], count: number): T[] {
    const out: T[] = [];
    for (let i = 0; i < count; i += 1) out.push(pick(items));
    return out;
  }

  function shuffle<T>(items: readonly T[]): T[] {
    const out = [...items];
    for (let i = out.length - 1; i > 0; i -= 1) {
      const j = Math.floor(next() * (i + 1));
      const tmp = out[i] as T;
      out[i] = out[j] as T;
      out[j] = tmp;
    }
    return out;
  }

  return {
    float: (min, max) => min + next() * (max - min),
    int: (min, max) => min + Math.floor(next() * (max - min + 1)),
    chance: (p) => next() < p,
    gaussian,
    normal: (mean, sd) => mean + gaussian() * sd,
    pick,
    picks,
    shuffle,
    index: (length) => Math.floor(next() * length),
  };
}

/** Stable 32-bit hash of a string, for naming seeds ("ridge:1363"). */
export function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
