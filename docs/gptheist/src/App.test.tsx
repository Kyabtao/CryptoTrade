import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App (shell)', () => {
  it('renders the desk title and handle', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1, name: /GPTHEIST DESK/ })).toBeInTheDocument();
    expect(screen.getByText('immortalhowwl')).toBeInTheDocument();
  });

  it('lays out every panel heading from the reference', () => {
    render(<App />);
    const names = [
      'BALANCE / ETH',
      'TOTAL PNL / USD',
      'MISSION CLOCK',
      'APPROVAL GATE',
      'BALANCE HISTORY',
      'ACTIVITY LOG',
      'Tail Probability Ridge',
      'Handoff Chord',
      '5D Strategy Lattice',
      'Relationship Graph Simulation',
    ];
    for (const name of names) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
  });

  it('shows the roster with the crew in reference order and active borders', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: /TOKYO/ })).toBeInTheDocument();
    expect(screen.getByText('SCOUTS')).toBeInTheDocument();
    expect(screen.getByText('SIMULATED DATA')).toBeInTheDocument();
  });
});
