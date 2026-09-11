import { line, curveCatmullRom } from 'd3-shape';
import { memo, useEffect, useMemo, useState } from 'react';
import { useMeasure } from '../../lib/useMeasure';
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion';
import type { GraphData, GraphNode, HubId } from '../../data/graph';

type Props = { data: GraphData };

function nodeColor(node: GraphNode): string {
  switch (node.cls) {
    case 'hub-bear':
      return '#e05c8a';
    case 'hub-catalyst':
      return 'var(--gp-teal)';
    case 'hub-astra':
      return 'var(--gp-node)';
    case 'bear':
      return 'var(--gp-neg)';
    case 'bull':
      return 'var(--gp-pos)';
    case 'catalyst':
      return 'var(--gp-teal)';
    case 'neutral':
      return 'var(--gp-faint)';
  }
}

const HUB_LABEL: Record<HubId, string> = {
  bear: 'BEAR CLUSTER',
  catalyst: 'CATALYST RING',
  astra: 'ASTRA PRIME',
};

/**
 * The relationship simulation: a force layout that ran once at data-generation
 * time, rendered as SVG with a gentle per-node jitter afterwards (frozen under
 * reduced motion). Shows the three labelled hubs, the dashed median path and
 * the blue APPROVED / FLOW tag.
 */
export const ForceGraph = memo(function ForceGraph({ data }: Props) {
  const [ref, { width, height }] = useMeasure<HTMLDivElement>();
  const reduced = usePrefersReducedMotion();
  const [now, setNow] = useState(0);

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

  const geom = useMemo(() => {
    if (width <= 0 || height <= 0) return null;
    const px = (n: GraphNode, i: number): [number, number] => {
      const jx = Math.sin(now / 900 + i * 1.7) * 1.2;
      const jy = Math.cos(now / 1100 + i * 2.3) * 1.0;
      return [n.x * width + jx, n.y * height + jy];
    };
    const pts = data.nodes.map((n, i) => px(n, i));
    const hubs = (['bear', 'catalyst', 'astra'] as HubId[]).map((h) => {
      const idx = data.hubIndex[h];
      const node = data.nodes[idx];
      const p = pts[idx];
      return { hub: h, node, p };
    });
    const median = line()
      .x((d) => d[0])
      .y((d) => d[1])
      .curve(curveCatmullRom);
    const bear = pts[data.hubIndex.bear];
    const catalyst = pts[data.hubIndex.catalyst];
    const astra = pts[data.hubIndex.astra];
    const medianPath =
      bear && catalyst && astra
        ? (median([
            [width * 0.04, height * 0.5],
            bear,
            astra,
            catalyst,
            [width * 0.96, height * 0.52],
          ]) ?? '')
        : '';
    return { pts, hubs, medianPath };
  }, [width, height, now, data]);

  return (
    <div ref={ref} className="relative h-full w-full">
      {geom ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Relationship graph simulation with bear cluster, catalyst ring and astra prime hubs"
          className="block"
        >
          {data.edges.map((e, i) => {
            const a = geom.pts[e.source];
            const b = geom.pts[e.target];
            if (!a || !b) return null;
            return (
              <line
                key={'e' + String(i)}
                x1={a[0]}
                y1={a[1]}
                x2={b[0]}
                y2={b[1]}
                stroke="var(--gp-hairline)"
                strokeWidth={0.7}
              />
            );
          })}

          <path
            d={geom.medianPath}
            fill="none"
            stroke="var(--gp-ink)"
            strokeWidth={1.1}
            strokeDasharray="5 4"
            opacity={0.7}
          />

          {data.nodes.map((n, i) => {
            const p = geom.pts[i];
            if (!p) return null;
            const hub = n.cls.startsWith('hub-');
            return (
              <circle
                key={'n' + String(n.id)}
                cx={p[0]}
                cy={p[1]}
                r={hub ? 12 : 2.1}
                fill={nodeColor(n)}
                stroke="var(--gp-card)"
                strokeWidth={hub ? 1.6 : 0.7}
                opacity={hub ? 0.9 : 0.85}
              />
            );
          })}

          {geom.hubs.map(({ hub, p }) =>
            p ? (
              <g
                key={'lbl' + hub}
                transform={'translate(' + String(p[0] - 34) + ', ' + String(p[1] + 18) + ')'}
              >
                <rect
                  width={68}
                  height={13}
                  rx={2.5}
                  fill="var(--gp-card)"
                  stroke="var(--gp-hairline)"
                  strokeWidth={0.8}
                />
                <text
                  x={34}
                  y={9}
                  textAnchor="middle"
                  fontSize={7.5}
                  fill="var(--gp-muted)"
                  style={{ fontFamily: 'var(--gp-font-mono)' }}
                >
                  {HUB_LABEL[hub]}
                </text>
              </g>
            ) : null
          )}

          <g transform={'translate(' + String(width * 0.42) + ', ' + String(height * 0.12) + ')'}>
            <rect width={84} height={15} rx={2.5} fill="var(--gp-info)" />
            <text
              x={42}
              y={10.5}
              textAnchor="middle"
              fontSize={8}
              fill="var(--gp-card)"
              style={{ fontFamily: 'var(--gp-font-mono)', fontWeight: 700 }}
            >
              APPROVED / FLOW
            </text>
          </g>
        </svg>
      ) : null}
    </div>
  );
});
