import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  PENTERACT_BOUND,
  penteractEdges,
  penteractVertices,
  project5to2,
  rotate5,
  rotationAt,
} from '../../lib/math5d';
import { useMeasure } from '../../lib/useMeasure';
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion';

/** One colour per 5-D axis, matching the D1–D5 legend. */
const AXIS_COLORS = [
  'var(--gp-pos)',
  'var(--gp-neg)',
  'var(--gp-node)',
  'var(--gp-amber)',
  'var(--gp-info)',
] as const;

export const AXIS_LEGEND = ['D1', 'D2', 'D3', 'D4', 'D5'] as const;

/** Compact sign string for a vertex's five ±1 coordinates, e.g. `+-+--`. */
function signsOf(v: readonly number[]): string {
  return v.map((c) => (c > 0 ? '+' : '-')).join('');
}

/**
 * Animated penteract: 32 vertices / 80 edges, rotated 5D→2D and slowly rotating in
 * two 5-D planes. Each edge takes the colour of the axis it translates along.
 * Driven by requestAnimationFrame off real time; under reduced motion the
 * lattice freezes at the fixed 263° frame.
 *
 * Hover follows the shared grammar: the vertex under the pointer grows and a
 * dark `.chart-tip` names it with its 5-D coordinates. Each 2.1px dot gets an
 * invisible r=9 hit circle — without it the vertices are unhoverable.
 */
export const Penteract = memo(function Penteract() {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();
  const reduced = usePrefersReducedMotion();
  const [now, setNow] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    if (reduced || typeof requestAnimationFrame === 'undefined') {
      setNow(0);
      return;
    }
    let raf = 0;
    const loop = () => {
      setNow(Date.now());
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [reduced]);

  const verts = useMemo(() => penteractVertices(), []);
  const edges = useMemo(() => penteractEdges(), []);

  const projected = useMemo(() => {
    if (width <= 0 || height <= 0) return null;
    const { a, b } = rotationAt(now);
    const cx = width / 2;
    const cy = height / 2;
    const scale = (Math.min(width, height) / 2 - 12) / PENTERACT_BOUND;
    const pts = verts.map((v) => {
      const [x, y] = project5to2(rotate5(v, a, b));
      return [cx + x * scale, cy - y * scale] as const;
    });
    return { pts, a, b };
  }, [verts, width, height, now]);

  const clear = useCallback(() => {
    setHover(null);
  }, []);

  const hv = hover != null ? (verts[hover] ?? null) : null;
  const hp = hover != null ? (projected?.pts[hover] ?? null) : null;
  const tip =
    hp && hv && hover != null
      ? {
          left: Math.max(4, hp[0] > width - 150 ? hp[0] - 144 : hp[0] + 14),
          top: Math.max(4, Math.min(hp[1] - 24, Math.max(4, height - 76))),
        }
      : null;

  return (
    <div ref={ref} className="relative h-full w-full">
      {projected ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Rotating penteract, the 5-cube: 32 vertices and 80 edges projected from five dimensions"
          className="block"
          onPointerLeave={clear}
          onPointerCancel={clear}
        >
          {edges.map((e) => {
            const pa = projected.pts[e.a];
            const pb = projected.pts[e.b];
            if (!pa || !pb) return null;
            return (
              <line
                key={String(e.a) + '-' + String(e.b)}
                x1={pa[0]}
                y1={pa[1]}
                x2={pb[0]}
                y2={pb[1]}
                stroke={AXIS_COLORS[e.axis] ?? 'var(--gp-info)'}
                strokeWidth={1}
                opacity={0.75}
              />
            );
          })}
          {projected.pts.map((p, i) => (
            <circle
              key={'v' + String(i)}
              cx={p[0]}
              cy={p[1]}
              r={hover === i ? 4.5 : 2.1}
              fill={AXIS_COLORS[i % 5] ?? 'var(--gp-node)'}
              stroke="var(--gp-card)"
              strokeWidth={0.8}
              data-testid={'penteract-dot-' + String(i)}
            />
          ))}
          {/* invisible hit layer over the 2.1px vertices */}
          {projected.pts.map((p, i) => (
            <circle
              key={'h' + String(i)}
              cx={p[0]}
              cy={p[1]}
              r={9}
              fill="transparent"
              style={{ cursor: 'pointer' }}
              onPointerMove={() => {
                setHover(i);
              }}
              data-testid={'penteract-v-' + String(i)}
            />
          ))}
        </svg>
      ) : null}

      {tip && hv && hover != null ? (
        <div className="chart-tip" style={{ left: tip.left, top: tip.top, opacity: 1 }}>
          <div className="t-head">{'VERTEX ' + String(hover).padStart(2, '0')}</div>
          <div className="t-row">
            <span
              className="sw"
              style={{ background: AXIS_COLORS[hover % 5] ?? 'var(--gp-node)' }}
            />
            5D<b className="num">{signsOf(hv)}</b>
          </div>
        </div>
      ) : null}
    </div>
  );
});
