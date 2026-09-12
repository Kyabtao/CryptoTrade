import { Card } from '../Card';
import { StatRow } from '../StatRow';
import { Penteract } from '../viz/Penteract';
import { rotationDegAt } from '../../lib/math5d';
import { fmtDeg } from '../../lib/fmt';
import { useDesk } from '../../store/deskStore';

const LEGEND = [
  { label: 'D1', cls: 'bg-pos' },
  { label: 'D2', cls: 'bg-neg' },
  { label: 'D3', cls: 'bg-node' },
  { label: 'D4', cls: 'bg-amber' },
  { label: 'D5', cls: 'bg-info' },
] as const;

export function LatticePanel() {
  // Re-renders on each 1 Hz engine tick, which refreshes the live readout.
  useDesk((s) => s.missionSec);
  const rotation = rotationDegAt(Date.now());

  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-info' }}
      title="5D Strategy Lattice"
      center="PENTERACT"
      right="32 NODES · 80 EDGES"
      footer="EVERY AXIS IS AN EDGE / A TEAM MUST PASS ALL FIVE"
      className="col-span-12 lg:col-span-6"
      bodyClassName="h-full"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[170px_1fr]">
        <div className="pt-2">
          <StatRow label="DIMENSIONS" value="5 / 5" />
          <StatRow label="VERTICES" value="32" />
          <StatRow label="EDGES" value="80" />
          <StatRow label="ROTATION" value={fmtDeg(rotation)} valueClass="text-neg" />
          <StatRow label="PROJECTION" value="5D → 2D" />
          <div className="mt-3 flex items-center gap-2">
            {LEGEND.map((item) => (
              <span key={item.label} className="flex items-center gap-1">
                <span aria-hidden="true" className={`size-1.5 rounded-full ${item.cls}`} />
                <span className="num text-[8.5px] text-faint">{item.label}</span>
              </span>
            ))}
          </div>
        </div>
        <div className="h-[220px]">
          <Penteract />
        </div>
      </div>
    </Card>
  );
}
