# VISUAL_SPEC.md — analysis of the reference screenshot

The reference (Money-Heist themed "GPTHEIST DESK", captured ~1024px wide) is the
source of truth for layout, palette, typography and per-panel content. It does
not persist in the workspace, so this file records everything the remaining
milestones need. Palette tokens live in `src/theme/theme.css`; this spec only
references them.

Global: page bg `canvas` #f6f6f4; cards white, 1px `hairline` #e6e6e2, ~10px
radius, soft shadow; 12-col grid, 16px gaps; ~16px outer margin; content max
~1600px. Labels: uppercase mono 10–11px, letter-spaced, `muted`. Values: mono,
tabular. Headings: Inter semibold.

---

## Header
- 40px green rounded square, white feather glyph.
- `GPTHEIST DESK` bold sans; hairline `|`; handle `immortalhowwl` red mono.
- Right: dark-green `LIVE` pill, white mono text, pulsing yellow-green dot at
  left; then `18:48 / 13H` black mono.

## KPI strip (4 equal cards)
1. `BALANCE / ETH` → `0.0189 ETH` (ink, ~26px bold). Sub `FROM 0.0156 ETH`.
2. `TOTAL PNL / USD` → `+$10.97` (green). Sub `+21.18%` (muted).
3. `MISSION CLOCK` → `02:43` (ink). Sub `16:05 → 05:05 / 13 HOURS`.
4. `APPROVAL GATE` → `PALERMO` (ink) + `ENTRY CLEARED` (green, tiny, right).
   10-segment bar, first 3 green rest hairline. Sub `CHECK 52 / EXIT DEPTH`.
   Green status dot top-right corner.

## Row 2 — 7/5
### // BALANCE HISTORY (7) — right caption `ETH / 13H`
Line chart. Y ticks `0.025 / 0.013 / 0.0`; X ticks `16:05 / 22:35 / 05:05`.
Faint grid. Green wash under the realised portion (left ~1/5). Ink line. Red dot
at current; red-bordered tag `0.0189` above it.

### // ACTIVITY LOG (5) — right caption `138 EVENTS`
Highlighted latest row on a light-lavender wash: `18:43 RIO` (code red), second
line `PULLBACK / INVALIDATION MARKED` (red). Then a scroll list of
`time · CODE · message · dot`. Code colours: TOKY amber, RIO red, NAIR teal,
LISB blue, DENV amber, STOC blue, HELS purple, PALM green, PROF blue, BERL red.

## Row 3 — 12 · ● Tail Probability Ridge (black dot)
Centre captions `STRIKE LANDSCAPE` + `PRICE-TARGET DENSITY / ACTIVE POOL`;
right `ONE RIDGE / ONE SESSION / TAILS PAY`.
- Left stats: `TAIL SCANNER / LIVE`; SESSIONS 1334; TAIL MASS 1.34% (green);
  IMPLIED MULT ×40.0; AVG ENTRY 1.3¢; BEST HIT +81.2 (green).
  Footer `PRICE THE TAIL. CHECK THE EXIT.`
- Right: ~24 stacked grey KDE curves offset diagonally (ridgeline). Right tail
  shaded pink with a dashed red strike line; black chip top-right
  `STRIKE / EXIT`. Hover tooltip (white box): `P(>STRIKE) 1.58%` (ink),
  `IMPLIED ×40.9` (red), `SESSION 1363` (faint). X-axis `−2σ −1σ 0 +1σ +2σ`.

## Row 4 — 6/6
### ● Handoff Chord (amber dot) — centre `WHO PASSES TO WHOM`, right `10 ROLES`
Chord of 10 arcs labelled TOKY(top), PALM, LISB, BERL, DENV, NAIR, STOC, HELS,
PROF, RIO. A few arcs coloured (LISB/PALM green, PROF/RIO blue, HELS purple,
BERL/NAIR red); ribbons mostly grey. Right stats: HANDOFFS 111; REJECTED 3
(red); EDGES / TASK 1; APPROVAL PALERMO (red). Footer
`FILES, NOT MEMORY / EVERY PASS LEAVES A TRAIL`.

### ● 5D Strategy Lattice (blue dot) — centre `PENTERACT`, right `32 NODES · 80 EDGES`
Left stats: DIMENSIONS 5 / 5; VERTICES 32; EDGES 80; ROTATION 263° (red);
PROJECTION 5D → 2D. Right: penteract wireframe; edges multicolour
(green/red/purple/amber/blue); coloured vertex dots; small D1–D5 axis legend.
Footer `EVERY AXIS IS AN EDGE / A TEAM MUST PASS ALL FIVE`.

## Row 5 — 12 · ● Relationship Graph Simulation (red dot)
Centre `VOLUME / FLOW / LIQUIDITY`; right `90 NODES · 134 EDGES`.
- Left: NODE CLASS legend (Bear signal red, Bull signal green, Median path
  black-dashed, Catalyst teal). BEAR PATHS 518 (red); BULL PATHS 1027 (green);
  PATHS SIM 1545; CONVERGENCE 97% (green); striped dark progress bar;
  `PREDICTED ▲ UP` (green).
- Centre: force graph; hubs BEAR CLUSTER (pink), CATALYST RING (teal),
  ASTRA PRIME (purple); many small nodes; dashed median path across; blue tag
  `APPROVED / FLOW`.
- Right: P(UP) 0.60 (green); P(DOWN) 0.40 (red); EDGE VS BOOK +23¢ (green);
  CONFIDENCE 95.0%; `EDGE DISTRIBUTION / 24H` histogram bars red→pink→green→blue.

## Roster strip (10 cards, reference order)
`03 TOKYO SCOUTS`(amber) · `10 PALERMO VETOES`(green, green border) ·
`07 DENVER SIGNALS`(amber) · `08 STOCKHOLM LIQUIDITY`(blue) ·
`01 PROFESSOR ROUTER`(blue, blue border) · `04 RIO CHARTS`(purple, blue border) ·
`03 HELSINKI LEDGER`(purple) · `05 NAIROBI BRIEFS`(red) ·
`02 BERLIN CONDITIONS`(red) · `06 LISBON RESEARCH`(teal, teal border).
Card: index top-left (faint), status dot top-right, flat pixel avatar
(red jumpsuit + headset; distinct hair/glasses/beard), name mono bold, role
coloured mono. Active cards get a coloured border and a tinted avatar
background matching the accent.
