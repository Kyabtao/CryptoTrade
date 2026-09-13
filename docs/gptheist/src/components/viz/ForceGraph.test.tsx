import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { generateForceGraph } from '../../data/graph';
import { ForceGraph } from './ForceGraph';

/** jsdom returns an all-zero rect by default; report a real box instead. */
function stubRect(w: number, h: number) {
  Element.prototype.getBoundingClientRect = function rect() {
    return {
      width: w,
      height: h,
      top: 0,
      left: 0,
      right: w,
      bottom: h,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
  };
}

function pointerMove(el: Element) {
  // Raw dispatch needs `act` to flush React — same trick as BalanceChart.test.
  act(() => {
    el.dispatchEvent(new MouseEvent('pointermove', { bubbles: true }));
  });
}

function setup() {
  stubRect(420, 220);
  const data = generateForceGraph(1545);
  const rendered = render(<ForceGraph data={data} />);
  return { ...rendered, data };
}

function linksOf(data: ReturnType<typeof generateForceGraph>, id: number): number {
  return data.edges.filter((e) => e.source === id || e.target === id).length;
}

describe('ForceGraph hover', () => {
  it('renders no tooltip, ring or grown node at rest', () => {
    const { container } = setup();
    expect(container.querySelector('.chart-tip')).toBeNull();
    expect(container.querySelector('[data-testid="graph-hub-ring"]')).toBeNull();
    const dots = [...container.querySelectorAll('[data-testid^="graph-dot-"]')];
    expect(dots.length).toBeGreaterThan(0);
    for (const d of dots) expect(d.getAttribute('r')).toBe('2.1');
  });

  it('names a hub and counts its links, with a dashed ring', () => {
    const { container, data } = setup();
    const hub = container.querySelector('[data-testid="graph-node-0"]') as Element;
    expect(hub).toBeTruthy();
    pointerMove(hub);

    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toBe('BEAR CLUSTER');
    expect(tip?.querySelector('.t-row b')?.textContent).toBe(String(linksOf(data, 0)));
    const ring = container.querySelector('[data-testid="graph-hub-ring"]');
    expect(ring?.getAttribute('stroke-dasharray')).toBe('3 3');
  });

  it('grows a satellite and shows its id, links and class', () => {
    const { container, data } = setup();
    const hit = container.querySelector('[data-testid="graph-node-10"]') as Element;
    expect(hit).toBeTruthy();
    pointerMove(hit);

    expect(container.querySelector('[data-testid="graph-dot-10"]')?.getAttribute('r')).toBe('5.1');
    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toBe('NODE 10');
    const rows = [...(tip?.querySelectorAll('.t-row') ?? [])].map((r) => r.textContent ?? '');
    expect(rows[0]).toBe('Links' + String(linksOf(data, 10)));
    const node10 = data.nodes.find((nd) => nd.id === 10);
    expect(rows[1]).toBe('Class' + (node10?.cls.toUpperCase() ?? ''));
  });

  it('hides the tooltip on pointer leave', () => {
    const { container } = setup();
    const hub = container.querySelector('[data-testid="graph-node-1"]') as Element;
    pointerMove(hub);
    expect(container.querySelector('.chart-tip')).toBeTruthy();
    fireEvent.pointerLeave(container.querySelector('svg') as SVGSVGElement);
    expect(container.querySelector('.chart-tip')).toBeNull();
    expect(container.querySelector('[data-testid="graph-hub-ring"]')).toBeNull();
  });
});
