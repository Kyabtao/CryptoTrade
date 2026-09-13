import { bisector } from 'd3-array';
import { scaleLinear } from 'd3-scale';
import { area, curveMonotoneX, line } from 'd3-shape';
import { memo, useCallback, useMemo, useState } from 'react';
import { DESK } from '../../config';
import { fmt, fmtEth, fmtTimeOfDay } from '../../lib/fmt';
import { useMeasure } from '../../lib/useMeasure';
import type { BalancePoint } from '../../types';

type Props = {
  /** Realised series, minutes since session start (0 … nowMin). */
  series: BalancePoint[];
  balanceEth: number;
};

const M = { left: 40, right: 14, top: 22, bottom: 22 };
const SESSION_MIN = DESK.sessionHours * 60; // 780

const Y_TICKS = [0, 0.0125, 0.025] as const;
const X_TICKS = [0, SESSION_MIN / 2, SESSION_MIN] as const;
const X_LABELS = ['16:05', '22:35', '05:05'] as const;

const MONO = { fontFamily: 'var(--gp-font-mono)' } as const;

/** Insertion-point search over the realised minutes (module scope: stateless). */
const bisectMin = bisector((p: BalancePoint) => p.min);

function yTickLabel(v: number): string {
  return v === 0 ? '0.0' : fmt(v, 3);
}

/**
 * Pure SVG line chart: faint grid, green wash under the realised portion, the
 * ink line, and a red-bordered current-value tag. D3 supplies the scales and
 * path generators; React owns the DOM.
 *
 * Hover follows the main site's `interactiveLineChart` contract (see
 * `docs/assets/charts.js`): a full-plot hit rect maps the pointer to the
 * nearest point and shows a dashed crosshair, a hover dot and a dark HTML
 * tooltip. Colours stay on the desk's light tokens — only the tooltip is the
 * shared dark pattern. There is deliberately no drag-to-zoom: on a 220px
 * panel it would need store wiring for no benefit (see DECISIONS).
 */
