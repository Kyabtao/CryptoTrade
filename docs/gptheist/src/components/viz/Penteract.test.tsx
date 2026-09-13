import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Penteract } from './Penteract';

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
  return render(<Penteract />);
}

describe('Penteract hover', () => {
  it('renders no tooltip and ungrown vertices at rest', () => {
    const { container } = setup();
    expect(container.querySelector('.chart-tip')).toBeNull();
    const dots = [...container.querySelectorAll('[data-testid^="penteract-dot-"]')];
    expect(dots).toHaveLength(32);
    for (const d of dots) expect(d.getAttribute('r')).toBe('2.1');
  });

  it('grows the vertex and shows its index and 5-D signs', () => {
    const { container } = setup();
    const hit = container.querySelector('[data-testid="penteract-v-5"]') as Element;
    expect(hit).toBeTruthy();
    pointerMove(hit);

    expect(container.querySelector('[data-testid="penteract-dot-5"]')?.getAttribute('r')).toBe(
      '4.5'
    );
    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toBe('VERTEX 05');
    // Vertex 5 = bits (+1,-1,+1,-1,-1) in binary order.
    expect(tip?.querySelector('.t-row b')?.textContent).toBe('+-+--');
  });

  it('hides the tooltip and shrinks the vertex on pointer leave', () => {
    const { container } = setup();
    const hit = container.querySelector('[data-testid="penteract-v-0"]') as Element;
    pointerMove(hit);
    expect(container.querySelector('.chart-tip')).toBeTruthy();
    fireEvent.pointerLeave(container.querySelector('svg') as SVGSVGElement);
    expect(container.querySelector('.chart-tip')).toBeNull();
    expect(container.querySelector('[data-testid="penteract-dot-0"]')?.getAttribute('r')).toBe(
      '2.1'
    );
  });
});
