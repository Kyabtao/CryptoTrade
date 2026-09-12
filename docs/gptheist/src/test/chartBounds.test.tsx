import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { BalanceChart } from '../components/viz/BalanceChart';
import { ChordDiagram } from '../components/viz/ChordDiagram';
import { ForceGraph } from '../components/viz/ForceGraph';
import { Penteract } from '../components/viz/Penteract';
import { RidgePlot } from '../components/viz/RidgePlot';
import { generateBalanceHistory } from '../data/balance';
import { generateChordMatrix } from '../data/chord';
import { generateForceGraph } from '../data/graph';
import { generateRidgeData } from '../data/ridge';
import { DESK, minSinceSessionStart } from '../config';

/**
 * Chart geometry must stay inside the box the chart measured.
 *
 * jsdom has no layout engine, so `useMeasure` normally reads 0×0 and every
 * visualisation renders nothing. Stubbing `getBoundingClientRect` lets the real
 * components lay themselves out at the narrowest width the desk can produce
 * (a full-width panel on a 320px phone ≈ 254px) and at a desktop width, and
 * then every coordinate and text run is checked against the box.
 *
 * Text width uses the exact JetBrains Mono advance (600/1000 em — every glyph
 * in the face is monospaced), so the check is not an approximation for the
 * mono labels the charts use.
 */

const MONO_ADVANCE = 0.6;

/** Narrowest and widest box a chart can be asked to draw into. */
const BOXES: Array<[number, number]> = [
  [254, 220],
  [420, 220],
  [1180, 220],
];

type Violation = string;

function textWidth(text: string, fontSize: number, letterSpacing = 0): number {
  return text.length * fontSize * MONO_ADVANCE + Math.max(0, text.length - 1) * letterSpacing;
}

/**
 * `translate(x,y)` on an ancestor shifts every coordinate below it. Anything
 * else (rotate/scale/matrix) is not modelled, so that subtree is skipped and
 * reported — the check never silently passes over geometry it did not read.
 */
function translateOf(el: Element): [number, number] | null {
  const t = el.getAttribute('transform');
  if (!t) return [0, 0];
  let ox = 0;
  let oy = 0;
  const fn = /([a-zA-Z]+)\(([^)]*)\)/g;
  let m: RegExpExecArray | null;
  while ((m = fn.exec(t)) !== null) {
    const [, name, args] = m;
    if (name !== 'translate') return null;
    const nums = (args ?? '').split(/[\s,]+/).map(Number);
    ox += nums[0] ?? 0;
    oy += nums[1] ?? 0;
  }
  return [ox, oy];
}

function scanSvg(svg: SVGSVGElement, w: number, h: number, who: string): Violation[] {
  const out: Violation[] = [];
  const skipped: string[] = [];

  const walk = (el: Element, ox: number, oy: number) => {
    const own = translateOf(el);
    if (own === null) {
      skipped.push(el.tagName);
      return;
    }
    const ax = ox + own[0];
    const ay = oy + own[1];

    for (const axis of ['x', 'cx', 'x1', 'x2'] as const) {
      const v = el.getAttribute(axis);
      if (v !== null && /^-?[\d.]+$/.test(v)) {
        const abs = Number(v) + ax;
        if (abs < -1 || abs > w + 1)
          out.push(`${who}: ${axis}=${abs.toFixed(1)} outside 0..` + String(w));
      }
    }
    for (const axis of ['y', 'cy', 'y1', 'y2'] as const) {
      const v = el.getAttribute(axis);
      if (v !== null && /^-?[\d.]+$/.test(v)) {
        const abs = Number(v) + ay;
        if (abs < -1 || abs > h + 1)
          out.push(`${who}: ${axis}=${abs.toFixed(1)} outside 0..` + String(h));
      }
    }

    // Path data: coordinates alternate x/y in the commands these charts emit.
    const d = el.getAttribute('d');
    if (d) {
      const nums = (d.match(/-?\d*\.?\d+/g) ?? []).map(Number);
      for (let i = 0; i < nums.length; i += 2) {
        const px = (nums[i] ?? 0) + ax;
        const py = (nums[i + 1] ?? 0) + ay;
        if (px < -1 || px > w + 1)
          out.push(`${who}: path x ${px.toFixed(1)} outside 0..` + String(w));
        if (nums[i + 1] !== undefined && (py < -1 || py > h + 1))
          out.push(`${who}: path y ${py.toFixed(1)} outside 0..` + String(h));
      }
    }

    if (el.tagName === 'text') {
      const xAttr = el.getAttribute('x');
      const x = (xAttr === null ? 0 : Number(xAttr)) + ax;
      const fsAttr = el.getAttribute('font-size');
      const lsAttr = el.getAttribute('letter-spacing');
      const size = fsAttr === null ? 10 : Number(fsAttr);
      const ls = lsAttr === null ? 0 : Number(lsAttr);
      const anchor = el.getAttribute('text-anchor') ?? 'start';
      const body = el.textContent;
      const tw = textWidth(body, size, ls);
      const left = anchor === 'middle' ? x - tw / 2 : anchor === 'end' ? x - tw : x;
      if (left < -1) out.push(`${who}: text "${body}" starts at ${left.toFixed(1)}`);
      if (left + tw > w + 1)
        out.push(`${who}: text "${body}" ends at ${(left + tw).toFixed(1)} > ` + String(w));
    }

    for (const child of Array.from(el.children)) walk(child, ax, ay);
  };

  walk(svg, 0, 0);
  if (skipped.length > 0) out.push(`${who}: SKIPPED (unmodelled transform) ${skipped.join(',')}`);
  return out;
}

