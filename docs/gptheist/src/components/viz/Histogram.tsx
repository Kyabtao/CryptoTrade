import { memo, useState } from 'react';
import type { HistogramBar } from '../../data/graph';

/**
 * EDGE DISTRIBUTION / 24H — a small bell of bars coloured red→pink→green→blue.
 * Plain flex divs are the right tool; no chart library needed.
 *
 * Hover follows the desk's shared grammar (see BalanceChart): the bar under
 * the pointer gets the dark `.chart-tip` tooltip. Like the main site's
 * `histogram` (which uses `<title>` tags), the bars themselves do not restyle
 * on hover — the tooltip anchored above the bar is the association.
 */
export const Histogram = memo(function Histogram({ bars }: { bars: HistogramBar[] }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const [hover, setHover] = useState<number | null>(null);

  const hp = hover != null ? (bars[hover] ?? null) : null;

  return (
    <div
      className="relative flex h-16 w-full items-end gap-[2px]"
      role="img"
      aria-label="Edge distribution over the last 24 hours"
      onPointerLeave={() => {
        setHover(null);
      }}
    >
      {bars.map((b, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-[3px]"
          style={{
            height: String(Math.round((b.value / max) * 100)) + '%',
            background: b.color,
            opacity: 0.85,
          }}
          onPointerMove={() => {
            setHover(i);
          }}
          data-testid={'edge-bar-' + String(i)}
        />
      ))}

      {hp && hover != null ? (
        <div
          className="chart-tip"
          style={{
            left: String(((hover + 0.5) / bars.length) * 100) + '%',
            bottom: 'calc(100% + 8px)',
            opacity: 1,
            // Centre on the bar; pin to the bar edge near the box sides so the
            // 130px tooltip never spills past the wrapper.
            transform:
              hover < 2
                ? 'none'
                : hover > bars.length - 3
                  ? 'translateX(-100%)'
                  : 'translateX(-50%)',
          }}
        >
          <div className="t-head">{'BIN ' + String(hover + 1) + ' / ' + String(bars.length)}</div>
          <div className="t-row">
            <span className="sw" style={{ background: hp.color }} />
            Count<b className="num">{String(hp.value)}</b>
          </div>
        </div>
      ) : null}
    </div>
  );
});
