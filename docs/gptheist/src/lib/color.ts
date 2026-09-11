import type { AgentAccent } from '../types';

/** Resolve an agent accent to the live CSS variable from theme.css. */
export function accentVar(accent: AgentAccent): string {
  switch (accent) {
    case 'pos':
      return 'var(--gp-pos)';
    case 'neg':
      return 'var(--gp-neg)';
    case 'info':
      return 'var(--gp-info)';
    case 'node':
      return 'var(--gp-node)';
    case 'teal':
      return 'var(--gp-teal)';
    case 'amber':
      return 'var(--gp-amber)';
  }
}

/** Resolve an agent accent to a Tailwind text class. */
export function accentText(accent: AgentAccent): string {
  switch (accent) {
    case 'pos':
      return 'text-pos';
    case 'neg':
      return 'text-neg';
    case 'info':
      return 'text-info';
    case 'node':
      return 'text-node';
    case 'teal':
      return 'text-teal';
    case 'amber':
      return 'text-amber';
  }
}

/** Resolve an agent accent to a Tailwind border class. */
export function accentBorder(accent: AgentAccent): string {
  switch (accent) {
    case 'pos':
      return 'border-pos';
    case 'neg':
      return 'border-neg';
    case 'info':
      return 'border-info';
    case 'node':
      return 'border-node';
    case 'teal':
      return 'border-teal';
    case 'amber':
      return 'border-amber';
  }
}
