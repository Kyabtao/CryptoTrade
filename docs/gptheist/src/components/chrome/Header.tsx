import { DESK } from '../../config';
import { FeatherLogo } from './FeatherLogo';

/**
 * Top bar: logo, title + red handle, and on the right a pulsing LIVE pill plus
 * the session clock `18:48 / 13H`.
 */
export function Header() {
  return (
    <header className="col-span-12 flex items-center gap-4 rounded-card border border-hairline bg-card px-4 py-3 shadow-card">
      <FeatherLogo />

      <h1 className="flex min-w-0 items-baseline gap-3 text-lg font-extrabold tracking-tight text-ink">
        <span className="whitespace-nowrap">{DESK.title}</span>
        <span aria-hidden="true" className="text-hairline">
          |
        </span>
        <span className="num truncate text-sm font-semibold text-neg">{DESK.handle}</span>
      </h1>

      <div className="ml-auto flex items-center gap-4">
        <span className="inline-flex items-center gap-2 rounded-full bg-pos px-4 py-1.5">
          <span aria-hidden="true" className="live-dot size-2.5 rounded-full" />
          <span className="num text-[11px] font-bold tracking-[0.12em] text-card">LIVE</span>
        </span>
        <span className="num text-sm font-semibold text-ink">
          {DESK.wallClock} <span className="text-faint">/</span> {DESK.sessionHours}H
        </span>
      </div>
    </header>
  );
}
