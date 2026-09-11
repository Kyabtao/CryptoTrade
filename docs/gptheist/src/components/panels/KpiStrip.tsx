import type { ReactNode } from 'react';
import { DESK } from '../../config';
import { fmtClock, fmtEth, fmtPct, fmtUsdSigned } from '../../lib/fmt';
import { useDesk } from '../../store/deskStore';

function KpiCard({
  label,
  corner,
  children,
}: {
  label: string;
  corner?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={label}
      className="hoverable relative flex flex-col gap-2 rounded-card border border-hairline bg-card px-4 py-3.5 shadow-card"
    >
      {corner ? <div className="absolute right-3 top-3">{corner}</div> : null}
      <h2 className="label num text-[10px] tracking-[0.12em] text-muted">{label}</h2>
      {children}
    </section>
  );
}

function Sub({ children }: { children: ReactNode }) {
  return <p className="label num mt-auto text-[9.5px] text-faint">{children}</p>;
}

/** Ten-segment progress bar; the first `filled` segments are green. */
export function SegmentBar({ filled, total }: { filled: number; total: number }) {
  return (
    <div
      role="img"
      aria-label={String(filled) + ' of ' + String(total) + ' segments filled'}
      className="flex gap-[3px]"
    >
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={`h-[5px] flex-1 rounded-full ${i < filled ? 'bg-pos' : 'bg-hairline'}`}
        />
      ))}
    </div>
  );
}

export function KpiStrip() {
  const balanceEth = useDesk((s) => s.balanceEth);
  const missionSec = useDesk((s) => s.missionSec);

  // PnL and percent derive from the live balance; ETH price is a constant.
  const pnlUsd = (balanceEth - DESK.balanceStartEth) * DESK.ethPriceUsd;
  const pnlPct = ((balanceEth - DESK.balanceStartEth) / DESK.balanceStartEth) * 100;

  return (
    <div className="col-span-12 grid grid-cols-2 gap-4 xl:grid-cols-4">
      <KpiCard label="BALANCE / ETH">
        <p className="num text-[26px] font-bold leading-none text-ink">{fmtEth(balanceEth)}</p>
        <Sub>FROM {fmtEth(DESK.balanceStartEth)}</Sub>
      </KpiCard>

      <KpiCard label="TOTAL PNL / USD">
        <p className="num text-[26px] font-bold leading-none text-pos">{fmtUsdSigned(pnlUsd)}</p>
        <Sub>{fmtPct(pnlPct)}</Sub>
      </KpiCard>

      <KpiCard label="MISSION CLOCK">
        <p className="num text-[26px] font-bold leading-none text-ink">{fmtClock(missionSec)}</p>
        <Sub>{DESK.missionWindow}</Sub>
      </KpiCard>

      <KpiCard
        label="APPROVAL GATE"
        corner={<span aria-hidden="true" className="size-1.5 rounded-full bg-pos" />}
      >
        <div className="flex items-baseline justify-between gap-2">
          <p className="num text-lg font-bold leading-none text-ink">{DESK.gate}</p>
          <p className="label num text-[9px] font-semibold text-pos">{DESK.gateTag}</p>
        </div>
        <SegmentBar filled={DESK.gateFilled} total={DESK.gateSegments} />
        <Sub>{DESK.gateCheck}</Sub>
      </KpiCard>
    </div>
  );
}
