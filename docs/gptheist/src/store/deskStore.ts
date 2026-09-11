import { createStore, type StoreApi } from 'zustand/vanilla';
import { useStore } from 'zustand';
import { DESK, minSinceSessionStart } from '../config';
import { generateBalanceHistory } from '../data/balance';
import { generateInitialEvents, makeLiveEvent } from '../data/events';
import { randomFrom } from '../lib/prng';
import type { ActivityEvent, BalancePoint } from '../types';

export type DeskState = {
  /** Wall clock, minutes since midnight (fractional while ticking). */
  wallMin: number;
  missionSec: number;
  balanceEth: number;
  series: BalancePoint[];
  events: ActivityEvent[];
  eventCount: number;
  handoffs: number;
  rejected: number;
  /** Seconds until the next activity event (4-8, per the brief). */
  nextEventIn: number;
  tick: () => void;
};

/**
 * Build an isolated store. Tests use this directly with a fixed seed; the app
 * uses the shared `deskStore` singleton below.
 */
export function createDeskStore(seed = 1337): StoreApi<DeskState> {
  const rng = randomFrom(seed);

  return createStore<DeskState>((set) => ({
    wallMin: DESK.wallClockMin,
    missionSec: DESK.missionClockSec,
    balanceEth: DESK.initialBalanceEth,
    series: generateBalanceHistory({
      seed,
      startEth: DESK.balanceStartEth,
      endEth: DESK.initialBalanceEth,
      nowMin: minSinceSessionStart(DESK.wallClockMin),
    }),
    events: generateInitialEvents({
      seed: seed + 1,
      count: DESK.eventCount,
      latestMin: DESK.wallClockMin - 5, // 18:43
    }),
    eventCount: DESK.eventCount,
    handoffs: DESK.handoffs,
    rejected: DESK.rejected,
    nextEventIn: rng.int(4, 8),

    tick: () => {
      set((state) => {
        const wallMin = state.wallMin + 1 / 60;
        const missionSec = Math.max(0, state.missionSec - 1);

        // Balance random-walks slightly; clamp so the chart never escapes.
        let balanceEth = state.balanceEth + rng.gaussian() * 0.000012;
        balanceEth = Math.min(0.024, Math.max(0.016, balanceEth));

        // Add a series point at most once per whole session-minute.
        const nowMin = Math.floor(minSinceSessionStart(wallMin));
        const lastMin = state.series[state.series.length - 1]?.min ?? -1;
        const series =
          nowMin > lastMin ? [...state.series, { min: nowMin, eth: balanceEth }] : state.series;

        let { events, eventCount, handoffs, rejected } = state;
        let nextEventIn = state.nextEventIn - 1;
        if (nextEventIn <= 0) {
          const ev = makeLiveEvent(rng, eventCount + 1, wallMin);
          events = [ev, ...events].slice(0, 80);
          eventCount += 1;
          handoffs += 1;
          if (ev.code === 'PALM' && ev.tone === 'neg') rejected += 1;
          nextEventIn = rng.int(4, 8);
        }

        return {
          wallMin,
          missionSec,
          balanceEth,
          series,
          events,
          eventCount,
          handoffs,
          rejected,
          nextEventIn,
        };
      });
    },
  }));
}

/** Shared store for the running app. */
export const deskStore = createDeskStore();

/** React binding with memoised selectors so panels only re-render on change. */
export function useDesk<T>(selector: (s: DeskState) => T): T {
  return useStore(deskStore, selector);
}

/** Drive the store at 1 Hz. Returns a stop function for useEffect cleanup. */
export function startEngine(store: StoreApi<DeskState> = deskStore): () => void {
  const id = window.setInterval(() => {
    store.getState().tick();
  }, 1000);
  return () => {
    window.clearInterval(id);
  };
}
