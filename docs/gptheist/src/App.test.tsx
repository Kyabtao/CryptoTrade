import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App (scaffold)', () => {
  it('mounts and shows the desk title', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1, name: 'GPTHEIST DESK' })).toBeInTheDocument();
  });

  it('declares that the toolchain is live', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 2, name: /toolchain is live/i })).toBeVisible();
  });
});
