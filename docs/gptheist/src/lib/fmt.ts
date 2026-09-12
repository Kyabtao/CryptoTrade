/**
 * Every number on the desk is rendered through this module — one place to
 * change decimals, thousands separators or the sign convention.
 *
 * Functions never throw on junk input: `NaN`/`±Infinity` collapse to a
 * placeholder, because a half-generated frame must never blank a panel.
 */

const NIL = '—';

/**
 * Round half away from zero in *decimal* space.
 *
 * `(1.005).toFixed(2)` returns `"1.00"`: the double nearest 1.005 is actually
 * 1.00499999999999989, so the naive path drops a cent on a money display.
 * Shifting through exponent *notation* avoids that, because parsing the string
 * `"1.005e2"` yields exactly 100.5, which then rounds the way a human expects.
 */
function roundHalfUp(value: number, decimals: number): number {
  if (!Number.isFinite(value) || decimals < 0) return value;
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  // `String()` is load-bearing here: it yields the shortest decimal that
  // round-trips ("1.005"), and re-parsing "1.005e2" gives exactly 100.5.
  const shifted = Number(String(abs) + 'e' + String(decimals));
  const scaled = Number.isFinite(shifted) ? shifted : abs * 10 ** decimals;
  const rounded = Math.round(scaled);
  const back = Number(String(rounded) + 'e-' + String(decimals));
  return sign * (Number.isFinite(back) ? back : rounded / 10 ** decimals);
}

/** Fixed-decimal number, e.g. `fmt(0.01887, 4) === "0.0189"`. */
export function fmt(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return NIL;
  return roundHalfUp(value, decimals).toFixed(decimals);
}

