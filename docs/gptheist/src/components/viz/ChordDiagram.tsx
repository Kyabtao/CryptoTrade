import { chord } from 'd3-chord';
import { memo, useCallback, useMemo, useState } from 'react';
import { accentForCode, agentByCode } from '../../data/agents';
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

type RibbonShape = {
  key: string;
  d: string;
  fill: string;
  opacity: number;
  /** Agent indices + handoff counts in each direction of the pair. */
  si: number;
  ti: number;
  sv: number;
  tv: number;
};
type GroupShape = {
  key: string;
  gi: number;
  d: string;
  color: string;
  lx: number;
  ly: number;
  anchor: 'start' | 'middle' | 'end';
  code: string;
};

type Hover = { kind: 'arc' | 'ribbon'; idx: number; x: number; y: number };

/**
 * Handoff chord: d3-chord computes the layout angles; the arc/ribbon paths are
 * emitted as plain SVG so the component stays type-clean under the strict
 * linter. Ten role arcs are coloured by agent accent, ribbons stay a quiet grey
 * except the strongest passes.
 *
 * Hover has no main-site counterpart (charts.js has no chord), so only the
 * shared grammar applies: the hovered arc or ribbon lights up while the rest
 * dims, and a cursor-following dark `.chart-tip` names the agents and counts.
 */
export const ChordDiagram = memo(function ChordDiagram({ data }: { data: ChordData }) {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<Hover | null>(null);

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
        si: r.source.index,
        ti: r.target.index,
        sv: r.source.value,
        tv: r.target.value,
      };
    });

    const groups: GroupShape[] = chords.groups.map((g) => {
      const code = data.codes[g.index % data.codes.length] as AgentCode;
      const mid = (g.startAngle + g.endAngle) / 2;
      const sin = Math.sin(mid);
      return {
        key: 'grp' + String(g.index),
        gi: g.index,
        d: arcPath(g.startAngle, g.endAngle, inner, outer),
        color: accentVar(accentForCode(code)),
        lx: sin * (outer + 12),
        ly: -Math.cos(mid) * (outer + 12),
        anchor: sin > 0.25 ? 'start' : sin < -0.25 ? 'end' : 'middle',
        code,
      };
    });

    const out = new Array<number>(data.codes.length).fill(0);
    const inn = new Array<number>(data.codes.length).fill(0);
    data.matrix.forEach((row, i) => {
      row.forEach((v, j) => {
        out[i] = (out[i] ?? 0) + v;
        inn[j] = (inn[j] ?? 0) + v;
      });
    });

    return { ribbons, groups, out, inn, cx: width / 2, cy: height / 2 };
  }, [width, height, data.matrix, data.codes]);

  const showAt = useCallback(
    (kind: 'arc' | 'ribbon', idx: number, clientX: number, clientY: number) => {
      const node = ref.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      setHover({ kind, idx, x: clientX - rect.left, y: clientY - rect.top });
    },
    [ref]
  );
  const clear = useCallback(() => {
    setHover(null);
  }, []);

  /** Ribbons touching the hovered arc stay lit; everything else dims. */
  const ribbonLit = (i: number): boolean => {
    if (!hover || !geom) return false;
    if (hover.kind === 'ribbon') return hover.idx === i;
    const r = geom.ribbons[i];
    return r !== undefined && (r.si === hover.idx || r.ti === hover.idx);
  };
  const arcLit = (gi: number): boolean => {
    if (!hover || !geom) return false;
    if (hover.kind === 'arc') return hover.idx === gi;
    const r = geom.ribbons[hover.idx];
    return r !== undefined && (r.si === gi || r.ti === gi);
  };

  const tip =
    hover && geom
      ? {
          left: Math.max(4, Math.min(hover.x + 14, Math.max(4, width - 140))),
          top: Math.max(4, Math.min(hover.y + 12, Math.max(4, height - 76))),
        }
      : null;

  const arcIdx = hover?.kind === 'arc' ? hover.idx : null;
  const arcCode = arcIdx != null ? String(data.codes[arcIdx % data.codes.length] ?? '') : null;
  const arcAgent = arcCode ? agentByCode(arcCode) : undefined;
  const arcOut = arcIdx != null ? (geom?.out[arcIdx] ?? 0) : 0;
  const arcIn = arcIdx != null ? (geom?.inn[arcIdx] ?? 0) : 0;
  const ribTip = hover?.kind === 'ribbon' ? (geom?.ribbons[hover.idx] ?? null) : null;

  return (
    <div ref={ref} className="relative h-full w-full">
      {geom ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Handoff chord diagram between the ten agent roles"
          className="block"
          onPointerLeave={clear}
          onPointerCancel={clear}
        >
          <g transform={'translate(' + String(geom.cx) + ', ' + String(geom.cy) + ')'}>
            {geom.ribbons.map((r, i) => (
              <path
                key={r.key}
                d={r.d}
                fill={r.fill}
                fillOpacity={!hover ? r.opacity : ribbonLit(i) ? 0.9 : 0.08}
                stroke="var(--gp-hairline)"
                strokeWidth={0.5}
                onPointerMove={(e) => {
                  showAt('ribbon', i, e.clientX, e.clientY);
                }}
                data-testid={'chord-ribbon-' + String(i)}
              />
            ))}
            {geom.groups.map((g) => (
              <g
                key={g.key}
                onPointerMove={(e) => {
                  showAt('arc', g.gi, e.clientX, e.clientY);
                }}
                data-testid={'chord-arc-' + g.code}
              >
                <path d={g.d} fill={g.color} opacity={!hover ? 0.9 : arcLit(g.gi) ? 1 : 0.35} />
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

      {tip && arcCode ? (
        <div className="chart-tip" style={{ left: tip.left, top: tip.top, opacity: 1 }}>
          <div className="t-head">{arcAgent ? arcAgent.name + ' · ' + arcAgent.role : arcCode}</div>
          <div className="t-row">
            <span className="sw" style={{ background: accentVar(accentForCode(arcCode)) }} />
            Out<b className="num">{String(arcOut)}</b>
          </div>
          <div className="t-row">
            <span className="sw" style={{ background: accentVar(accentForCode(arcCode)) }} />
            In<b className="num">{String(arcIn)}</b>
          </div>
        </div>
      ) : null}

      {tip && ribTip && hover?.kind === 'ribbon' ? (
        <RibbonTip
          left={tip.left}
          top={tip.top}
          src={String(data.codes[ribTip.si % data.codes.length] ?? '')}
          tgt={String(data.codes[ribTip.ti % data.codes.length] ?? '')}
          sv={ribTip.sv}
          tv={ribTip.tv}
        />
      ) : null}
    </div>
  );
});

function RibbonTip({
  left,
  top,
  src,
  tgt,
  sv,
  tv,
}: {
  left: number;
  top: number;
  src: string;
  tgt: string;
  sv: number;
  tv: number;
}) {
  return (
    <div className="chart-tip" style={{ left, top, opacity: 1 }}>
      <div className="t-head">{src + ' → ' + tgt}</div>
      {sv > 0 ? (
        <div className="t-row">
          <span className="sw" style={{ background: accentVar(accentForCode(src)) }} />
          {src + '→' + tgt}
          <b className="num">{String(sv)}</b>
        </div>
      ) : null}
      {tv > 0 ? (
        <div className="t-row">
          <span className="sw" style={{ background: accentVar(accentForCode(tgt)) }} />
          {tgt + '→' + src}
          <b className="num">{String(tv)}</b>
        </div>
      ) : null}
    </div>
  );
}
