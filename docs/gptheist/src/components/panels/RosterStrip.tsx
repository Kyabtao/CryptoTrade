import { AGENTS } from '../../data/agents';
import { accentBorder, accentText, accentVar } from '../../lib/color';
import { Avatar } from '../viz/Avatar';

/**
 * Bottom strip: ten agent cards in reference order, each with its flat SVG
 * portrait (red jumpsuit + headset), index, status dot, name and role. Active
 * agents get a coloured border and a tinted avatar backdrop.
 */
export function RosterStrip() {
  return (
    <div className="col-span-12 grid grid-cols-2 gap-4 sm:grid-cols-5 xl:grid-cols-10">
      {AGENTS.map((agent) => {
        const active = agent.state === 'active';
        return (
          <section
            key={agent.code}
            aria-label={agent.name + ' — ' + agent.role}
            className={`hoverable flex flex-col items-center gap-2 rounded-card border bg-card px-2 py-3 shadow-card ${
              active ? accentBorder(agent.accent) : 'border-hairline'
            }`}
          >
            <div className="flex w-full items-center justify-between px-1">
              <span className="num text-[9px] text-faint">{agent.index}</span>
              <span
                aria-hidden="true"
                className="size-1.5 rounded-full"
                style={{ background: accentVar(agent.accent) }}
              />
            </div>

            <div
              className="grid size-12 place-items-center overflow-hidden rounded-[8px]"
              style={{
                background: active
                  ? `color-mix(in srgb, ${accentVar(agent.accent)} 14%, transparent)`
                  : 'var(--gp-canvas)',
              }}
            >
              <Avatar code={agent.code} name={agent.name} />
            </div>

            <div className="text-center">
              <h3 className="num text-[10px] font-bold text-ink">{agent.name}</h3>
              <p className={`label num mt-0.5 text-[8.5px] ${accentText(agent.accent)}`}>
                {agent.role}
              </p>
            </div>
          </section>
        );
      })}
    </div>
  );
}
