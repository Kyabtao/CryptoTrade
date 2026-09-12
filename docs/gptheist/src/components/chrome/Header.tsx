import { DESK } from '../../config';
import { fmtTimeOfDay } from '../../lib/fmt';
import { useDesk } from '../../store/deskStore';
import { FeatherLogo } from './FeatherLogo';

/**
 * Top bar: logo, title + red handle, and on the right a pulsing LIVE pill plus
 * the live session clock `18:48 / 13H`.
 */
export function Header() {
  const wallMin = useDesk((s) => s.wallMin);

  return (
    <header className="col-span-12 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-card border border-hairline bg-card px-4 py-3 shadow-card">
      <FeatherLogo />

      <h1 className="flex min-w-0 items-baseline gap-3 text-lg font-extrabold tracking-tight text-ink">
        <span className="whitespace-nowrap">{DESK.title}</span>
        {/* The @handle is decorative; it is dropped below `sm` so the title
            never collides with the LIVE pill on a phone. */}
        <span aria-hidden="true" className="hidden text-hairline sm:inline">
          |
        </span>
        <span className="num hidden truncate text-sm font-semibold text-neg sm:inline">
          {DESK.handle}
        </span>
      </h1>

      <div className="ml-auto flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
        <span className="inline-flex items-center gap-2 rounded-full bg-pos px-4 py-1.5">
          <span aria-hidden="true" className="live-dot size-2.5 rounded-full" />
          <span className="num text-[11px] font-bold tracking-[0.12em] text-card">LIVE</span>
        </span>
        <span className="num text-sm font-semibold text-ink">
          {fmtTimeOfDay(wallMin)} <span className="text-faint">/</span> {DESK.sessionHours}H
        </span>
      </div>
    </header>
  );
}
