import { fmtTimeOfDay } from '../lib/fmt';
import { randomFrom, type Random } from '../lib/prng';
import type { ActivityEvent, AgentCode } from '../types';

/**
 * Per-agent message templates in the desk's terse house style, taken from the
 * brief. The engine draws one at random when an agent "speaks".
 */
export const EVENT_TEMPLATES: Record<AgentCode, readonly string[]> = {
  TOKY: [
    'fresh pool / volume preceded price',
    'scout sweep / new pool flagged',
    'volume spike / watching',
  ],
  PALM: ['safe exit / veto gate checked', 'veto reviewed / gate held', 'exit route / veto cleared'],
  LISB: ['holder snapshot / freshness check', 'research digest / synced', 'source freshness / ok'],
  BERL: [
    'exact return conditions saved',
    'conditions locked / no drift',
    'return terms / verified',
  ],
  DENV: ['X + TG / paid noise filtered', 'signal filtered / noise dropped', 'trigger set / clean'],
  NAIR: ['cleared brief → Astra', 'brief cleared / forwarded', 'summary → Astra'],
  STOC: ['depth / slippage / size checked', 'liquidity window / ok', 'slippage within budget'],
  HELS: ['positions / exit rules saved', 'ledger snapshot / written', 'exit rules / persisted'],
  PROF: ['ULTRA / 1 YEAR / SELF-FUND', 'routing plan / updated', 'capital plan / self-fund'],
  RIO: [
    'pullback / invalidation marked',
    'pullback / invalidation marked',
    'chart structure / re-marked',
  ],
};

const CODES = Object.keys(EVENT_TEMPLATES) as AgentCode[];

function toneFor(code: AgentCode, rng: Random): ActivityEvent['tone'] {
  if (code === 'PALM') return rng.chance(0.3) ? 'neg' : 'pos';
  if (code === 'RIO') return 'neg';
  if (code === 'PROF' || code === 'STOC' || code === 'LISB') return 'info';
  if (code === 'HELS' || code === 'NAIR') return 'pos';
  return rng.chance(0.5) ? 'pos' : 'neutral';
}

/** One live event at the current wall-clock minute. */
export function makeLiveEvent(rng: Random, id: number, wallMin: number): ActivityEvent {
  const code = rng.pick(CODES);
  const message = rng.pick(EVENT_TEMPLATES[code]);
  return { id, time: fmtTimeOfDay(wallMin), code, message, tone: toneFor(code, rng) };
}

export type InitialEventsOptions = {
  seed: number;
  count: number;
  /** Wall-clock minute of the most recent (highlighted) event. */
  latestMin: number;
};

/**
 * The back-scroll of the log: `count` events, newest first, walking backwards
 * in time with realistic 1-6 minute gaps. The newest is always RIO marking an
 * invalidation, matching the reference's highlighted row.
 */
export function generateInitialEvents(opts: InitialEventsOptions): ActivityEvent[] {
  const rng = randomFrom(opts.seed);
  const events: ActivityEvent[] = [];
  let min = opts.latestMin;
  let id = opts.count;

  events.push({
    id,
    time: fmtTimeOfDay(min),
    code: 'RIO',
    message: 'pullback / invalidation marked',
    tone: 'neg',
  });

  for (let i = 1; i < opts.count; i += 1) {
    id -= 1;
    min -= rng.int(1, 6);
    const code = rng.pick(CODES);
    events.push({
      id,
      time: fmtTimeOfDay(min),
      code,
      message: rng.pick(EVENT_TEMPLATES[code]),
      tone: toneFor(code, rng),
    });
  }
  return events;
}
