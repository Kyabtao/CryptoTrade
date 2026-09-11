# DECISIONS.md

Assumptions and judgement calls taken while building GPTHEIST DESK. Where the
brief was ambiguous, this records what was chosen and why, so the choice can be
revisited deliberately instead of being rediscovered.

---

## 1. `reference.png` was not present

**Brief:** "Match its layout, typography, colour palette and data-viz style as
closely as possible", with the screenshot to be attached as `reference.png` in
the repo root.

**Reality:** no `reference.png` exists in the repository
(`git ls-files | grep -i png` returns nothing, and the file is absent from the
working tree).

**Decision:** build from the written specification, which is detailed enough to
fix layout, palette, copy and per-panel content precisely. Panel geometry,
spacing and type scale follow the written numbers (12-column grid, 16px gaps,
10–11px uppercase mono labels, 10px card radius). If the screenshot is added
later, the visual pass becomes a diff against it rather than a rebuild — every
token lives in one file (`src/theme/theme.css`) and panel structure is one
folder per panel.

**Impact:** low for structure and colour, moderate for pixel-level detail
(exact paddings, icon shapes, chart stroke weights).

## 2. Everything lives in one folder

**Instruction:** "make one folder and then start coding, don't change anything
outside of folder, just add in nav for this folder."

**Decision:** the whole app lives in `docs/gptheist/`. Exactly one file outside
it is touched — `docs/assets/layout.js`, to add the `GPTHEIST` nav entry. In
particular:

- The root `README.md` is **not** modified; this app's docs live in
  `docs/gptheist/README.md`.
- `docs/assets/style.css`, `charts.js` and `data.js` are **not** touched. The
  desk ships its own stylesheet and does not depend on the parent chrome.
- No new GitHub Actions workflow, no root config changes, no new root
  gitignore entries — `docs/gptheist/.gitignore` covers the folder.

## 3. `dist/` is committed

**Context:** the parent site is published by GitHub Pages from `main` / `docs`
with no build step (confirmed by reading the root README and both workflows in
`.github/workflows/` — `tests.yml` runs pytest only, `paper-trade.yml` commits
JSON only).

**Decision:** commit the Vite build output to `docs/gptheist/dist/` and point
the nav at `gptheist/dist/index.html`. The alternative — a Pages build action —
would require changing files outside the folder, which the instruction forbids.
`base: './'` in `vite.config.ts` keeps asset URLs relative so the bundle works
both under `/<repo>/gptheist/dist/` and from any local static server.

## 4. Tailwind CSS 4, not 3

**Decision:** Tailwind v4 with the `@tailwindcss/vite` plugin. There is no
`tailwind.config.js`: tokens are declared as CSS custom properties in
`src/theme/theme.css` and exposed to Tailwind through `@theme inline` in
`src/theme/index.css`.

**Why:** this is the current Tailwind line, it removes a config file, it
tree-shakes unused utilities from the actual CSS, and it keeps the palette in
plain CSS — which satisfies the brief's "Tailwind for layout/utility styling
plus a small theme.css for CSS variables" more directly than duplicating the
palette into a JS config.

## 5. `#d33` normalised to `#dd3333`

**Brief:** red accent listed as `#d33`.

**Decision:** expanded to the six-digit form `#dd3333` in `theme.css`. Identical
colour; the long form avoids ambiguity when the value is consumed by SVG `fill`
attributes and by tools that stringify colours.

## 6. Variable fonts, self-hosted

**Brief:** JetBrains Mono (or IBM Plex Mono) for data and labels, Inter for
headings, self-hosted, no CDN.

**Decision:** `@fontsource-variable/inter` and
`@fontsource-variable/jetbrains-mono`. One woff2 per subset instead of one per
weight, which keeps the whole desk well inside the 400 kB gzipped budget while
still giving every weight used. Fallback stacks in `theme.css` degrade to
system UI / `ui-monospace` if the files are ever stripped.

## 7. `Math.random` is banned

**Decision:** ESLint's `no-restricted-properties` rejects `Math.random`
project-wide. All mock data comes from `src/lib/prng.ts` (mulberry32 + a
Box–Muller gaussian).

**Why:** the desk must look identical on every load and every test run.
Deterministic seeds also make "why does this panel look like that" answerable
from the seed string alone.

## 8. D3 is math-only

**Decision:** no D3 selection, transition or DOM code. React owns the SVG tree;
D3 supplies scales (`d3-scale`), path generators (`d3-shape`), the chord layout
(`d3-chord`), force simulation ticks (`d3-force`) and array statistics
(`d3-array`).

**Why:** the brief requires it, and it keeps React's reconciliation — plus
memoisation — as the single source of truth for what is on screen.

## 9. Strictness beyond `"strict": true`

`tsconfig.app.json` also enables `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`, `noImplicitOverride`, `noImplicitReturns`,
`noUnusedLocals`/`noUnusedParameters` and `forceConsistentCasingInFileNames`,
and the ESLint config uses `typescript-eslint`'s `strictTypeChecked` preset.

**Why:** the brief says strict TS with no `any`; `noUncheckedIndexedAccess` in
particular catches the class of bug that matters most here — indexing a
generated array one element past the end and quietly rendering `undefined`
inside an SVG path.

## 10. Simulation is contained, never networked

No `fetch`, `XMLHttpRequest` or WebSocket exists in the source. The engine
(`src/store/`) advances a clock and emits events on timers. A `DeskFeed`
adapter interface is defined for a future real feed, but nothing in the shipped
bundle implements it. The footer carries a permanent **SIMULATED DATA** badge.

---

## Open questions

1. **The reference screenshot.** Adding `reference.png` would let the visual
   pass be verified rather than inferred. Until then, panel-level geometry is
   derived from the written spec (see §1).
2. **Nav label.** The parent dashboard's items are single words
   ("Dashboard", "Analytics", …). `GPTHEIST` was chosen to match; `Desk` or
   `Agent Desk` would also fit.
3. **Bundle budget.** Measured after the visualisation milestones land; the
   scaffold is far under the 400 kB gzip ceiling and the plan is to keep D3
   imports to the five named modules.
