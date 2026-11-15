# AquaState — Design System

**Direction:** Day/Night Observatory. Two surfaces, one instrument.

- **Night** — the world overview, the hazard board and the dam deep-dive. Obsidian ground, teal data hue, tabular figures.
- **Day** — the country sheet, the dam atlas, method and sources. Tinted climate frame, white working sheet, petrol data hue.
- **Shared** — IBM Plex Sans/Mono, one 24px gutter, status never colour-only, no gradients at rest, 120–180ms feedback, `prefers-reduced-motion` respected.

## Why two surfaces

The two source projects had strong, opposite identities: the water app's printable survey sheet and the space app's data terminal. The merge gives each mode a job:

- the **world** is a night map — you scan for pressure;
- the **country** is a daylight sheet — you read the arithmetic;
- the **dam** is an instrument panel — you inspect the signed proof.

The navigation, typography, status language and data hue stay identical, so it reads as one instrument rather than two skins.

## Tokens

### Night

| Role | Value |
|---|---|
| Ground | `#081012` |
| Surface | `#0d1719` |
| Raised | `#122023` |
| Border / rule | `#1e3034` / `#17272a` |
| Text / muted / faint | `#edf5f4` / `#9bb0ae` / `#718684` |
| Data hue | `#34c9b8` |
| Positive / negative | `#55c98a` / `#ef6f72` |
| Watch / stressed | `#e5a23b` / `#e07a3f` |

### Day

| Role | Value |
|---|---|
| Ground | `#f2f5f2` |
| Surface | `#ffffff` |
| Ink / muted | `#14201d` / `#5b6763` |
| Rule | `#e3e8e4` |
| Data hue | `#1b6c80` |
| Pill live / inventory | `#dcfae5` / `#f0f3f0` |

## Type

- IBM Plex Sans 400/500/600, local woff2; IBM Plex Mono for figures, IDs and formulas.
- World title `clamp(38px, 4.7vw, 68px)` / 500; country title `clamp(34px, 4vw, 54px)` / 500; section 15–24px; body 12–15px; labels 9–11px.
- Tabular numerals everywhere. Sentence case. No uppercase tracked labels except tiny metadata.

## Layout

- **World:** hero + global index card; map (540px) + “where the pressure is” signal panel; country ledger and active events rail; four hazard cards; cascade; source ledger.
- **Country:** header + country index card; four hazard cards; map + dam table + climate trajectory in the main column; why-this-score, water system, confidence and events in the rail.
- **Dam atlas:** headline + counts; viewport map; filters; table; pagination.
- **Dam deep-dive:** DRI ring + buffer bridge; waterfall + sub-index stack + analogs; facts, country context and method in the rail.
- **Method / sources:** sticky contents + readable article, max 860px.

## Components

- **Country index card:** 58px figure, status pill, rank, confidence, coverage, population.
- **Hazard card:** English + Arabic label, 0–100 pressure, gradient meter, source and confidence.
- **Signal panel:** top country per pressure with a mini bar; fills the map column without inventing another chart.
- **Water runway:** 30-day SVG line, emergency threshold, rain event marker; the signature element.
- **DRI ring:** SVG `pathLength=100`; the score is the dash, not a decorative gauge.
- **Waterfall:** signed bars against the 50-point neutral midline; Σ + 50 = HRI.
- **Sub-index stack:** `<details>` rows with score, status, confidence, explanation, proof steps and components.
- **Status:** word + colour; no red/green-only encoding.
- **Buttons:** 34–38px, 6px radius; dark primary, outline secondary; press scale 0.98.

## Motion

Feedback only. 120–180ms ease-out on hover/focus/press and layer changes. The map recolours instantly; no entrance animation. `prefers-reduced-motion` removes travel and transforms.

## Accessibility

- Every map has a table or ranking alternative; the map is an enhancement.
- Keyboard reachable controls with visible focus rings.
- Contrast 4.5:1 on text tiers.
- Arabic labels carry `lang="ar" dir="rtl"` at the label level.
- Mobile: single column at 760px, map 420px, filter fields full width, tables scroll horizontally with a labelled wrapper.

## Data graphics

No chart library. Inline SVG for the runway and climate trajectory; Leaflet with a bundled Natural Earth basemap and no external tiles. Maps work offline after the first load.
