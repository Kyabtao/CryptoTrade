import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { generateEdgeHistogram } from '../../data/graph';
import { Histogram } from './Histogram';

function pointerOver(bar: HTMLElement) {
  // A raw dispatch, unlike `fireEvent`, needs `act` to flush React — same
  // trick as BalanceChart.test.tsx (`pointerenter` itself is polyfilled by
  // React from over/out pairs, so the component listens to `pointermove`).
  act(() => {
    bar.dispatchEvent(new MouseEvent('pointermove', { bubbles: true }));
  });
}

describe('Histogram hover', () => {
  it('renders no tooltip at rest', () => {
    const { container } = render(<Histogram bars={generateEdgeHistogram()} />);
    expect(container.querySelector('.chart-tip')).toBeNull();
  });

  it('shows the bin and count above the hovered bar', () => {
    const bars = generateEdgeHistogram();
    const { container } = render(<Histogram bars={bars} />);
    const bar = container.querySelector('[data-testid="edge-bar-6"]') as HTMLElement;
    expect(bar).toBeTruthy();
    pointerOver(bar);
    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toBe('BIN 7 / 12');
    expect(tip?.querySelector('.t-row b')?.textContent).toBe(String(bars[6]?.value));
  });

  it('hides the tooltip on pointer leave', () => {
    const { container } = render(<Histogram bars={generateEdgeHistogram()} />);
    const bar = container.querySelector('[data-testid="edge-bar-0"]') as HTMLElement;
    pointerOver(bar);
    expect(container.querySelector('.chart-tip')).toBeTruthy();
    const wrap = container.firstElementChild as HTMLElement;
    fireEvent.pointerLeave(wrap);
    expect(container.querySelector('.chart-tip')).toBeNull();
  });
});
