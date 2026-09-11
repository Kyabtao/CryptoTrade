import { describe, expect, it } from 'vitest';
import { generateEdgeHistogram, generateForceGraph } from './graph';

describe('generateForceGraph', () => {
  it('is deterministic for a seed', () => {
    expect(generateForceGraph(1545)).toEqual(generateForceGraph(1545));
  });

  it('produces 90 nodes and 134 edges', () => {
    const g = generateForceGraph(1545);
    expect(g.nodes).toHaveLength(90);
    expect(g.edges).toHaveLength(134);
  });

  it('has the three labelled hubs first', () => {
    const g = generateForceGraph(1545);
    expect(g.nodes[0]?.cls).toBe('hub-bear');
    expect(g.nodes[1]?.cls).toBe('hub-catalyst');
    expect(g.nodes[2]?.cls).toBe('hub-astra');
  });

  it('keeps every node inside the normalised layout box', () => {
    const g = generateForceGraph(1545);
    for (const n of g.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(1);
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y).toBeLessThanOrEqual(1);
    }
  });

  it('references only existing nodes in edges', () => {
    const g = generateForceGraph(1545);
    for (const e of g.edges) {
      expect(e.source).toBeGreaterThanOrEqual(0);
      expect(e.source).toBeLessThan(90);
      expect(e.target).toBeGreaterThanOrEqual(0);
      expect(e.target).toBeLessThan(90);
      expect(e.source).not.toBe(e.target);
    }
  });
});

describe('generateEdgeHistogram', () => {
  it('returns a dozen positive bars', () => {
    const bars = generateEdgeHistogram();
    expect(bars).toHaveLength(12);
    for (const b of bars) expect(b.value).toBeGreaterThan(0);
  });
});
