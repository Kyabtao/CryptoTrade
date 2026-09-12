import { chord } from 'd3-chord';
import { memo, useMemo } from 'react';
import { accentForCode } from '../../data/agents';
import { accentVar } from '../../lib/color';
import { useMeasure } from '../../lib/useMeasure';
import type { ChordData } from '../../data/chord';
import type { AgentCode } from '../../types';

/** Round + stringify a coordinate so paths are stable and lint-clean. */
const n = (x: number): string => String(Math.round(x * 100) / 100);

function polar(r: number, a: number): [number, number] {
  return [r * Math.sin(a), -r * Math.cos(a)];
}

/** Annular sector (group arc) between angles a0..a1, radii r0..r1. */
function arcPath(a0: number, a1: number, r0: number, r1: number): string {
  const [x0, y0] = polar(r1, a0);
  const [x1, y1] = polar(r1, a1);
  const [x2, y2] = polar(r0, a1);
  const [x3, y3] = polar(r0, a0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return (
    'M' +
    n(x0) +
    ',' +
    n(y0) +
    'A' +
    n(r1) +
    ',' +
    n(r1) +
    ' 0 ' +
    String(large) +
    ' 1 ' +
    n(x1) +
    ',' +
    n(y1) +
    'L' +
    n(x2) +
    ',' +
    n(y2) +
    'A' +
    n(r0) +
    ',' +
    n(r0) +
    ' 0 ' +
    String(large) +
    ' 0 ' +
    n(x3) +
    ',' +
    n(y3) +
    'Z'
  );
}

/** Ribbon between a source arc and a target arc at radius r. */
function ribbonPath(s0: number, s1: number, t0: number, t1: number, r: number): string {
  const [sx0, sy0] = polar(r, s0);
  const [sx1, sy1] = polar(r, s1);
  const [tx0, ty0] = polar(r, t0);
  const [tx1, ty1] = polar(r, t1);
  const ls = s1 - s0 > Math.PI ? 1 : 0;
  const lt = t1 - t0 > Math.PI ? 1 : 0;
  return (
    'M' +
    n(sx0) +
    ',' +
    n(sy0) +
    'A' +
    n(r) +
    ',' +
    n(r) +
    ' 0 ' +
    String(ls) +
    ' 1 ' +
    n(sx1) +
    ',' +
    n(sy1) +
    'Q0,0 ' +
    n(tx0) +
    ',' +
    n(ty0) +
    'A' +
    n(r) +
    ',' +
    n(r) +
    ' 0 ' +
    String(lt) +
    ' 1 ' +
    n(tx1) +
    ',' +
    n(ty1) +
    'Q0,0 ' +
    n(sx0) +
    ',' +
    n(sy0) +
    'Z'
  );
}

type RibbonShape = { key: string; d: string; fill: string; opacity: number };
type GroupShape = {
  key: string;
  d: string;
  color: string;
  lx: number;
  ly: number;
  anchor: 'start' | 'middle' | 'end';
  code: string;
};

/**
 * Handoff chord: d3-chord computes the layout angles; the arc/ribbon paths are
 * emitted as plain SVG so the component stays type-clean under the strict
 * linter. Ten role arcs are coloured by agent accent, ribbons stay a quiet grey
 * except the strongest passes.
 */
export const ChordDiagram = memo(function ChordDiagram({ data }: { data: ChordData }) {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();

  const geom = useMemo(() => {
    if (width <= 0 || height <= 0) return null;
    const size = Math.min(width, height);
    const outer = size / 2 - 24;
    const inner = outer - 7;

    const chords = chord().padAngle(0.04)(data.matrix);

    const ribbons: RibbonShape[] = chords.map((r, i) => {
      const srcCode = data.codes[r.source.index % data.codes.length] as AgentCode;
      const strong = r.source.value >= 6;
      return {
        key: 'rib' + String(i),
        d: ribbonPath(
          r.source.startAngle,
          r.source.endAngle,
          r.target.startAngle,
          r.target.endAngle,
          inner
        ),
        fill: strong ? accentVar(accentForCode(srcCode)) : '#d8d8d3',
        opacity: strong ? 0.28 : 0.5,
      };
    });

    const groups: GroupShape[] = chords.groups.map((g) => {
      const code = data.codes[g.index % data.codes.length] as AgentCode;
      const mid = (g.startAngle + g.endAngle) / 2;
      const sin = Math.sin(mid);
      return {
        key: 'grp' + String(g.index),
        d: arcPath(g.startAngle, g.endAngle, inner, outer),
        color: accentVar(accentForCode(code)),
        lx: sin * (outer + 12),
        ly: -Math.cos(mid) * (outer + 12),
        anchor: sin > 0.25 ? 'start' : sin < -0.25 ? 'end' : 'middle',
        code,
      };
    });

    return { ribbons, groups, cx: width / 2, cy: height / 2 };
  }, [width, height, data.matrix, data.codes]);

  return (
    <div ref={ref} className="h-full w-full">
      {geom ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Handoff chord diagram between the ten agent roles"
          className="block"
        >
          <g transform={'translate(' + String(geom.cx) + ', ' + String(geom.cy) + ')'}>
            {geom.ribbons.map((r) => (
              <path
                key={r.key}
                d={r.d}
                fill={r.fill}
                fillOpacity={r.opacity}
                stroke="var(--gp-hairline)"
                strokeWidth={0.5}
              />
            ))}
            {geom.groups.map((g) => (
              <g key={g.key}>
                <path d={g.d} fill={g.color} opacity={0.9} />
                <text
                  x={n(g.lx)}
                  y={n(g.ly)}
                  textAnchor={g.anchor}
                  fontSize={8.5}
                  fill={g.color}
                  style={{ fontFamily: 'var(--gp-font-mono)', fontWeight: 700 }}
                >
                  {g.code}
                </text>
              </g>
            ))}
          </g>
        </svg>
      ) : null}
    </div>
  );
});
