import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Footer } from './Footer';

/**
 * The desk is deployed to `docs/gptheist/dist/index.html`, two directories
 * below the dashboard at `docs/index.html`. A single `../index.html` resolves
 * to `docs/gptheist/index.html` — which exists, so it is not a 404, but it is
 * the Vite *dev* entry (`<script src="/src/main.tsx">`) and renders a blank
 * page on Pages. The link therefore has to climb two levels.
 */
function resolveFrom(href: string, from = 'docs/gptheist/dist/index.html'): string {
  const parts = from.split('/').slice(0, -1);
  for (const seg of href.split('/')) {
    if (seg === '..') parts.pop();
    else if (seg !== '.' && seg !== '') parts.push(seg);
  }
  return parts.join('/');
}

describe('Footer', () => {
  it('links back to the CryptoTrade dashboard, not the Vite dev entry', () => {
    render(<Footer />);
    const link = screen.getByRole('link', { name: /CryptoTrade dashboard/ });
    const href = link.getAttribute('href') ?? '';
    expect(resolveFrom(href)).toBe('docs/index.html');
  });

  it('keeps the SIMULATED DATA badge', () => {
    render(<Footer />);
    expect(screen.getByText('SIMULATED DATA')).toBeInTheDocument();
  });
});
