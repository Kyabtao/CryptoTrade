import { Card } from '../Card';
import { useDesk } from '../../store/deskStore';
import { accentForCode } from '../../data/agents';
import { accentText } from '../../lib/color';
import { fmtCount } from '../../lib/fmt';
import type { ActivityEvent } from '../../types';

const TONE_TEXT: Record<ActivityEvent['tone'], string> = {
  pos: 'text-pos',
  neg: 'text-neg',
  info: 'text-info',
  neutral: 'text-ink',
};

const TONE_DOT: Record<ActivityEvent['tone'], string> = {
  pos: 'bg-pos',
  neg: 'bg-neg',
  info: 'bg-info',
  neutral: 'bg-hairline',
};

function Row({ ev }: { ev: ActivityEvent }) {
  return (
    <div className="grid grid-cols-[34px_36px_1fr_10px] items-baseline gap-2 border-b border-hairline-soft py-[5px] last:border-b-0">
      <span className="num text-[9.5px] text-faint">{ev.time}</span>
      <span className={`num text-[9.5px] font-bold ${accentText(accentForCode(ev.code))}`}>
        {ev.code}
      </span>
      <span className="num truncate text-[9.5px] text-muted">{ev.message}</span>
      <span
        aria-hidden="true"
        className={`size-1.5 self-center justify-self-end rounded-full ${TONE_DOT[ev.tone]}`}
      />
    </div>
  );
}

export function ActivityLogPanel() {
  const events = useDesk((s) => s.events);
  const eventCount = useDesk((s) => s.eventCount);

  const [latest, ...rest] = events;

  return (
    <Card
      mode={{ kind: 'mono' }}
      title="ACTIVITY LOG"
      right={`${fmtCount(eventCount)} EVENTS`}
      className="col-span-12 lg:col-span-5"
      bodyClassName="h-full"
    >
      <div className="flex h-[220px] flex-col">
        {latest ? (
          <div className="mb-2 shrink-0 rounded-chip bg-[var(--gp-info-wash)] px-3 py-2">
            <div className="flex items-baseline gap-2">
              <span className="num text-[10px] text-faint">{latest.time}</span>
              <span
                className={`num text-[10px] font-bold ${accentText(accentForCode(latest.code))}`}
              >
                {latest.code}
              </span>
            </div>
            <p
              className={`num mt-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] ${TONE_TEXT[latest.tone]}`}
            >
              {latest.message}
            </p>
          </div>
        ) : null}

        <div
          className="quiet-scroll min-h-0 flex-1 overflow-y-auto pr-1"
          aria-label="Activity log history"
        >
          {rest.map((ev) => (
            <Row key={ev.id} ev={ev} />
          ))}
        </div>
      </div>
    </Card>
  );
}
