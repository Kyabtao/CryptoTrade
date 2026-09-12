import { useMemo } from 'react';
import { Card } from '../Card';
import { StatRow } from '../StatRow';
import { RidgePlot } from '../viz/RidgePlot';
import { generateRidgeData } from '../../data/ridge';
import { DESK } from '../../config';
import { fmtCents, fmtMult, fmtPct, fmtSigned } from '../../lib/fmt';

export function RidgePanel() {
  const data = useMemo(() => generateRidgeData({ seed: 1363 }), []);
  const r = DESK.ridge;

  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-ink' }}
      title="Tail Probability Ridge"
      center="STRIKE LANDSCAPE · PRICE-TARGET DENSITY / ACTIVE POOL"
      right="ONE RIDGE / ONE SESSION / TAILS PAY"
      footer="PRICE THE TAIL. CHECK THE EXIT."
      className="col-span-12"
      bodyClassName="h-full"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[190px_1fr]">
        <div>
          <p className="label num mb-1 text-[10px] text-muted">TAIL SCANNER / LIVE</p>
          <StatRow label="SESSIONS" value={String(r.sessions)} />
          <StatRow label="TAIL MASS" value={fmtPct(r.tailMassPct, 2)} valueClass="text-pos" />
          <StatRow label="IMPLIED MULT" value={fmtMult(r.impliedMult, 1)} />
          <StatRow label="AVG ENTRY" value={fmtCents(r.avgEntryCents, 1)} />
          <StatRow label="BEST HIT" value={fmtSigned(r.bestHit, 1)} valueClass="text-pos" />
        </div>
        <div className="h-[200px]">
          <RidgePlot data={data} />
        </div>
      </div>
    </Card>
  );
}
