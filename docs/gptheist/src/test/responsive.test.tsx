import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from '../App';
import { Card } from '../components/Card';
import { Header } from '../components/chrome/Header';
import { KpiStrip } from '../components/panels/KpiStrip';
import { RosterStrip } from '../components/panels/RosterStrip';

/**
 * Responsive contract for the 12-column desk.
 *
 * The breakpoints are Tailwind's defaults — sm 40rem, md 48rem, lg 64rem,
 * xl 80rem — which the compiled stylesheet confirms. These assertions pin the
 * class contracts the layout depends on so a refactor cannot silently un-stack
 * the desk on a phone or break the 12-column rows on a desktop.
 */

/** col-span a panel occupies at a breakpoint, read off its class list. */
function spanAt(className: string, bp: '' | 'sm' | 'md' | 'lg' | 'xl'): number {
  const prefix = bp === '' ? '' : bp + ':';
  const own = new RegExp(`(?:^|\\s)${prefix}col-span-(\\d+)(?:\\s|$)`).exec(className);
  if (own) return Number(own[1]);
  if (bp === '') return 1;
  const order = ['', 'sm', 'md', 'lg', 'xl'] as const;
  const i = order.indexOf(bp);
  for (let k = i - 1; k >= 0; k -= 1) {
    const name = order[k] ?? '';
    const p = name === '' ? '' : name + ':';
    const m = new RegExp(`(?:^|\\s)${p}col-span-(\\d+)(?:\\s|$)`).exec(className);
    if (m) return Number(m[1]);
  }
  return 1;
}

describe('desk grid contract', () => {
  const { container } = render(<App />);
  const main = container.querySelector('main') as HTMLElement;
  const kids = [...main.children];

  it('lays the shell out on a 12-column grid with a 16px gap', () => {
    expect(main.className).toContain('grid-cols-12');
    expect(main.className).toContain('gap-4'); // 1rem = 16px
    expect(main.className).toContain('max-w-[1600px]');
  });

  it('spans every row to exactly 12 columns at lg and above', () => {
    for (const bp of ['lg', 'xl'] as const) {
      let row = 0;
      for (const k of kids) {
        const span = spanAt(k.className, bp);
        expect(span, `${k.tagName} at ${bp}`).toBeLessThanOrEqual(12);
        if (row + span > 12) row = 0; // sparse auto-placement wraps
        row += span;
        expect(row, `${k.tagName} overflowed its row at ${bp}`).toBeLessThanOrEqual(12);
      }
    }
  });

  it('stacks every panel full width below lg', () => {
    for (const bp of ['', 'sm', 'md'] as const) {
      for (const k of kids) {
        expect(spanAt(k.className, bp), `${k.tagName} at "${bp || 'base'}"`).toBe(12);
      }
    }
  });
});

describe('panel and strip responsiveness', () => {
  it('grows the KPI strip 1 → 2 → 4 across and scales the values up from sm', () => {
    const { container } = render(<KpiStrip />);
    const strip = container.firstElementChild as HTMLElement;
    expect(strip.className).toContain('grid-cols-2');
    expect(strip.className).toContain('xl:grid-cols-4');
    const values = [...strip.querySelectorAll('p.num')].map((p) => p.className);
    const big = values.filter((c) => c.includes('text-[26px]') || c.includes('text-[21px]'));
    expect(big).toHaveLength(3);
    for (const c of big) {
      expect(c).toContain('text-[21px]'); // phone size that cannot overflow a 2-up card
      expect(c).toContain('sm:text-[26px]'); // reference size from 640px up
    }
    expect(strip.querySelector('div.flex.flex-wrap')?.className).toContain('justify-between');
  });

  it('grows the crew strip 2 → 5 → 10 across', () => {
    const { container } = render(<RosterStrip />);
    const strip = container.firstElementChild as HTMLElement;
    expect(strip.className).toContain('grid-cols-2');
    expect(strip.className).toContain('sm:grid-cols-5');
    expect(strip.className).toContain('xl:grid-cols-10');
    expect(strip.querySelectorAll('section')).toHaveLength(10);
  });

  it('lets the card header stack the caption under the title below sm', () => {
    const { container } = render(
      <Card title="Tail Probability Ridge" right="ONE RIDGE / ONE SESSION / TAILS PAY">
        <div />
      </Card>
    );
    const head = container.querySelector('header') as HTMLElement;
    expect(head.className).toContain('grid-cols-1');
    expect(head.className).toContain('sm:grid-cols-[1fr_auto]');
    const caption = head.querySelector('div.label') as HTMLElement;
    expect(caption.className).toContain('min-w-0');
    expect(caption.className).toContain('sm:justify-self-end');
  });

  it('wraps the top bar and drops the decorative handle below sm', () => {
    const { container } = render(<Header />);
    const bar = container.querySelector('header') as HTMLElement;
    expect(bar.className).toContain('flex-wrap');
    const handle = [...bar.querySelectorAll('span')].find((s) => s.textContent === 'immortalhowwl');
    expect(handle?.className).toContain('hidden');
    expect(handle?.className).toContain('sm:inline');
    expect(bar.querySelector('h1')?.className).toContain('min-w-0');
  });
});
