import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function RidgePanel() {
  return (
    <Card
      mode={{ kind: 'dot', dotClass: 'bg-ink' }}
      title="Tail Probability Ridge"
      center="STRIKE LANDSCAPE · PRICE-TARGET DENSITY / ACTIVE POOL"
      right="ONE RIDGE / ONE SESSION / TAILS PAY"
      footer="PRICE THE TAIL. CHECK THE EXIT."
      className="col-span-12"
    >
      <PanelPlaceholder height={190} note="ridgeline · milestone 4" />
    </Card>
  );
}
