import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function BalanceHistoryPanel() {
  return (
    <Card
      mode={{ kind: 'mono' }}
      title="BALANCE HISTORY"
      right="ETH / 13H"
      className="col-span-12 lg:col-span-7"
      bodyClassName="h-full"
    >
      <PanelPlaceholder height={216} note="line chart · milestone 3" />
    </Card>
  );
}