/** Fixed-decimal number with thousands separators, e.g. `1,363`. */
export function fmtGrouped(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return NIL;
  return roundHalfUp(value, decimals).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Always-signed number: `+10.97`, `-0.42`, and `+0.00` for zero.
 * The explicit `+` is what makes a PnL column scannable.
 * A magnitude that rounds to zero is shown positive, so a sub-cent PnL never
 * renders as an alarming `-0.00`.
 */
export function fmtSigned(value: number, decimals = 2): string {
  return fmtSignedWith(value, '', decimals);
}

/** Signed number with a unit prefix, e.g. `fmtSignedWith(10.97, '$')` → `+$10.97`. */
export function fmtSignedWith(value: number, prefix: string, decimals = 2): string {
  if (!Number.isFinite(value)) return NIL;
  const rounded = roundHalfUp(value, decimals);
  const body = Math.abs(rounded).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const sign = rounded < 0 ? '-' : '+';
  return `${sign}${prefix}${body}`;
}

/** Plain prefixed number, e.g. `fmtWith(0.0189, '$')` → `$0.02` at 2dp. */
export function fmtWith(value: number, prefix: string, decimals = 2): string {
  if (!Number.isFinite(value)) return NIL;
  return `${prefix}${fmt(value, decimals)}`;
}

/** Signed percent, e.g. `fmtPct(21.18)` → `+21.18%`. */
export function fmtPct(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return NIL;
  return `${fmtSigned(value, decimals)}%`;
}

/** ETH balance at the desk's standard 4 decimals, e.g. `0.0189 ETH`. */
export function fmtEth(value: number, decimals = 4): string {
  if (!Number.isFinite(value)) return NIL;
  return `${fmt(value, decimals)} ETH`;
}

/** USD at 2 decimals, e.g. `$10.97`. */
export function fmtUsd(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return NIL;
  return `$${fmt(value, decimals)}`;
}

/** Signed USD, e.g. `+$10.97`. */
export function fmtUsdSigned(value: number, decimals = 2): string {
  return fmtSignedWith(value, '$', decimals);
}

/** Multiples, e.g. `fmtMult(40.9)` → `×40.9`. */
export function fmtMult(value: number, decimals = 1): string {
  if (!Number.isFinite(value)) return NIL;
  return `×${fmt(value, decimals)}`;
}

/** Cents, e.g. `fmtCents(1.3)` → `1.3¢`. */
export function fmtCents(value: number, decimals = 1): string {
  if (!Number.isFinite(value)) return NIL;
  return `${fmt(value, decimals)}¢`;
}

/** Signed cents, e.g. `+23¢`. */
export function fmtCentsSigned(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return NIL;
  return `${fmtSigned(value, decimals)}¢`;
}

/** Degrees without the unit, e.g. `fmtDeg(263)` → `263°`. */
export function fmtDeg(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return NIL;
  return `${fmt(value, decimals)}°`;
}

/** Seconds → `mm:ss`, e.g. `163` → `02:43`. Always two digits per part. */
export function fmtClock(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return NIL;
  const s = Math.floor(totalSeconds);
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return `${pad2(mm)}:${pad2(ss)}`;
}

/** Fractional hours → `hh:mm`, e.g. `fmtHours(13.5)` → `13:30`. */
export function fmtHours(hours: number): string {
  if (!Number.isFinite(hours)) return NIL;
  // Take the sign off before splitting, otherwise the floor of a negative
  // quotient puts a second minus sign on the minutes ("-03:-15").
  const sign = hours < 0 ? '-' : '';
  const total = Math.abs(Math.round(hours * 60));
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${sign}${pad2(hh)}:${pad2(mm)}`;
}

/** Minutes past midnight → `HH:MM`, e.g. `1128` → `18:48`. */
export function fmtTimeOfDay(minutesPastMidnight: number): string {
  if (!Number.isFinite(minutesPastMidnight)) return NIL;
  const m = ((Math.round(minutesPastMidnight) % 1440) + 1440) % 1440;
  return `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
}

/** Compact counts: `1.5k` past 10 000, plain integer below. */
export function fmtCount(value: number): string {
  if (!Number.isFinite(value)) return NIL;
  if (Math.abs(value) >= 10000) return `${fmt(value / 1000, 1)}k`;
  return fmtGrouped(Math.round(value));
}

function pad2(n: number): string {
  // String() first: `restrict-template-expressions` (rightly) refuses to let a
  // raw number into a template literal, where 1e-7 would render unhelpfully.
  const sign = n < 0 ? '-' : '';
  return sign + String(Math.abs(n)).padStart(2, '0');
}

/* ------------------------------------------------------------------ *
 * Sign colouring
 *
 * Panels must not pick colours ad hoc: these helpers turn a number into
 * the CSS variable it should be painted with, so "green means up" holds
 * everywhere and a palette change stays a one-line edit.
 * ------------------------------------------------------------------ */

export type Tone = 'pos' | 'neg' | 'neutral';

/** Classify a delta: strictly positive, strictly negative, or neither. */
export function toneOf(value: number, epsilon = 0): Tone {
  if (!Number.isFinite(value)) return 'neutral';
  if (value > epsilon) return 'pos';
  if (value < -epsilon) return 'neg';
  return 'neutral';
}

const TONE_CLASS: Record<Tone, string> = {
  pos: 'text-pos',
  neg: 'text-neg',
  neutral: 'text-muted',
};

const TONE_VAR: Record<Tone, string> = {
  pos: 'var(--gp-pos)',
  neg: 'var(--gp-neg)',
  neutral: 'var(--gp-muted)',
};

/** Tailwind text class for a value's sign. */
export function toneClass(value: number, epsilon = 0): string {
  return TONE_CLASS[toneOf(value, epsilon)];
}

/** CSS custom-property colour for a value's sign (for inline SVG fills). */
export function toneColor(value: number, epsilon = 0): string {
  return TONE_VAR[toneOf(value, epsilon)];
}

/**
 * Signed number already wrapped in a span with the right colour, so log rows
 * and KPI cards cannot drift apart. Returns a string of markup — callers use
 * it through `dangerouslySetInnerHTML` only for these pre-formatted values.
 */
export function signedHtml(value: number, decimals = 2, prefix = ''): string {
  const tone = toneOf(value);
  const text = fmtSignedWith(value, prefix, decimals);
  return `<span class="num ${TONE_CLASS[tone]}">${escapeHtml(text)}</span>`;
}

/** Minimal HTML escaping for anything interpolated into generated markup. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
