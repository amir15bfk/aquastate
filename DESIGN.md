# AquaState — Design System

**Direction:** Framed sheet (tasteskill seed 647431404), climate-tool face.
**Mode:** Operate. Precision and restraint; the data carries the colour.

## The idea

The app is a **hydrological survey sheet**: a tinted field frame holds a white instrument sheet. The map is the survey itself; the right rail is the margin where an analyst writes the arithmetic. The signature element is the **water runway** — stored-water days drawn against the day rain arrives.

## Themes

Every page has a **light** theme (the survey-sheet palette below) and a **dark** theme (the world palette: ground `#081012`, surface `#0d1719`, teal `#34c9b8`). `<html data-theme>` is set before paint from the saved choice or the system setting, and the site-bar toggle switches it. Use the `--t-*` tokens from `static/ds/themes.css` (never raw hex) for anything structural; maps and charts read them with `DS.cssVar()` and listen for the `ds:theme` event.

## Palette

```css
--ground: #f2f5f2;       /* tinted climate frame, one low-chroma green-grey step */
--surface: #ffffff;      /* the working sheet */
--raised: #f7f9f7;
--active: #e9eeea;
--border: #e3e8e4;
--rule: #eef1ef;
--control: #c9d1cb;
--text: #14201d;
--muted: #5b6763;
--faint: #6f7a76;
--accent: #1b6c80;       /* petrol: the one data hue */
--accent-ink: #0d4553;
--accent-wash: #e7f1f2;
--positive: #1e7b4f;
--negative: #c4242a;
--warning: #8a5a0a;
--chart-1: #1b6c80;
--chart-2: #2f70bb;
--chart-3: #a86f0c;
--pill-positive-bg: #dcfae5;
--pill-positive-ink: #04250e;
--pill-negative-bg: #ffedea;
--pill-negative-ink: #831c1e;
--pill-warning-bg: #fffbeb;
--pill-warning-ink: #713f12;
--pill-neutral-bg: #ebedee;
--pill-neutral-ink: #353736;
```

Colour budget: under 3% of pixels. The accent marks data and the selected state; status colours are reserved for status. No gradients, glows, or shadows at rest.

## Type

- **Manrope** variable (200–800), SIL OFL, self-hosted in `static/fonts/` — every app (world, water, pilot). Friendly, highly legible, with tabular figures (`tnum`).
- **IBM Plex Mono** 400/500 for formulas and IDs only.
- Scale (see `static/ds/ds.css`): 12 / 13 / 15 / 18 / 22 / 28, fluid 30–44 page titles, fluid 30–40 KPIs. Minimum text size 12px.
- Sentence case. Tabular numbers everywhere numbers line up.
- No uppercase tracked labels (removed in Nov 2026, see `scripts/ds_normalize_css.py`).

> The shared design-system layer (`static/ds/ds.css`, `static/ds/pages.css`) and the shared site bar (`templates/partials/site_bar.html`) are documented in `UI_IMPROVEMENTS_REPORT.md`. The palettes below are unchanged.

## Shell

- 228px tinted sidebar + 48px tinted top bar forming one L-frame.
- White sheet inset 8px from the right and bottom, 16px radius, 1px border, no shadow.
- Content padding 24px. One 24px gutter.
- Phone: frame disappears; 48px top bar, sheet becomes the screen, nav becomes a sheet.

## Layout

- Overview: 1fr map column + 400px explainability rail, 24px gap. Both start at the same top edge, below the title row.
- Left column: map (58vh, min 440px), then a compact dam ledger.
- Right rail: verdict card, water runway, sub-index ledger, trend card, lineage card.
- 1440×900 must show the verdict, runway, map, and sub-index headers without scrolling.
- 768: rail moves under the map; 390: single column, controls wrap, table becomes rows.

## Components

- **Verdict card:** a 40px status word, 28px index, `OK` / `Watch` / `Stressed` / `Critical`; under it one sentence with days of cover and rain arrival.
- **Water runway:** 30-day SVG line of aggregate storage, emergency threshold, rain event marker. This is the signature element.
- **Sub-index ledger:** five rows with label, value, weight, contribution bar; each row is a `<details>` with formula, inputs, source, confidence, and meaning. No cards inside cards.
- **Dam ledger:** rows with name, capacity/storage, cover days, rain day, status. The row fill never becomes a bar.
- **Map:** circle markers sized by capacity, coloured by status; selected marker has an ink ring; popup with the same numbers as the ledger.
- **Scenario bar:** segmented buttons (Forecast / Dry spell / Rain in 2 days) + demand stress range + horizon select. One row; wraps on phone.
- **Source chips:** neutral chips with a live/cached dot; never decorative.
- **Buttons:** 32px, 6px radius, near-black primary; outline secondary; press scale 0.97; focus 2px accent ring.
- **Pills:** only beside values, 20-24px, pale tint + dark same-hue text.

## Motion

App-screen rules: feedback only. 120-180ms ease-out on hover/focus/press, map marker selection, details disclosure, and the scenario update. No entrance animations. `prefers-reduced-motion` removes transforms.

## Accessibility

- Every control keyboard reachable with a visible focus ring.
- Status never colour-only: word + shape.
- Map has a text alternative: the dam ledger and a "Reservoir data" table.
- Contrast 4.5:1 on all text tiers.
- Numeric columns use tabular figures and right alignment.
