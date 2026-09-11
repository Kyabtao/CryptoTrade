import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function RelationshipPanel() {
  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-neg' }}
      title="Relationship Graph Simulation"
      center="VOLUME / FLOW / LIQUIDITY"
      right="90 NODES · 134 EDGES"
      className="col-span-12"
    >
      <PanelPlaceholder height={200} note="force graph + histogram · milestone 6" />
    </Card>
  );
}
