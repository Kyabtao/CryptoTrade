import { AGENTS } from '../../data/agents';
import { accentBorder, accentText } from '../../lib/color';

/**
 * Bottom strip: ten agent cards in reference order. Milestone 2 renders the
 * structure, accents and active borders; the pixel avatars arrive with the
 * roster milestone.
 */
export function RosterStrip() {
  return (
    <div className="col-span-12 grid grid-cols-2 gap-4 sm:grid-cols-5 xl:grid-cols-10">
      {AGENTS.map((agent) => (
        <section
          key={agent.code}
          aria-label={`${agent.name} — ${agent.role}`}
          className={`flex flex-col items-center gap-2 rounded-card border bg-card px-2 py-3 shadow-card ${
            agent.state === 'active' ? accentBorder(agent.accent) : 'border-hairline'
          }`}
        >
          <div className="flex w-full items-center justify-between px-1">
            <span className="num text-[9px] text-faint">{agent.index}</span>
            <span
              aria-hidden="true"
              className="size-1.5 rounded-full"
              style={{ background: `var(--gp-${agent.accent})` }}
            />
          </div>

          {/* Avatar placeholder — replaced by inline SVG in the roster milestone. */}
          <div
            aria-hidden="true"
            className="num grid size-12 place-items-center rounded-[8px] bg-[var(--gp-neg-wash)] text-sm font-bold text-neg"
          >
            {agent.name.slice(0, 1)}
          </div>

          <div className="text-center">
            <h3 className="num text-[10px] font-bold text-ink">{agent.name}</h3>
            <p className={`label num mt-0.5 text-[8.5px] ${accentText(agent.accent)}`}>
              {agent.role}
            </p>
          </div>
        </section>
      ))}
    </div>
  );
}