export const BalanceChart = memo(function BalanceChart({ series, balanceEth }: Props) {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const geom = useMemo(() => {
    if (width <= 0 || height <= 0 || series.length < 2) return null;
    const x = scaleLinear()
      .domain([0, SESSION_MIN])
      .range([M.left, width - M.right]);
    const y = scaleLinear()
      .domain([0, 0.025])
      .range([height - M.bottom, M.top]);
    const lineGen = line<BalancePoint>()
      .x((p) => x(p.min))
      .y((p) => y(p.eth))
      .curve(curveMonotoneX);
    const areaGen = area<BalancePoint>()
      .x((p) => x(p.min))
      .y0(y(0))
      .y1((p) => y(p.eth))
      .curve(curveMonotoneX);
    return {
      x,
      y,
      linePath: lineGen(series) ?? '',
      areaPath: areaGen(series) ?? '',
    };
  }, [series, width, height]);

  /** Nearest realised index to a client X, clamped — the `idxAt` of charts.js. */
  const idxAt = useCallback(
    (clientX: number): number | null => {
      const node = ref.current;
      if (!node || !geom || series.length === 0) return null;
      const rect = node.getBoundingClientRect();
      if (rect.width <= 0) return null;
      // The SVG is drawn 1:1 in the measured box (no viewBox scaling), so the
      // client offset maps straight onto plot coordinates.
      const px = clientX - rect.left;
      const minGuess = geom.x.invert(Math.max(M.left, Math.min(width - M.right, px)));
      const at = Math.max(0, Math.min(series.length - 1, bisectMin.left(series, minGuess)));
      const lo = series[Math.max(0, at - 1)];
      const hi = series[at];
      if (!lo || !hi) return at;
      return Math.abs(hi.min - minGuess) <= Math.abs(minGuess - lo.min) ? at : Math.max(0, at - 1);
    },
    [geom, ref, series, width]
  );

  const onMove = useCallback(
    (e: React.PointerEvent) => {
      setHover(idxAt(e.clientX));
    },
    [idxAt]
  );
  const onLeave = useCallback(() => {
    setHover(null);
  }, []);

  const last = series[series.length - 1];
  const hp = hover != null ? (series[hover] ?? null) : null;
  // Flip the tooltip to the left of the cursor near the right edge, exactly
  // like the main site's clamp (`relX + 14`, kept inside the container).
  const tipLeft =
    hp && geom
      ? Math.max(4, geom.x(hp.min) > width - 170 ? geom.x(hp.min) - 144 : geom.x(hp.min) + 14)
      : 0;

  return (
    <div ref={ref} className="relative h-full w-full">
      {geom && last ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={'Balance history line chart, current ' + fmtEth(balanceEth)}
          className="block"
        >
          {/* faint grid */}
          {Y_TICKS.map((t) => (
            <line
              key={'y' + String(t)}
              x1={M.left}
              x2={width - M.right}
              y1={geom.y(t)}
              y2={geom.y(t)}
              stroke="var(--gp-hairline)"
              strokeWidth={1}
              strokeDasharray={t === 0 ? undefined : '2 4'}
            />
          ))}
          {X_TICKS.map((t) => (
            <line
              key={'x' + String(t)}
              x1={geom.x(t)}
              x2={geom.x(t)}
              y1={M.top}
              y2={height - M.bottom}
              stroke="var(--gp-hairline-soft)"
              strokeWidth={1}
            />
          ))}

          {/* realised wash + line */}
          <path d={geom.areaPath} fill="var(--gp-pos-wash)" stroke="none" />
          <path d={geom.linePath} fill="none" stroke="var(--gp-ink)" strokeWidth={1.6} />

          {/* current point + red-bordered tag */}
          <circle
            cx={geom.x(last.min)}
            cy={geom.y(last.eth)}
            r={3.2}
            fill="var(--gp-neg)"
            stroke="var(--gp-card)"
            strokeWidth={1.4}
          />
          <g
            transform={
              'translate(' +
              String(Math.min(geom.x(last.min) - 24, width - M.right - 52)) +
              ', ' +
              String(Math.max(2, geom.y(last.eth) - 24)) +
              ')'
            }
          >
            <rect
              width={52}
              height={16}
              rx={3}
              fill="var(--gp-card)"
              stroke="var(--gp-neg)"
              strokeWidth={1}
            />
            <text
              x={26}
              y={11.5}
              textAnchor="middle"
              fontSize={9}
              fill="var(--gp-neg)"
              style={MONO}
            >
              {fmt(balanceEth, 4)}
            </text>
          </g>

          {/* axis labels */}
          {Y_TICKS.map((t) => (
            <text
              key={'yl' + String(t)}
              x={M.left - 6}
              y={geom.y(t) + 3}
              textAnchor="end"
              fontSize={8.5}
              fill="var(--gp-faint)"
              style={MONO}
            >
              {yTickLabel(t)}
            </text>
          ))}
          {X_TICKS.map((t, i) => (
            <text
              key={'xl' + String(t)}
              x={geom.x(t)}
              y={height - 6}
              textAnchor={i === 0 ? 'start' : i === X_TICKS.length - 1 ? 'end' : 'middle'}
              fontSize={8.5}
              fill="var(--gp-faint)"
              style={MONO}
            >
              {X_LABELS[i]}
            </text>
          ))}

          {/* hover crosshair + dot, rendered only while hovering so the rest
              state stays pixel-identical to the reference */}
          {hp ? (
            <g pointerEvents="none">
              <line
                x1={geom.x(hp.min)}
                x2={geom.x(hp.min)}
                y1={M.top}
                y2={height - M.bottom}
                stroke="var(--gp-info)"
                strokeWidth={1}
                strokeDasharray="3 3"
                data-testid="balance-crosshair"
              />
              <circle
                cx={geom.x(hp.min)}
                cy={geom.y(hp.eth)}
                r={4}
                fill="var(--gp-ink)"
                stroke="var(--gp-card)"
                strokeWidth={2}
              />
            </g>
          ) : null}

          {/* Full-plot hit area. `touch-action: pan-y` is deliberate (as in
              charts.js): `none` would trap the finger and block page scroll
              over the chart on touch devices. */}
          <rect
            x={M.left}
            y={M.top}
            width={Math.max(1, width - M.left - M.right)}
            height={Math.max(1, height - M.top - M.bottom)}
            fill="transparent"
            style={{ cursor: 'crosshair', touchAction: 'pan-y' }}
            onPointerMove={onMove}
            onPointerLeave={onLeave}
            onPointerCancel={onLeave}
            data-testid="balance-hit"
          />
        </svg>
      ) : null}

      {/* dark hover tooltip, the one element shared 1:1 with the main site */}
      {hp && geom ? (
        <div className="chart-tip" style={{ left: tipLeft, top: 10, opacity: 1 }}>
          <div className="t-head">{fmtTimeOfDay(DESK.sessionStartMin + hp.min)}</div>
          <div className="t-row">
            <span className="sw" style={{ background: 'var(--gp-pos)' }} />
            Balance<b className="num">{fmt(hp.eth, 4)}</b>
          </div>
        </div>
      ) : null}
    </div>
  );
});