function charts(): Array<[string, React.ReactElement]> {
  return [
    [
      'BalanceChart',
      <BalanceChart
        series={generateBalanceHistory({
          seed: 7,
          startEth: DESK.balanceStartEth,
          endEth: DESK.initialBalanceEth,
          nowMin: minSinceSessionStart(DESK.wallClockMin),
        })}
        balanceEth={DESK.initialBalanceEth}
      />,
    ],
    ['RidgePlot', <RidgePlot data={generateRidgeData({ seed: 1363 })} />],
    ['ChordDiagram', <ChordDiagram data={generateChordMatrix(111)} />],
    ['Penteract', <Penteract />],
    ['ForceGraph', <ForceGraph data={generateForceGraph(1545)} />],
  ];
}

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

describe('chart geometry stays inside the measured box', () => {
  const original = Element.prototype.getBoundingClientRect.bind(Element.prototype);
  beforeEach(() => {
    Element.prototype.getBoundingClientRect = original;
  });

  for (const [w, h] of BOXES) {
    it(`draws inside ${String(w)}×${String(h)}`, () => {
      stubRect(w, h);
      const violations: Violation[] = [];
      for (const [name, node] of charts()) {
        const { container } = render(<div style={{ width: w, height: h }}>{node}</div>);
        const svg = container.querySelector('svg');
        // A chart that renders nothing here would make the check vacuous.
        expect(svg, `${name} rendered no <svg> at ${String(w)}px`).toBeTruthy();
        violations.push(...scanSvg(svg as SVGSVGElement, w, h, `${name}@${String(w)}`));
      }
      expect(violations).toEqual([]);
    });
  }
});

describe('the bounds scanner actually detects violations', () => {
  it('flags coordinates and text outside the box', () => {
    document.body.innerHTML =
      '<svg><g transform="translate(100,50)">' +
      '<circle cx="300" cy="10" r="2"/>' +
      '<text x="0" y="0" font-size="10" text-anchor="start">012345678901234567890123456789</text>' +
      '</g></svg>';
    const svg = document.body.querySelector('svg') as unknown as SVGSVGElement;
    const found = scanSvg(svg, 254, 220, 'control');
    expect(found.some((v) => v.includes('cx=400.0'))).toBe(true);
    // x=0 + translate(100) + 30 chars * 10px * 0.6em = 280 > 254
    expect(found.some((v) => v.includes('ends at 280.0'))).toBe(true);
  });

  it('reports rather than skips geometry behind an unmodelled transform', () => {
    document.body.innerHTML = '<svg><g transform="rotate(12)"><circle cx="9" cy="9"/></g></svg>';
    const svg = document.body.querySelector('svg') as unknown as SVGSVGElement;
    expect(scanSvg(svg, 254, 220, 'control').join()).toContain('SKIPPED');
  });
});
