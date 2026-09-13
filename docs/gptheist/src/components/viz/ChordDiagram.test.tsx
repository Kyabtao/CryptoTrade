import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { agentByCode } from '../../data/agents';
import { generateChordMatrix } from '../../data/chord';
import { ChordDiagram } from './ChordDiagram';

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

function pointerMove(el: Element, clientX: number, clientY: number) {
  // Raw dispatch needs `act` to flush React; a MouseEvent typed as
  // `pointermove` preserves the coordinates jsdom's PointerEvent drops.
  act(() => {
    el.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX, clientY }));
  });
}

function setup() {
  stubRect(420, 220);
  const data = generateChordMatrix(111);
  const rendered = render(<ChordDiagram data={data} />);
  return { ...rendered, data };
}

describe('ChordDiagram hover', () => {
  it('renders no tooltip and full-strength arcs at rest', () => {
    const { container } = setup();
    expect(container.querySelector('.chart-tip')).toBeNull();
    const arcs = [...container.querySelectorAll('[data-testid^="chord-arc-"] path')];
    expect(arcs.length).toBe(10);
    for (const p of arcs) expect(p.getAttribute('opacity')).toBe('0.9');
  });

  it('names the agent and counts Out/In on arc hover, dimming the rest', () => {
    const { container, data } = setup();
    const arc = container.querySelector('[data-testid="chord-arc-TOKY"]') as Element;
    expect(arc).toBeTruthy();
    pointerMove(arc, 210, 60);

    const tip = container.querySelector('.chart-tip');
    const agent = agentByCode('TOKY');
    expect(tip?.querySelector('.t-head')?.textContent).toBe(agent?.name + ' · ' + agent?.role);
    const rows = [...(tip?.querySelectorAll('.t-row b') ?? [])].map((b) => b.textContent);
    const i = data.codes.indexOf('TOKY');
    const out = data.matrix[i]?.reduce((s, v) => s + v, 0) ?? -1;
    const inn = data.matrix.reduce((s, row) => s + (row[i] ?? 0), 0);
    expect(rows).toEqual([String(out), String(inn)]);

    // Hovered arc lit, another dimmed.
    expect(arc.querySelector('path')?.getAttribute('opacity')).toBe('1');
    const other = container.querySelector('[data-testid="chord-arc-RIO"] path');
    expect(other?.getAttribute('opacity')).toBe('0.35');
  });

  it('shows both directions of a pair on ribbon hover', () => {
    const { container } = setup();
    const ribbon = container.querySelector('[data-testid="chord-ribbon-0"]') as Element;
    expect(ribbon).toBeTruthy();
    pointerMove(ribbon, 210, 110);

    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toMatch(/^[A-Z]{4} → [A-Z]{4}$/);
    const rows = tip?.querySelectorAll('.t-row') ?? [];
    expect(rows.length).toBeGreaterThanOrEqual(1);
    for (const r of rows) expect(r.querySelector('b')?.textContent).toMatch(/^\d+$/);
  });

  it('hides the tooltip and restores opacity on pointer leave', () => {
    const { container } = setup();
    const ribbon = container.querySelector('[data-testid="chord-ribbon-0"]') as Element;
    pointerMove(ribbon, 210, 110);
    expect(container.querySelector('.chart-tip')).toBeTruthy();
    const svg = container.querySelector('svg') as SVGSVGElement;
    fireEvent.pointerLeave(svg);
    expect(container.querySelector('.chart-tip')).toBeNull();
    const arcs = [...container.querySelectorAll('[data-testid^="chord-arc-"] path')];
    for (const p of arcs) expect(p.getAttribute('opacity')).toBe('0.9');
  });
});
