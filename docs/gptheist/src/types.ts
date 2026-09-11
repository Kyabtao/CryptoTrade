/**
 * Shared domain types for GPTHEIST DESK.
 *
 * Kept in one file so generators, the store, panels and tests all agree on the
 * shape of the data. Everything is plain and serialisable.
 */

/** Four-letter agent codes used across the log, chord and roster. */
export type AgentCode =
  'TOKY' | 'PALM' | 'LISB' | 'BERL' | 'DENV' | 'NAIR' | 'STOC' | 'HELS' | 'PROF' | 'RIO';

/** Full roster names, in display order. */
export type AgentName =
  | 'TOKYO'
  | 'PALERMO'
  | 'DENVER'
  | 'STOCKHOLM'
  | 'PROFESSOR'
  | 'RIO'
  | 'HELSINKI'
  | 'NAIROBI'
  | 'BERLIN'
  | 'LISBON';

/** The accent colour an agent is drawn with (log code, role text, border). */
export type AgentAccent = 'pos' | 'neg' | 'info' | 'node' | 'teal' | 'amber';

export type AgentRole =
  | 'SCOUTS'
  | 'VETOES'
  | 'SIGNALS'
  | 'LIQUIDITY'
  | 'ROUTER'
  | 'CHARTS'
  | 'LEDGER'
  | 'BRIEFS'
  | 'CONDITIONS'
  | 'RESEARCH';

export type Agent = {
  code: AgentCode;
  name: AgentName;
  role: AgentRole;
  /** Two-digit roster index as shown on the card. */
  index: string;
  accent: AgentAccent;
  /** Border treatment for the roster card; `line` is the default hairline. */
  state: 'active' | 'line';
};

/** One row of the activity log. */
export type ActivityEvent = {
  id: number;
  time: string; // "18:43"
  code: AgentCode;
  message: string;
  /** Small status dot to the right of the row. */
  tone: 'pos' | 'neg' | 'info' | 'neutral';
};

/** A single point of the balance history series. */
export type BalancePoint = {
  min: number; // minutes since session start
  eth: number;
};
