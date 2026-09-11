import { DESK } from '../../config';
import { fmtCount } from '../../lib/fmt';
import { Card } from '../Card';
import { PanelPlaceholder } from './PanelPlaceholder';

export function ActivityLogPanel() {
  return (
    <Card
      mode={{ kind: 'mono' }}
      title="ACTIVITY LOG"
      right={`${fmtCount(DESK.eventCount)} EVENTS`}
      className="col-span-12 lg:col-span-5"
      bodyClassName="h-full"
    >
      <PanelPlaceholder height={216} note="event feed · milestone 3" />
    </Card>
  );
}
