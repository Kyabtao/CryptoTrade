import { memo } from 'react';
import type { HistogramBar } from '../../data/graph';

/**
 * EDGE DISTRIBUTION / 24H — a small bell of bars coloured red→pink→green→blue.
 * Plain flex divs are the right tool; no chart library needed.
 */
export const Histogram = memo(function Histogram({ bars }: { bars: HistogramBar[] }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <div
      className="flex h-16 w-full items-end gap-[2px]"
      role="img"
      aria-label="Edge distribution over the last 24 hours"
    >
      {bars.map((b, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-[2px]"
          style={{
            height: String(Math.round((b.value / max) * 100)) + '%',
            background: b.color,
          }}
        />
      ))}
    </div>
  );
});
