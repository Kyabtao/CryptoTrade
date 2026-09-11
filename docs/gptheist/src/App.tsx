/**
 * Application root.
 *
 * Milestone 1 is the scaffold, so this renders a deliberately small screen
 * that exercises the whole toolchain end to end: the React mount, the
 * Tailwind build, the CSS variables in theme.css and the self-hosted fonts.
 * The panel grid replaces it in the next milestone.
 */
function App() {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex items-center gap-3 border-b border-hairline bg-card px-5 py-3">
        <span
          aria-hidden="true"
          className="grid size-8 place-items-center rounded-[8px] bg-pos text-card"
        >
          <FeatherGlyph className="size-4" />
        </span>
        <h1 className="font-mono text-sm font-bold tracking-[0.08em] text-ink">GPTHEIST DESK</h1>
      </header>

      <main className="mx-auto max-w-[1600px] px-5 py-8">
        <div className="rounded-card border border-hairline bg-card p-6 shadow-card">
          <p className="label">Scaffold</p>
          <h2 className="mt-2 text-2xl font-semibold text-ink">Toolchain is live</h2>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Vite + React 18 + TypeScript (strict), Tailwind CSS 4, D3 v7 modules, Zustand, Vitest.
            Panels arrive in the next milestones.
          </p>
          <dl className="mt-6 grid gap-4 sm:grid-cols-3">
            <Token name="Positive" swatch="bg-pos" value="#1f9d55" />
            <Token name="Negative" swatch="bg-neg" value="#d33333" />
            <Token name="Flow" swatch="bg-info" value="#2f6fed" />
          </dl>
        </div>
      </main>
    </div>
  );
}

function Token({ name, swatch, value }: { name: string; swatch: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className={`size-3 rounded-chip ${swatch}`} />
      <dt className="label">{name}</dt>
      <dd className="num ml-auto text-xs text-ink">{value}</dd>
    </div>
  );
}

/** The desk's mark: a white feather on a green rounded square (inline SVG). */
export function FeatherGlyph({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M20.5 3.2c-5.2-.6-10.1 1.2-13.7 4.8-3.4 3.4-5.3 8.1-5.3 12.9 0 .7.1 1.4.2 2l2.8-2.8c.4-3.5 1.9-6.7 4.3-9.1 2.1-2.1 4.8-3.6 7.7-4.3-2 1.9-3.7 4-4.9 6.4-1.7 3.3-2.7 6.9-2.7 10.6h3.5c.8-3.5 2.4-6.7 4.6-9.3 1.9-2.3 2.8-4.8 3.5-11.2z" />
    </svg>
  );
}

export default App;
