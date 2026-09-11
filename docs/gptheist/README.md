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

## Architecture

```
main.tsx ─ mounts App
App ─────── 12-col grid; starts the 1 Hz SimulationEngine
│
├─ store/deskStore.ts   Zustand store: clock, balance, events, handoffs
│      ▲ tick() at 1 Hz (startEngine); deterministic seeded PRNG
│
├─ data/                seeded generators (all pure, all unit-tested)
│   balance · events · ridge(+lib/kde) · chord · graph(d3-force) · agents
│
├─ lib/                 math + plumbing
│   prng · fmt · kde · math5d · color · useMeasure · usePrefersReducedMotion
│   feed (DeskFeed adapter — see below)
│
├─ components/viz/      pure SVG visualisations (data in via props)
│   BalanceChart · RidgePlot · ChordDiagram · Penteract · ForceGraph ·
│   Histogram · Avatar        (D3 does the math; React owns the DOM)
│
└─ components/panels/   one folder-state per dashboard panel, wiring the
    store into the viz + Card chrome (header, captions, footer)
```

Data flows one way: generators seed the store; panels select memoised slices;
viz components are pure functions of their props. Nothing in the shipped
bundle performs a network request.

## Swapping the mock data for a real feed

The seam is `DeskFeed` in `src/lib/feed.ts`:

```ts
type DeskFeed = {
  subscribe: (topic: DeskTopic, cb: (payload: unknown) => void) => () => void;
};
```

The app currently adapts the simulation store to this interface
(`createSimFeed`). To go live, implement `DeskFeed` over a WebSocket — open the
socket in the constructor, `subscribe(topic, cb)` sends
`{ subscribe: topic }` and routes matching messages to `cb`, returning an
unsubscribe that removes the listener — and hand it to your bootstrap instead
of `createSimFeed`. Topics are `balance`, `events`, `clock`, `handoffs`. The
panels never see the difference.

## Accessibility & motion

- Semantic headings per card (`h1` desk title, `h2` panels, `h3` roster).
- Every chart/svg carries a descriptive `aria-label`; KPI segments and the
  striped bar expose `role="img"` summaries.
- A skip-to-content link precedes the header.
- Reduced motion: `usePrefersReducedMotion()` freezes the penteract and force
  jitter at a static frame, and a CSS backstop in `index.css` switches off all
  animation/transition under `prefers-reduced-motion`.

## Responsive behaviour

One 12-column shell, one set of breakpoints (Tailwind defaults — `sm` 640,
`md` 768, `lg` 1024, `xl` 1280):

| Width       | Shell                                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------------------ |
| ≥ 1280      | Reference layout: KPI 4-up, 7+5 and 6+6 rows, crew 10-up                                                           |
| 1024 – 1279 | Same rows; KPI strip drops to 2-up                                                                                 |
| 768 – 1023  | Every panel full width; chart + stats columns still side by side                                                   |
| < 768       | Stats columns stack under their chart; crew strip 2-up                                                             |
| < 640       | Card captions drop under their title; top bar wraps and the `@handle` is dropped; KPI values step down 26px → 21px |

Two guardrails keep that honest:

- `src/test/responsive.test.tsx` pins the class contract — every direct child of
  `main` is `col-span-12` below `lg`, the `lg`/`xl` rows pack to exactly 12, and
  the KPI/crew/card-header/top-bar responsive classes are present.
- `src/test/chartBounds.test.tsx` stubs `getBoundingClientRect` so the real
  charts lay out at 254 px (a full-width panel on a 320 px phone), 420 px and
  1180 px, then checks every SVG coordinate and text run against the measured
  box. It carries its own positive control, so it cannot pass vacuously.

No visualisation has a hard-coded pixel width: each one measures its container
(`lib/useMeasure.ts`) and returns `null` until it has a size, so charts scale
instead of overflowing.

## Verification & budgets

- `npm run typecheck | lint | format:check | test | build` are all wired and
  green; `npm run coverage` produces a V8 coverage report.
- Bundle at the final milestone: ~76 kB JS + ~8 kB CSS gzipped — far under the
  400 kB ceiling. Only the five named D3 modules are imported.
- The build is 404-free by construction: `base: './'`, relative favicon, and
  the only outbound link is the parent dashboard (`../index.html`).
- Lighthouse: not runnable in this sandbox (no headless browser). A11y/perf
  basics above are in place; run `npx lighthouse` locally against
  `npm run preview` to confirm ≥ 90.

## Related documents

- [`DECISIONS.md`](DECISIONS.md) — assumptions taken where the brief was
  ambiguous, and the reasons behind them.
