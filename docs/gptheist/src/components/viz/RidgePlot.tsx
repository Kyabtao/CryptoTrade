import { memo, useMemo, useState } from 'react';
import { scaleLinear } from 'd3-scale';
import { DESK } from '../../config';
import { fmtMult, fmtPct } from '../../lib/fmt';
import { useMeasure } from '../../lib/useMeasure';
import type { RidgeData } from '../../data/ridge';

type Props = { data: RidgeData };

const M = { left: 10, right: 10, top: 8, bottom: 22 };
const X_LABELS = [-2, -1, 0, 1, 2] as const;

type Tooltip = { p: string; mult: string; session: number };

/**
 * Ridgeline: ~24 stacked, peak-normalised density curves drawn back-to-front
 * (each filled with the card colour to occlude the ones behind), right tail
 * shaded pink past the strike, one dashed red strike line through the surface,
 * and a single hover tooltip.
 */
export const RidgePlot = memo(function RidgePlot({ data }: Props) {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const count = data.ridges.length;

  const geom = useMemo(() => {
    if (width <= 0 || height <= 0 || count === 0) return null;
    const skew = Math.min(6, width * 0.006);
    const x = scaleLinear()
      .domain([-3, 3])
      .range([M.left, width - M.right - skew * count * 0.4]);
    const plotH = height - M.top - M.bottom;
    const rowStep = plotH / (count + 3);
    const curveH = rowStep * 3.4;

    const ridges = data.ridges.map((r, i) => {
      const baseline = height - M.bottom - i * rowStep;
      const xoff = i * skew * 0.4;
      const amp = 0.3 + 0.7 * (i / (count - 1));
      return { r, baseline, xoff, amp };
    });

    return { x, ridges, skew, curveH };
  }, [width, height, count, data.ridges]);

  const hovered = hover != null ? data.ridges[hover] : null;
  const tip: Tooltip = hovered
    ? {
        p: fmtPct(hovered.tailP * 100, 2),
        mult: fmtMult(hovered.tailP > 0 ? 1 / hovered.tailP : 0, 1),
        session: hovered.session,
      }
    : {
        p: fmtPct(DESK.ridge.tooltipP, 2),
        mult: fmtMult(DESK.ridge.tooltipMult, 1),
        session: DESK.ridge.tooltipSession,
      };

  const areaPath = (
    curve: { x: number; y: number }[],
    baseline: number,
    xoff: number,
    amp: number,
    x: (v: number) => number,
    curveH: number,
    fromX?: number
  ): string => {
    const pts = curve.filter((p) => fromX == null || p.x >= fromX);
    if (pts.length === 0) return '';
    let d = 'M' + String(x((pts[0] as { x: number }).x) + xoff) + ',' + String(baseline);
    for (const p of pts) {
      d += 'L' + String(x(p.x) + xoff) + ',' + String(baseline - p.y * amp * curveH);
    }
    const lastX = x((pts[pts.length - 1] as { x: number }).x) + xoff;
    d += 'L' + String(lastX) + ',' + String(baseline) + 'Z';
    return d;
  };

  return (
    <div ref={ref} className="relative h-full w-full">
      {geom ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Tail probability ridgeline, one density curve per session, right tail shaded past the strike"
          className="block"
          onMouseLeave={() => {
            setHover(null);
          }}
        >
          {/* draw back (top) to front (bottom) so nearer ridges occlude */}
          {[...geom.ridges].reverse().map(({ r, baseline, xoff, amp }, rev) => {
            const i = count - 1 - rev;
            return (
              <g key={r.session}>
                <path
                  d={areaPath(r.curve, baseline, xoff, amp, geom.x, geom.curveH)}
                  fill="var(--gp-card)"
                  stroke="var(--gp-faint)"
                  strokeWidth={0.8}
                  onMouseEnter={() => {
                    setHover(i);
                  }}
                />
              </g>
            );
          })}

          {/* pink right-tail shading + dashed strike line, on top */}
          {geom.ridges.map(({ r, baseline, xoff, amp }) => (
            <path
              key={'tail' + String(r.session)}
              d={areaPath(r.curve, baseline, xoff, amp, geom.x, geom.curveH, data.strike)}
              fill="var(--gp-neg-wash)"
              stroke="none"
              pointerEvents="none"
            />
          ))}
          <polyline
            points={geom.ridges
              .map(
                ({ baseline, xoff }) => String(geom.x(data.strike) + xoff) + ',' + String(baseline)
              )
              .join(' ')}
            fill="none"
            stroke="var(--gp-neg)"
            strokeWidth={1.2}
            strokeDasharray="4 3"
            pointerEvents="none"
          />

          {/* x axis */}
          {X_LABELS.map((t) => (
            <text
              key={'rx' + String(t)}
              x={geom.x(t)}
              y={height - 6}
              textAnchor="middle"
              fontSize={8.5}
              fill="var(--gp-faint)"
              style={{ fontFamily: 'var(--gp-font-mono)' }}
            >
              {t === 0 ? '0' : (t > 0 ? '+' + String(t) : String(t)) + 'σ'}
            </text>
          ))}
        </svg>
      ) : null}

      {/* single hover tooltip */}
      {geom ? (
        <div
          className="pointer-events-none absolute rounded-chip border border-hairline bg-card px-2.5 py-1.5 shadow-card"
          style={{ left: '46%', top: '34%' }}
        >
          <p className="num text-[9.5px] text-ink">P(&gt;STRIKE) {tip.p}</p>
          <p className="num text-[9.5px] font-semibold text-neg">IMPLIED {tip.mult}</p>
          <p className="num text-[8.5px] text-faint">SESSION {tip.session}</p>
        </div>
      ) : null}
    </div>
  );
});
