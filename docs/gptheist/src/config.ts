/**
 * Central desk configuration — the fixed numbers the reference pins down.
 *
 * Live values (clock, balance, events) start from these and are then advanced
 * by the SimulationEngine (milestone 3). Everything here is mock data; no
 * exchange, wallet or market API is contacted anywhere in the app.
 */

export const DESK = {
  /** Header */
  title: 'GPTHEIST DESK',
  handle: 'immortalhowwl',

  /** Session wall clock + window */
  wallClockMin: 18 * 60 + 48, // 18:48
  sessionStartMin: 16 * 60 + 5, // 16:05
  sessionEndMin: 5 * 60 + 5, // 05:05 (next day)
  sessionHours: 13,

  /** KPI strip — balance is the source of truth; PnL and % derive from it. */
  balanceStartEth: 0.0156,
  /** Chosen so the derived PnL renders exactly `+$10.97` at t0 (see DECISIONS). */
  initialBalanceEth: 0.018924,
  missionClockSec: 163, // 02:43
  missionWindow: '16:05 → 05:05 / 13 HOURS',

  /** Approval gate */
  gate: 'PALERMO',
  gateTag: 'ENTRY CLEARED',
  gateFilled: 3,
  gateSegments: 10,
  gateCheck: 'CHECK 52 / EXIT DEPTH',

  /** USD value of one ETH, held constant by the sim (per the brief). */
  ethPriceUsd: 3300,

  /** Activity log */
  eventCount: 138,

  /** Handoff chord running totals (advanced by the engine). */
  handoffs: 111,
  rejected: 3,

  /** Tail Probability Ridge (row 3). */
  ridge: {
    sessions: 1334,
    tailMassPct: 1.34,
    impliedMult: 40.0,
    avgEntryCents: 1.3,
    bestHit: 81.2,
    tooltipP: 1.58,
    tooltipMult: 40.9,
    tooltipSession: 1363,
  },

  /** Relationship Graph Simulation (row 5). */
  rel: {
    bearPaths: 518,
    bullPaths: 1027,
    pathsSim: 1545,
    convergencePct: 97,
    pUp: 0.6,
    pDown: 0.4,
    edgeVsBookCents: 23,
    confidencePct: 95.0,
  },
} as const;

/** Minutes since session start for a given wall-clock minute (session crosses midnight). */
export function minSinceSessionStart(wallMin: number): number {
  return (((wallMin - DESK.sessionStartMin) % 1440) + 1440) % 1440;
}

/** Fixed axis extents for the balance history chart. */
export const BALANCE_AXIS = {
  xStartMin: DESK.sessionStartMin,
  xEndMin: 24 * 60 + DESK.sessionEndMin, // crosses midnight
  yMin: 0,
  yMax: 0.025,
  xTicks: ['16:05', '22:35', '05:05'],
} as const;
