import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function ChordPanel() {
  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-amber' }}
      title="Handoff Chord"
      center="WHO PASSES TO WHOM"
      right="10 ROLES"
      footer="FILES, NOT MEMORY / EVERY PASS LEAVES A TRAIL"
      className="col-span-12 lg:col-span-6"
    >
      <PanelPlaceholder height={220} note="chord diagram · milestone 5" />
    </Card>
  );
}
