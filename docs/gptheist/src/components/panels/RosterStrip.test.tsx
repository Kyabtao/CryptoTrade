import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RosterStrip } from './RosterStrip';

describe('RosterStrip', () => {
  it('renders a portrait for every crew member', () => {
    render(<RosterStrip />);
    for (const name of [
      'TOKYO',
      'PALERMO',
      'DENVER',
      'STOCKHOLM',
      'PROFESSOR',
      'RIO',
      'HELSINKI',
      'NAIROBI',
      'BERLIN',
      'LISBON',
    ]) {
      expect(screen.getByRole('img', { name: name + ' avatar' })).toBeInTheDocument();
    }
  });

  it('marks the active agents with coloured borders', () => {
    const { container } = render(<RosterStrip />);
    const palermo = screen.getByRole('region', { name: /PALERMO/ });
    expect(palermo.className).toContain('border-pos');
    const professor = screen.getByRole('region', { name: /PROFESSOR/ });
    expect(professor.className).toContain('border-info');
    expect(container.querySelectorAll('section')).toHaveLength(10);
  });
});
