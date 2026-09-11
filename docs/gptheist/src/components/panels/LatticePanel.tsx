import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function LatticePanel() {
  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-info' }}
      title="5D Strategy Lattice"
      center="PENTERACT"
      right="32 NODES · 80 EDGES"
      footer="EVERY AXIS IS AN EDGE / A TEAM MUST PASS ALL FIVE"
      className="col-span-12 lg:col-span-6"
    >
      <PanelPlaceholder height={220} note="animated 5-cube · milestone 5" />
    </Card>
  );
}
