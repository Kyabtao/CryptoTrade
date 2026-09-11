import type { ReactNode } from 'react';

/**
 * One `LABEL … value` line used by the stats columns beside each visualisation.
 * Kept in one place so the ridge, chord, lattice and relationship columns all
 * line up identically.
 */
export function StatRow({
  label,
  value,
  valueClass = 'text-ink',
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3.5px]">
      <span className="label num text-[10px] text-muted">{label}</span>
      <span className={`num text-[12px] font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
}
