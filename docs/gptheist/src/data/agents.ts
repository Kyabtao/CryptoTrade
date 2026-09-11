import type { Agent } from '../types';

/**
 * The ten-person crew, in the exact roster order pinned by the reference:
 * index, name, role. Accents and active borders follow the screenshot and are
 * reused consistently for log codes and chord labels.
 */
export const AGENTS: readonly Agent[] = [
  { code: 'TOKY', name: 'TOKYO', role: 'SCOUTS', index: '03', accent: 'amber', state: 'line' },
  { code: 'PALM', name: 'PALERMO', role: 'VETOES', index: '10', accent: 'pos', state: 'active' },
  { code: 'DENV', name: 'DENVER', role: 'SIGNALS', index: '07', accent: 'amber', state: 'line' },
  {
    code: 'STOC',
    name: 'STOCKHOLM',
    role: 'LIQUIDITY',
    index: '08',
    accent: 'info',
    state: 'line',
  },
  { code: 'PROF', name: 'PROFESSOR', role: 'ROUTER', index: '01', accent: 'info', state: 'active' },
  { code: 'RIO', name: 'RIO', role: 'CHARTS', index: '04', accent: 'node', state: 'active' },
  { code: 'HELS', name: 'HELSINKI', role: 'LEDGER', index: '03', accent: 'node', state: 'line' },
  { code: 'NAIR', name: 'NAIROBI', role: 'BRIEFS', index: '05', accent: 'neg', state: 'line' },
  { code: 'BERL', name: 'BERLIN', role: 'CONDITIONS', index: '02', accent: 'neg', state: 'line' },
  { code: 'LISB', name: 'LISBON', role: 'RESEARCH', index: '06', accent: 'teal', state: 'active' },
] as const;

/** Look up an agent by its four-letter code. */
export function agentByCode(code: string): Agent | undefined {
  return AGENTS.find((a) => a.code === code);
}
