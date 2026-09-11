import { describe, expect, it } from 'vitest';
import {
  escapeHtml,
  fmt,
  fmtClock,
  fmtCount,
  fmtCentsSigned,
  fmtDeg,
  fmtEth,
  fmtHours,
  fmtMult,
  fmtPct,
  fmtSigned,
  fmtSignedWith,
  fmtTimeOfDay,
  fmtUsd,
  fmtUsdSigned,
  signedHtml,
  toneClass,
  toneColor,
  toneOf,
} from './fmt';

describe('fmt', () => {
  it('rounds to the requested decimals', () => {
    expect(fmt(0.01887, 4)).toBe('0.0189');
    expect(fmt(1.005, 2)).toBe('1.01');
    expect(fmt(263.4, 0)).toBe('263');
  });

  it('defaults to two decimals', () => {
    expect(fmt(1.5)).toBe('1.50');
  });

  it('rounds half away from zero in decimal space, not binary', () => {
    // The naive `(1.005).toFixed(2)` is "1.00" and would drop a cent.
    expect(fmt(1.005, 2)).toBe('1.01');
    expect(fmt(-1.005, 2)).toBe('-1.01');
    expect(fmt(2.675, 2)).toBe('2.68');
    expect(fmt(0.125, 2)).toBe('0.13');
  });

  it('falls back to a dash on non-finite input', () => {
    expect(fmt(Number.NaN)).toBe('—');
    expect(fmt(Number.POSITIVE_INFINITY)).toBe('—');
  });
});

describe('signed formatting', () => {
  it('always shows the sign', () => {
    expect(fmtSigned(10.97)).toBe('+10.97');
    expect(fmtSigned(-0.42)).toBe('-0.42');
    expect(fmtSigned(0)).toBe('+0.00');
  });

  it('never renders a negative zero for a sub-cent PnL', () => {
    expect(fmtSigned(-0.0001, 2)).toBe('+0.00');
    expect(fmtSignedWith(-0.0001, '$', 2)).toBe('+$0.00');
    expect(fmtSigned(-0.6, 0)).toBe('-1');
  });

  it('places the prefix between the sign and the digits', () => {
    expect(fmtSignedWith(10.97, '$')).toBe('+$10.97');
    expect(fmtSignedWith(-1234.5, '$')).toBe('-$1,234.50');
  });

  it('formats percentages and currencies the way the KPI strip shows them', () => {
    expect(fmtPct(21.18)).toBe('+21.18%');
    expect(fmtPct(-3.4, 1)).toBe('-3.4%');
    expect(fmtUsd(10.97)).toBe('$10.97');
    expect(fmtUsdSigned(10.97)).toBe('+$10.97');
    expect(fmtEth(0.01887)).toBe('0.0189 ETH');
  });

  it('formats market-flavoured units', () => {
    expect(fmtMult(40.9)).toBe('×40.9');
    expect(fmtMult(40)).toBe('×40.0');
    expect(fmtCentsSigned(23)).toBe('+23¢');
    expect(fmtCentsSigned(-5)).toBe('-5¢');
    expect(fmtDeg(263)).toBe('263°');
  });
});

describe('time formatting', () => {
  it('renders mm:ss countdowns with zero padding', () => {
    expect(fmtClock(163)).toBe('02:43');
    expect(fmtClock(59)).toBe('00:59');
    expect(fmtClock(0)).toBe('00:00');
    expect(fmtClock(3600)).toBe('60:00');
  });

  it('rejects nonsense durations', () => {
    expect(fmtClock(-1)).toBe('—');
    expect(fmtClock(Number.NaN)).toBe('—');
  });

  it('renders hh:mm from fractional hours', () => {
    expect(fmtHours(13)).toBe('13:00');
    expect(fmtHours(13.5)).toBe('13:30');
    expect(fmtHours(-2.25)).toBe('-02:15');
  });

  it('renders a wall-clock time from minutes past midnight, wrapping at 24h', () => {
    expect(fmtTimeOfDay(1128)).toBe('18:48');
    expect(fmtTimeOfDay(0)).toBe('00:00');
    expect(fmtTimeOfDay(1440)).toBe('00:00');
    expect(fmtTimeOfDay(-60)).toBe('23:00');
  });
});

describe('fmtCount', () => {
  it('groups thousands and abbreviates large counts', () => {
    expect(fmtCount(138)).toBe('138');
    expect(fmtCount(1363)).toBe('1,363');
    expect(fmtCount(9999)).toBe('9,999');
    expect(fmtCount(13_340)).toBe('13.3k');
    expect(fmtCount(1_545_000)).toBe('1545.0k');
  });
});

describe('sign colouring', () => {
  it('classifies deltas', () => {
    expect(toneOf(0.001)).toBe('pos');
    expect(toneOf(-0.001)).toBe('neg');
    expect(toneOf(0)).toBe('neutral');
    expect(toneOf(Number.NaN)).toBe('neutral');
  });

  it('honours an epsilon so tiny noise stays neutral', () => {
    expect(toneOf(0.0004, 0.001)).toBe('neutral');
    expect(toneOf(0.002, 0.001)).toBe('pos');
  });

  it('maps tones to the theme, not to hard-coded colours', () => {
    expect(toneClass(1)).toBe('text-pos');
    expect(toneClass(-1)).toBe('text-neg');
    expect(toneClass(0)).toBe('text-muted');
    expect(toneColor(1)).toBe('var(--gp-pos)');
    expect(toneColor(-1)).toBe('var(--gp-neg)');
  });

  it('wraps signed numbers in markup that carries the tone', () => {
    expect(signedHtml(10.97, 2, '$')).toBe('<span class="num text-pos">+$10.97</span>');
    expect(signedHtml(-2.5, 1)).toBe('<span class="num text-neg">-2.5</span>');
  });
});

describe('escapeHtml', () => {
  it('escapes everything that could break out of an attribute or text node', () => {
    expect(escapeHtml(`<a href="x">&'</a>`)).toBe(
      '&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;'
    );
  });
});
