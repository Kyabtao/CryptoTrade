import type { ReactNode } from 'react';

type CardMode =
  /** `// BALANCE HISTORY` — uppercase mono muted, as on row 2. */
  | { kind: 'mono' }
  /** `● Tail Probability Ridge` — sans semibold with a coloured status dot. */
  | { kind: 'dot'; dotClass: string };

export type CardProps = {
  title: string;
  mode?: CardMode;
  /** Small mono caption pinned to the top-right, e.g. `ETH / 13H`. */
  right?: ReactNode;
  /** Mono caption centred across the header, e.g. `STRIKE LANDSCAPE`. */
  center?: ReactNode;
  /** Footer strip under a hairline, e.g. `FILES, NOT MEMORY`. */
  footer?: ReactNode;
  /** Extra node (dot, tag) pinned to the top-right corner of the card. */
  corner?: ReactNode;
  headingLevel?: 2 | 3;
  ariaLabel?: string;
  className?: string;
  bodyClassName?: string;
  children?: ReactNode;
};

/**
 * The white 1px-hairline 10px-radius panel used everywhere on the desk.
 * Owns the header row (title + captions) and an optional footer caption, so
 * every panel's chrome is identical by construction.
 */
export function Card({
  title,
  mode = { kind: 'dot', dotClass: 'bg-ink' },
  right,
  center,
  footer,
  corner,
  headingLevel = 2,
  ariaLabel,
  className = '',
  bodyClassName = '',
  children,
}: CardProps) {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';

  const titleNode =
    mode.kind === 'mono' ? (
      <Heading className="label num text-[11px] font-medium tracking-[0.12em] text-muted">
        <span aria-hidden="true" className="mr-1 text-faint">
          //
        </span>
        {title}
      </Heading>
    ) : (
      <Heading className="flex items-center gap-2 text-[15px] font-semibold text-ink">
        <span aria-hidden="true" className={`size-2 rounded-full ${mode.dotClass}`} />
        {title}
      </Heading>
    );

  return (
    <section
      aria-label={ariaLabel ?? title}
      className={`relative flex flex-col rounded-card border border-hairline bg-card shadow-card ${className}`}
    >
      {corner ? <div className="absolute right-3 top-3">{corner}</div> : null}

      <header className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 px-4 pb-3 pt-4">
        {titleNode}
        <div className="label num justify-self-end text-[10px] text-faint">{right}</div>
        {center ? (
          <div className="label num col-span-2 -mt-1 justify-self-center text-[10px] text-faint">
            {center}
          </div>
        ) : null}
      </header>

      <div className={`flex-1 px-4 pb-4 ${bodyClassName}`}>{children}</div>

      {footer ? (
        <footer className="label num border-t border-hairline-soft px-4 py-2 text-[9px] text-faint">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}
