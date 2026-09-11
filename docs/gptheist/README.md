# GPTHEIST DESK

A **Money Heist**–themed control panel for a simulated AI multi-agent
crypto / prediction-market trading system. Everything you see is generated
locally in the browser from seeded mock data — **no exchange, wallet or market
API is contacted, and nothing is fetched at runtime.**

It lives entirely inside `docs/gptheist/` and is linked from the parent
CryptoTrade dashboard navigation (`GPTHEIST`).

---

## Run it

```bash
cd docs/gptheist
npm install
npm run dev          # http://localhost:5173
```

Production build and local preview of the built bundle:

```bash
npm run build        # type-checks, then emits ./dist
npm run preview      # http://localhost:4173
```

Quality gates:

```bash
npm run typecheck    # tsc -b, strict
npm run lint         # eslint, type-aware strict ruleset
npm run format:check # prettier
npm test             # vitest run
```

## Why `dist/` is committed

The parent site is published by **GitHub Pages straight from `main` / `docs`
with no build step** (see the root README). So the compiled bundle has to live
in git for the page to load in production. `node_modules/` and `coverage/` are
git-ignored by `docs/gptheist/.gitignore`; `dist/` deliberately is not.

Rebuild and commit after any source change:

```bash
npm run build && git add dist && git commit -m "chore(gptheist): rebuild bundle"
```

## Stack

| Concern       | Choice                                                                                                                 |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Build         | Vite 7                                                                                                                 |
| UI            | React 18 + TypeScript (`"strict": true`, no `any`)                                                                     |
| Styling       | Tailwind CSS 4 (`@tailwindcss/vite`) + `src/theme/theme.css` tokens                                                    |
| Visualisation | D3 v7 modules only — `d3-scale`, `d3-shape`, `d3-chord`, `d3-force`, `d3-array`. React owns the SVG; D3 does the math. |
| State         | Zustand                                                                                                                |
| Tests         | Vitest + React Testing Library                                                                                         |
| Fonts         | `@fontsource-variable/inter` and `@fontsource-variable/jetbrains-mono`, self-hosted — no CDN                           |

No UI component library, no chart library other than D3.

## Layout

```
src/
├── App.tsx              application root
├── main.tsx             mount + global stylesheet
├── types.ts             shared domain types
├── components/
│   ├── panels/*         one folder per dashboard panel (state + markup)
│   └── viz/*            pure SVG visualisations that take data props
├── data/                deterministic seeded mock generators
├── lib/
│   ├── fmt.ts           every displayed number goes through here
│   ├── prng.ts          seeded PRNG (Math.random is banned by ESLint)
│   ├── math5d.ts        5-D rotation + projection for the penteract
│   └── kde.ts           kernel density estimation for the ridgeline
├── store/               Zustand store + SimulationEngine
└── theme/
    ├── theme.css        CSS custom properties (palette, type, radius)
    └── index.css        Tailwind entry, font imports, base layer
```

## Design tokens

Palette and typography are declared once in
[`src/theme/theme.css`](src/theme/theme.css) and mapped onto Tailwind's theme
namespace in `src/theme/index.css`, so `bg-pos`, `text-muted`, `border-hairline`
and friends always resolve to the same values.

| Token           | Value     | Use                       |
| --------------- | --------- | ------------------------- |
| `--gp-canvas`   | `#f6f6f4` | page background           |
| `--gp-card`     | `#ffffff` | card fill                 |
| `--gp-hairline` | `#e6e6e2` | 1px borders, grid lines   |
| `--gp-ink`      | `#111111` | body text                 |
| `--gp-muted`    | `#8a8a86` | uppercase labels          |
| `--gp-pos`      | `#1f9d55` | positive / live / cleared |
| `--gp-neg`      | `#d33333` | negative / veto / alert   |
| `--gp-info`     | `#2f6fed` | info / flow               |
| `--gp-node`     | `#5b3fa0` | graph nodes               |
| `--gp-teal`     | `#2aa198` | catalyst ring             |
| `--gp-amber`    | `#e0a100` | caution / pending         |

## Accessibility & motion

Every card exposes a semantic heading and charts carry an `aria-label`
summary. Animations read a single `--gp-motion` switch that flips to `0` under
`prefers-reduced-motion`, and JS timers are gated on the same preference, so
reduced-motion users get a static desk.

## Related documents

- [`DECISIONS.md`](DECISIONS.md) — assumptions taken where the brief was
  ambiguous, and the reasons behind them.
