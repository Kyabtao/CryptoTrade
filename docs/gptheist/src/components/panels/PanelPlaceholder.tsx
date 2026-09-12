/**
 * Milestone-2 body for panels whose visualisation lands later. A quiet dashed
 * well that reserves the exact height the finished chart will occupy, so the
 * grid reads like the reference from the very first shell commit.
 */
export function PanelPlaceholder({ height, note }: { height: number; note: string }) {
  return (
    <div
      className="grid h-full w-full place-items-center rounded-chip border border-dashed border-hairline bg-canvas/60"
      style={{ minHeight: height }}
    >
      <span className="label num text-[9px] text-faint">{note}</span>
    </div>
  );
}
