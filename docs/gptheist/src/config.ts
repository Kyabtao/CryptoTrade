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
  wallClock: '18:48',
  sessionStartMin: 16 * 60 + 5, // 16:05
  sessionEndMin: 5 * 60 + 5, // 05:05 (next day)
  sessionHours: 13,

  /** KPI strip */
  balanceEth: 0.0189,
  balanceStartEth: 0.0156,
  pnlUsd: 10.97,
  pnlPct: 21.18,
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
} as const;

/** Fixed axis extents for the balance history chart. */
export const BALANCE_AXIS = {
  xStartMin: DESK.sessionStartMin,
  xEndMin: 24 * 60 + DESK.sessionEndMin, // crosses midnight
  yMin: 0,
  yMax: 0.025,
  xTicks: ['16:05', '22:35', '05:05'],
} as const;
