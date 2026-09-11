import { useMemo } from 'react';
import { Card } from '../Card';
import { StatRow } from '../StatRow';
import { ChordDiagram } from '../viz/ChordDiagram';
import { generateChordMatrix } from '../../data/chord';
import { useDesk } from '../../store/deskStore';

export function ChordPanel() {
  const data = useMemo(() => generateChordMatrix(111), []);
  const handoffs = useDesk((s) => s.handoffs);
  const rejected = useDesk((s) => s.rejected);

  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-amber' }}
      title="Handoff Chord"
      center="WHO PASSES TO WHOM"
      right="10 ROLES"
      footer="FILES, NOT MEMORY / EVERY PASS LEAVES A TRAIL"
      className="col-span-12 lg:col-span-6"
      bodyClassName="h-full"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_170px]">
        <div className="h-[220px]">
          <ChordDiagram data={data} />
        </div>
        <div className="pt-2">
          <StatRow label="HANDOFFS" value={String(handoffs)} />
          <StatRow label="REJECTED" value={String(rejected)} valueClass="text-neg" />
          <StatRow label="EDGES / TASK" value="1" />
          <StatRow label="APPROVAL" value="PALERMO" valueClass="text-neg" />
        </div>
      </div>
    </Card>
  );
}
