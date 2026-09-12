import { describe, expect, it } from 'vitest';
import { createDeskStore } from './deskStore';

describe('deskStore', () => {
  it('initialises from the reference snapshot', () => {
    const s = createDeskStore(7).getState();
    expect(s.eventCount).toBe(138);
    expect(s.events[0]?.code).toBe('RIO');
    expect(s.missionSec).toBe(163);
    expect(s.wallMin).toBe(18 * 60 + 48);
    expect(s.balanceEth).toBeCloseTo(0.018924, 6);
    expect(s.series[s.series.length - 1]?.min).toBe(163);
    expect(s.handoffs).toBe(111);
    expect(s.rejected).toBe(3);
  });

  it('advances the wall clock and mission countdown by one second per tick', () => {
    const store = createDeskStore(7);
    store.getState().tick();
    const s = store.getState();
    expect(s.missionSec).toBe(162);
    expect(s.wallMin).toBeCloseTo(18 * 60 + 48 + 1 / 60, 6);
  });

  it('emits a new event after the 4-8s window and increments counters', () => {
    const store = createDeskStore(7);
    const before = store.getState();
    const wait = before.nextEventIn;
    expect(wait).toBeGreaterThanOrEqual(4);
    expect(wait).toBeLessThanOrEqual(8);

    for (let i = 0; i < wait; i += 1) store.getState().tick();

    const after = store.getState();
    expect(after.eventCount).toBe(139);
    expect(after.handoffs).toBe(112);
    expect(after.events).toHaveLength(80); // capped window
    expect(after.events[0]?.time).toBe('18:48'); // still within the same minute
  });

  it('appends at most one series point per whole session-minute', () => {
    const store = createDeskStore(7);
    const lenBefore = store.getState().series.length;
    for (let i = 0; i < 61; i += 1) store.getState().tick();
    const series = store.getState().series;
    expect(series.length).toBe(lenBefore + 1);
    expect(series[series.length - 1]?.min).toBe(164);
  });

  it('keeps the balance finite and clamped over a long run', () => {
    const store = createDeskStore(7);
    for (let i = 0; i < 600; i += 1) store.getState().tick();
    const b = store.getState().balanceEth;
    expect(Number.isFinite(b)).toBe(true);
    expect(b).toBeGreaterThanOrEqual(0.016);
    expect(b).toBeLessThanOrEqual(0.024);
  });
});
