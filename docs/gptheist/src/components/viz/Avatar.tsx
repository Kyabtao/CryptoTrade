import { memo } from 'react';
import type { AgentCode } from '../../types';

type Hair = 'bob' | 'afro' | 'blond' | 'slick' | 'buzz' | 'bald' | 'curly';

type Features = {
  skin: string;
  hair: Hair;
  hairColor: string;
  beard?: string;
  glasses?: boolean;
};

/** Per-character look so the ten avatars stay distinct and recognisable. */
const FEATURES: Record<AgentCode, Features> = {
  TOKY: { skin: '#f2c9a0', hair: 'bob', hairColor: '#2b2b2b' },
  PALM: { skin: '#e8b48c', hair: 'slick', hairColor: '#6b6b6b', beard: '#7a7a74' },
  DENV: { skin: '#e8b48c', hair: 'buzz', hairColor: '#3a2b1e' },
  STOC: { skin: '#f2c9a0', hair: 'blond', hairColor: '#d9a441' },
  PROF: { skin: '#f2c9a0', hair: 'bob', hairColor: '#3a2b1e', glasses: true },
  RIO: { skin: '#e8b48c', hair: 'curly', hairColor: '#2b2b2b', beard: '#2b2b2b', glasses: true },
  HELS: { skin: '#f2c9a0', hair: 'bald', hairColor: '#2b2b2b', beard: '#1f1f1f' },
  NAIR: { skin: '#8d5a3b', hair: 'afro', hairColor: '#1f1f1f' },
  BERL: { skin: '#e8b48c', hair: 'slick', hairColor: '#4a4a46', beard: '#4a4a46' },
  LISB: { skin: '#f2c9a0', hair: 'bob', hairColor: '#6b4a2b' },
};

const SUIT = 'var(--gp-neg)';
const HEADSET = '#333333';

function HairPatch({ f }: { f: Features }) {
  switch (f.hair) {
    case 'bob':
      return <path d="M12 20c0-8 5-12 12-12s12 4 12 12v6h-4v-8H16v8h-4z" fill={f.hairColor} />;
    case 'afro':
      return <circle cx={24} cy={12} r={9} fill={f.hairColor} />;
    case 'blond':
      return (
        <g fill={f.hairColor}>
          <circle cx={17} cy={12} r={4.5} />
          <circle cx={24} cy={10} r={5} />
          <circle cx={31} cy={12} r={4.5} />
        </g>
      );
    case 'slick':
      return (
        <path d="M13 16c1-6 6-8 11-8s10 2 11 8l-2 2c-2-4-5-5-9-5s-7 1-9 5z" fill={f.hairColor} />
      );
    case 'buzz':
      return (
        <path d="M14 14c2-4 6-6 10-6s8 2 10 6l-1 3c-2-3-5-4-9-4s-7 1-9 4z" fill={f.hairColor} />
      );
    case 'curly':
      return (
        <g fill={f.hairColor}>
          <circle cx={16} cy={13} r={4} />
          <circle cx={24} cy={10} r={4.5} />
          <circle cx={32} cy={13} r={4} />
        </g>
      );
    case 'bald':
      return null;
  }
}

/**
 * A flat, pixel-flavoured crew portrait: red jumpsuit + headset, with the
 * hair/glasses/beard variations pinned per character in FEATURES. Pure inline
 * SVG — no external images.
 */
export const Avatar = memo(function Avatar({ code, name }: { code: AgentCode; name: string }) {
  const f = FEATURES[code];
  return (
    <svg viewBox="0 0 48 48" className="size-full" role="img" aria-label={name + ' avatar'}>
      {/* jumpsuit */}
      <path d="M8 46c1-8 7-12 16-12s15 4 16 12z" fill={SUIT} />
      <rect x={22.6} y={35} width={2.8} height={11} fill="var(--gp-card)" opacity={0.85} />

      {/* head */}
      <rect x={14} y={9} width={20} height={19} rx={7} fill={f.skin} />

      {/* hair / beard / glasses */}
      <HairPatch f={f} />
      {f.beard ? (
        <path d="M15 21c0 6 4 9 9 9s9-3 9-9v3c0 6-4 9-9 9s-9-3-9-9z" fill={f.beard} />
      ) : null}

      {/* eyes */}
      <circle cx={20} cy={18} r={1.4} fill="#111111" />
      <circle cx={28} cy={18} r={1.4} fill="#111111" />

      {f.glasses ? (
        <g fill="none" stroke="#111111" strokeWidth={1.1}>
          <circle cx={20} cy={18} r={3.4} />
          <circle cx={28} cy={18} r={3.4} />
          <path d="M23.4 18h1.2" />
        </g>
      ) : null}

      {/* headset: band over the head + mic to the mouth */}
      <path d="M12 16c0-8 6-11 12-11s12 3 12 11" fill="none" stroke={HEADSET} strokeWidth={2} />
      <circle cx={12} cy={18} r={2.4} fill={HEADSET} />
      <path d="M12 20c1 4 4 6 8 6" fill="none" stroke={HEADSET} strokeWidth={1.4} />
      <circle cx={21} cy={26} r={1.4} fill={HEADSET} />
    </svg>
  );
});
