import { Card } from '../Card';
import { BalanceChart } from '../viz/BalanceChart';
import { useDesk } from '../../store/deskStore';

export function BalanceHistoryPanel() {
  const series = useDesk((s) => s.series);
  const balanceEth = useDesk((s) => s.balanceEth);

  return (
    <Card
      mode={{ kind: 'mono' }}
      title="BALANCE HISTORY"
      right="ETH / 13H"
      className="col-span-12 lg:col-span-7"
      bodyClassName="h-full"
    >
      <div className="h-[220px]">
        <BalanceChart series={series} balanceEth={balanceEth} />
      </div>
    </Card>
  );
}
