import { describe, expect, it } from 'vitest';
import { EVENT_TEMPLATES, generateInitialEvents, makeLiveEvent } from './events';
import { randomFrom } from '../lib/prng';

const toMin = (t: string): number => {
  const [h, m] = t.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

describe('generateInitialEvents', () => {
  it('returns the requested count, newest first', () => {
    const ev = generateInitialEvents({ seed: 3, count: 40, latestMin: 18 * 60 + 43 });
    expect(ev).toHaveLength(40);
  });

  it('pins the newest event to RIO marking an invalidation', () => {
    const ev = generateInitialEvents({ seed: 3, count: 40, latestMin: 18 * 60 + 43 });
    const first = ev[0];
    expect(first?.code).toBe('RIO');
    expect(first?.message).toBe('pullback / invalidation marked');
    expect(first?.tone).toBe('neg');
    expect(first?.time).toBe('18:43');
  });

  it('walks backwards with realistic 1-6 minute gaps and descending ids', () => {
    const ev = generateInitialEvents({ seed: 5, count: 40, latestMin: 18 * 60 + 43 });
    for (let i = 1; i < ev.length; i += 1) {
      const prev = ev[i - 1];
      const cur = ev[i];
      if (!prev || !cur) continue;
      const gap = toMin(prev.time) - toMin(cur.time);
      expect(gap).toBeGreaterThanOrEqual(1);
      expect(gap).toBeLessThanOrEqual(6);
      expect(cur.id).toBe(prev.id - 1);
    }
  });

  it('only uses known codes and their templates', () => {
    const ev = generateInitialEvents({ seed: 8, count: 60, latestMin: 18 * 60 + 43 });
    for (const e of ev) {
      expect(EVENT_TEMPLATES[e.code]).toContain(e.message);
    }
  });
});

describe('makeLiveEvent', () => {
  it('produces a well-formed event at the given minute', () => {
    const rng = randomFrom(1);
    const e = makeLiveEvent(rng, 200, 18 * 60 + 48);
    expect(e.id).toBe(200);
    expect(e.time).toBe('18:48');
    expect(EVENT_TEMPLATES[e.code]).toContain(e.message);
  });
});
