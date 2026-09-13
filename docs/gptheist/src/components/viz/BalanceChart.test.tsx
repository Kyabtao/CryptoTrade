import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DESK, minSinceSessionStart } from '../../config';
import { generateBalanceHistory } from '../../data/balance';
import { fmt, fmtTimeOfDay } from '../../lib/fmt';
import { BalanceChart } from './BalanceChart';

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

function series() {
  return generateBalanceHistory({
    seed: 7,
    startEth: DESK.balanceStartEth,
    endEth: DESK.initialBalanceEth,
    nowMin: minSinceSessionStart(DESK.wallClockMin),
  });
}

/**
 * jsdom's `PointerEvent` constructor drops `clientX` from the init dict, so
 * `fireEvent.pointerMove(hit, { clientX })` reaches the handler with
 * `clientX === undefined`. A `MouseEvent` carrying the `pointermove` type
 * still triggers React's `onPointerMove` and preserves the coordinates.
 */
function pointerMove(hit: SVGRectElement, clientX: number) {
  // `act` because a raw dispatch, unlike `fireEvent`, does not flush React.
  act(() => {
    hit.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX }));
  });
}

function setup() {
  stubRect(420, 220);
  const s = series();
  const rendered = render(<BalanceChart series={s} balanceEth={DESK.initialBalanceEth} />);
  const hit = rendered.container.querySelector('[data-testid="balance-hit"]');
  expect(hit, 'hit rect rendered').toBeTruthy();
  return { ...rendered, s, hit: hit as SVGRectElement };
}

describe('BalanceChart hover (main-site interaction contract)', () => {
  it('renders no tooltip, crosshair or dot at rest', () => {
    const { container } = setup();
    expect(container.querySelector('.chart-tip')).toBeNull();
    expect(container.querySelector('[data-testid="balance-crosshair"]')).toBeNull();
  });

  it('shows a crosshair, dot and dark tooltip at the nearest point on hover', () => {
    const { container, hit, s } = setup();
    pointerMove(hit, 80);
    const tip = container.querySelector('.chart-tip');
    expect(tip).toBeTruthy();
    // Nearest realised point to x=80 is series[21] (min 86 → 17:31).
    expect(s[21]?.min).toBe(86);
    expect(tip?.querySelector('.t-head')?.textContent).toBe('17:31');
    expect(tip?.querySelector('.t-row b')?.textContent).toBe(fmt(s[21]?.eth ?? NaN, 4));
    expect(container.querySelector('[data-testid="balance-crosshair"]')).toBeTruthy();
  });

  it('clamps hover past the realised portion to the live balance', () => {
    const { container, hit } = setup();
    // Far right of the 780-minute axis; the realised series ends at nowMin.
    pointerMove(hit, 400);
    const tip = container.querySelector('.chart-tip');
    expect(tip?.querySelector('.t-head')?.textContent).toBe(
      fmtTimeOfDay(DESK.sessionStartMin + minSinceSessionStart(DESK.wallClockMin))
    );
    expect(tip?.querySelector('.t-row b')?.textContent).toBe(fmt(DESK.initialBalanceEth, 4));
  });

  it('hides the tooltip and crosshair on pointer leave', () => {
    const { container, hit } = setup();
    pointerMove(hit, 80);
    expect(container.querySelector('.chart-tip')).toBeTruthy();
    fireEvent.pointerLeave(hit);
    expect(container.querySelector('.chart-tip')).toBeNull();
    expect(container.querySelector('[data-testid="balance-crosshair"]')).toBeNull();
  });

  it('keeps the hit area scroll-friendly for touch (pan-y, crosshair cursor)', () => {
    const { hit } = setup();
    expect(hit.getAttribute('fill')).toBe('transparent');
    expect(hit.style.touchAction).toBe('pan-y');
    expect(hit.style.cursor).toBe('crosshair');
  });
});
