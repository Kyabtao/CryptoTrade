import {
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';
import { randomFrom } from '../lib/prng';

export type NodeClass = 'bear' | 'bull' | 'catalyst' | 'neutral';
export type HubId = 'bear' | 'catalyst' | 'astra';
export type HubClass = 'hub-bear' | 'hub-catalyst' | 'hub-astra';

export type GraphNode = {
  id: number;
  cls: NodeClass | HubClass;
  r: number;
  x: number; // 0..1 layout space
  y: number;
};

export type GraphEdge = { source: number; target: number };

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  hubIndex: Record<HubId, number>;
};

type SimNode = SimulationNodeDatum & {
  id: number;
  cls: GraphNode['cls'];
  r: number;
  hub: HubId;
};
type SimLink = SimulationLinkDatum<SimNode>;

/** Hub anchors in normalised layout space (matches the reference framing). */
const ANCHORS: Record<HubId, { x: number; y: number }> = {
  bear: { x: 0.22, y: 0.34 },
  catalyst: { x: 0.78, y: 0.38 },
  astra: { x: 0.5, y: 0.78 },
};

const CLUSTER_OF: Record<HubId, NodeClass> = {
  bear: 'bear',
  catalyst: 'catalyst',
  astra: 'bull',
};

/**
 * ~90 nodes / 134 edges: three hubs (bear cluster, catalyst ring, astra prime)
 * with satellites, laid out by running a d3-force simulation once (seeded
 * start positions keep it deterministic). The component only renders and adds
 * a gentle jitter afterwards.
 */
export function generateForceGraph(seed = 1545): GraphData {
  const rng = randomFrom(seed);
  const hubIndex: Record<HubId, number> = { bear: 0, catalyst: 1, astra: 2 };

  const HUB_CLASS: Record<HubId, HubClass> = {
    bear: 'hub-bear',
    catalyst: 'hub-catalyst',
    astra: 'hub-astra',
  };

  const nodes: SimNode[] = (['bear', 'catalyst', 'astra'] as HubId[]).map((hub, i) => ({
    id: i,
    cls: HUB_CLASS[hub],
    r: hub === 'bear' ? 0.045 : 0.04,
    hub,
    x: ANCHORS[hub].x,
    y: ANCHORS[hub].y,
  }));

  const clusterSizes: Record<HubId, number> = { bear: 30, catalyst: 27, astra: 30 };
  const clusterOf: HubId[] = [];
  (Object.keys(clusterSizes) as HubId[]).forEach((hub) => {
    for (let i = 0; i < clusterSizes[hub]; i += 1) clusterOf.push(hub);
  });

  clusterOf.forEach((hub, k) => {
    const a = ANCHORS[hub];
    const base = CLUSTER_OF[hub];
    const cls: GraphNode['cls'] = rng.chance(0.6)
      ? base
      : rng.pick(['bear', 'bull', 'catalyst', 'neutral'] as NodeClass[]);
    nodes.push({
      id: 3 + k,
      cls,
      r: 0.008,
      hub,
      x: a.x + rng.normal(0, 0.09),
      y: a.y + rng.normal(0, 0.09),
    });
  });

  const edges: GraphEdge[] = [];
  // Satellites attach to their hub: 87 edges.
  nodes.slice(3).forEach((n) => {
    edges.push({ source: n.id, target: hubIndex[n.hub] });
  });
  // Hub triangle: 3 edges.
  edges.push({ source: 0, target: 1 }, { source: 1, target: 2 }, { source: 2, target: 0 });
  // Cross links up to 134 total.
  let guard = 0;
  while (edges.length < 134 && guard < 4000) {
    guard += 1;
    const a = rng.index(nodes.length);
    const b = rng.index(nodes.length);
    if (a === b) continue;
    if (edges.some((e) => (e.source === a && e.target === b) || (e.source === b && e.target === a)))
      continue;
    edges.push({ source: a, target: b });
  }

  // Run the simulation once, synchronously and deterministically.
  const links: SimLink[] = edges.map((e) => ({ source: e.source, target: e.target }));
  const sim = forceSimulation<SimNode>(nodes)
    .force(
      'link',
      forceLink<SimNode, SimLink>(links)
        .id((d) => d.id)
        .distance(0.07)
        .strength(0.25)
    )
    .force('charge', forceManyBody<SimNode>().strength(-0.0035))
    .force(
      'x',
      forceX<SimNode>((d) => ANCHORS[d.hub].x).strength((d) => (d.r > 0.02 ? 0.7 : 0.06))
    )
    .force(
      'y',
      forceY<SimNode>((d) => ANCHORS[d.hub].y).strength((d) => (d.r > 0.02 ? 0.7 : 0.06))
    )
    .stop();
  for (let i = 0; i < 250; i += 1) sim.tick();

  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      cls: n.cls,
      r: n.r,
      x: Math.min(0.98, Math.max(0.02, n.x ?? 0.5)),
      y: Math.min(0.96, Math.max(0.04, n.y ?? 0.5)),
    })),
    edges,
    hubIndex,
  };
}

export type HistogramBar = { value: number; color: string };

/** EDGE DISTRIBUTION / 24H: a bell of bars coloured red→pink→green→blue. */
export function generateEdgeHistogram(): HistogramBar[] {
  const values = [3, 5, 7, 9, 6, 11, 13, 12, 9, 7, 4, 3];
  return values.map((value, i) => ({
    value,
    color: i < 2 ? 'var(--gp-neg)' : i < 4 ? '#e77fa0' : i < 8 ? 'var(--gp-pos)' : 'var(--gp-info)',
  }));
}
