import { useMemo } from 'react';
import { Card } from '../Card';
import { StatRow } from '../StatRow';
import { ForceGraph } from '../viz/ForceGraph';
import { Histogram } from '../viz/Histogram';
import { generateEdgeHistogram, generateForceGraph } from '../../data/graph';
import { DESK } from '../../config';
import { fmt, fmtCentsSigned, fmtPct } from '../../lib/fmt';

const LEGEND = [
  { label: 'Bear signal', swatch: 'bg-neg', dashed: false },
  { label: 'Bull signal', swatch: 'bg-pos', dashed: false },
  { label: 'Median path', swatch: 'bg-ink', dashed: true },
  { label: 'Catalyst', swatch: 'bg-teal', dashed: false },
] as const;

export function RelationshipPanel() {
  const graph = useMemo(() => generateForceGraph(1545), []);
  const bars = useMemo(() => generateEdgeHistogram(), []);
  const rel = DESK.rel;

  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-neg' }}
      title="Relationship Graph Simulation"
      center="VOLUME / FLOW / LIQUIDITY"
      right="90 NODES · 134 EDGES"
      className="col-span-12"
      bodyClassName="h-full"
    >
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[200px_1fr_200px]">
        {/* left: legend + path stats */}
        <div>
          <p className="label num mb-1 text-[10px] text-muted">NODE CLASS</p>
          <ul className="mb-3 space-y-1">
            {LEGEND.map((item) => (
              <li key={item.label} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`h-[3px] w-3 rounded-full ${item.swatch} ${item.dashed ? 'opacity-60' : ''}`}
                />
                <span className="num text-[9px] text-muted">{item.label}</span>
              </li>
            ))}
          </ul>
          <StatRow label="BEAR PATHS" value={String(rel.bearPaths)} valueClass="text-neg" />
          <StatRow label="BULL PATHS" value={String(rel.bullPaths)} valueClass="text-pos" />
          <StatRow label="PATHS SIM" value={String(rel.pathsSim)} />
          <StatRow
            label="CONVERGENCE"
            value={fmtPct(rel.convergencePct, 0)}
            valueClass="text-pos"
          />
          <div
            aria-hidden="true"
            className="my-2 h-[8px] w-full rounded-chip"
            style={{
              background:
                'repeating-linear-gradient(90deg, var(--gp-node) 0 3px, transparent 3px 5px)',
            }}
          />
          <p className="label num text-[10px] text-pos">PREDICTED ▲ UP</p>
        </div>

        {/* centre: force graph */}
        <div className="h-[220px]">
          <ForceGraph data={graph} />
        </div>

        {/* right: probabilities + histogram */}
        <div>
          <StatRow label="P(UP)" value={fmt(rel.pUp, 2)} valueClass="text-pos" />
          <StatRow label="P(DOWN)" value={fmt(rel.pDown, 2)} valueClass="text-neg" />
          <StatRow
            label="EDGE VS BOOK"
            value={fmtCentsSigned(rel.edgeVsBookCents)}
            valueClass="text-pos"
          />
          <StatRow label="CONFIDENCE" value={fmtPct(rel.confidencePct, 1)} />
          <p className="label num mb-1 mt-4 text-[9px] text-faint">EDGE DISTRIBUTION / 24H</p>
          <Histogram bars={bars} />
        </div>
      </div>
    </Card>
  );
}
