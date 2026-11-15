# UI Improvements Report — AquaState (November 2026)

> **Scope note.** The brief referred to "ANZAR / AquaGuard AI". No project with either name exists on this machine; the only project in the workspace is **AquaState** (`C:\Users\Lenovo\Desktop\nasa\aquastate`), an Algeria-centred water and climate observatory. The redesign was applied to AquaState and its name was kept — renaming the product was not part of the brief. As requested, **the existing colour palettes were kept unchanged**.

Screenshots of the result are in [`docs/screenshots/redesign/`](docs/screenshots/redesign/).

---

## 1. Executive Summary

AquaState had strong, honest data but three disconnected front-ends: the world observatory, the water runway (`/water/`) and the dam simulator (`/pilot/`). Each had its own header, typography and spacing. The dashboard was a rigid grid of bordered boxes with 9–11 px uppercase labels, and nothing could be explored at a scale below the country. The simulator's map was broken.

The redesign:

- **One design system.** A shared token/component layer, the **Manrope** typeface, one site bar with search on every page, and softer surfaces with larger radii and fewer borders, all on the original palette.
- **A new dashboard.** The first page now opens with a welcome question, a gauge and four interactive KPI cards, then one explorer that connects the map, ranking, distribution chart and a country detail panel. An Algeria preview and filterable alerts follow.
- **A new Map Viewer (`/map/`).** It started with Algeria's **48 real wilaya boundaries** and now covers **the whole world: any of 209 countries' first-level regions** (§5b). Regions are coloured by five layers computed from **live NASA POWER, Open-Meteo and GloFAS data inside each region**, using the app's existing WCRI-2.0 mathematics. It adds a monthly replay, filters, tooltips, a dynamic legend and a rich detail panel. No value is invented.
- **A friendly 404 page** with a playable **"Catch the Rain"** mini-game: keyboard, mouse and touch controls, score, lives, best score, pause and restart.
- **Bug fixes found during the audit:** the broken `/pilot/` map, an Alpine.js runtime error, the Windows cache-path limit, and a favicon 404 on every page.
- **Responsive behaviour:** a collapsible navigation drawer, a mobile filter sheet on the map, a touch pad for the game, and no horizontal overflow on any route at 390, 768 or 1440 px.

All existing tests still pass (58 Django + 137 pytest). There are 88 automated browser checks (78 interaction + 10 state), all passing.

---

## 2. Initial UI Audit

The audit inspected every route at 1440×900 and 390×844 with headless Edge (full-page screenshots, console capture, overflow measurement), and read every template and stylesheet.

| Area | Problem found |
|---|---|
| Architecture | Three apps with three base templates and three header designs (`world/base.html`, `hydro/base.html` with its own sidebar, `dashboard/base.html` with MapLibre/Alpine/Tailwind). `/pilot/` had no way back to the rest of the site. |
| Typography | **119 declarations** set text at **9–11 px**, plus more at 7–8 px (e.g. `.water-facts dt` 8 px, `.dri-unit` 7 px). **24 rules** used tracked uppercase labels, contradicting the project's own `DESIGN.md` ("No uppercase tracked labels"). |
| Visual style | Every panel had a 1 px border and a 12 px radius; the hierarchy came from boxes, not spacing. The dashboard read as a generic grid of cards. |
| Dashboard | The hero headline was poetic but didn't tell a newcomer what the page does. The rankings ignored the selected map layer (always index). Tooltips were bound once at load, so they went stale after a refresh. The country card was cramped in a map corner. "Where the pressure is" used 10–11 px text. There was no date or period control, and the hazard cards were static. |
| Map | Countries only; no sub-national geography (searching for "wilaya", "ADM1" or "admin1" across the code base found nothing). The monitored-dam legend was hard-coded to "38 monitored" while the atlas had 33. |
| `/pilot/` | **Broken.** `Alpine Expression Error: storm is not defined` (the simulator's `x-data` never declared `storm`). MapLibre's **worker failed to load** because Windows' MIME registry served `.mjs` as `text/plain`, so the map stayed blank. |
| Navigation | The mobile top bar wrapped into two rows of links; there was no search anywhere. |
| 404 | Django's default 404 page. |
| Assets | `/favicon.ico` returned 404 on every page load. |

No horizontal overflow was found before or after the redesign.

---

## 3. Design System Changes

New files: **`static/ds/ds.css`** (tokens and components, loaded last on every page), **`static/ds/pages.css`** (page layer and legacy harmonisation), **`static/ds/ds.js`** (behaviour).

### Typography
- **Manrope** variable (weights 200–800), SIL OFL. It is self-hosted in `static/fonts/` with latin and latin-ext subsets (39 KB total) plus a preload hint, so there is no external font CDN.
  - Chosen over Inter, DM Sans and Plus Jakarta Sans: it is warmer and friendlier for non-experts, and it has **tabular figures** (`tnum`, verified with fontTools). That matters for a data product whose KPIs and rankings must align.
  - IBM Plex Mono stays for formulas.
- Scale tokens: 12 / 13 / 15 / 18 / 22 / 28 px, plus fluid page titles `clamp(30px, 3.6vw, 44px)` and fluid KPIs `clamp(30px, 3vw, 40px)`.
- **Minimum text size is now 12 px.** `scripts/ds_normalize_css.py` rewrote the legacy stylesheets at the source:
  - **134 font sizes raised:** sizes of 10 px or less became 12 px, and anything between 10 and 12 px became 13 px. SVG-text rules were skipped because they sit in fixed viewBoxes.
  - **24 uppercase-tracked labels** were converted to sentence case with normal tracking.
  - Hard-coded IBM Plex Sans stacks now point at `var(--ds-font)`.
- Headings use `text-wrap: balance` and paragraphs use `text-wrap: pretty`.

### Colour palette (unchanged)
The two existing palettes are kept exactly. They are now exposed under one set of names (`--c-*`):
- **World, dark:** ground `#081012`, surface `#0d1719`, teal `#34c9b8`, amber `#e5a23b`, orange `#e07a3f`, red `#ef6f72`, blue `#5ba7e8`, green `#55c98a`.
- **Survey sheet, light:** `#f2f5f2` and white, with petrol `#1b6c80`.
- The status bands (resilient/stable/watch/stressed/critical) and the pressure ramp (`#2b6f6a → #8fae5a → #e5a23b → #e07a3f → #ef6f72`) are the same as before.

### Spacing, radius, elevation, motion
- A 4-point spacing scale (`--sp-1` … `--sp-16`) with a fluid page gutter `clamp(16px, 3vw, 32px)`.
- Radii 8 / 12 / 16 / 20 px plus pill. Soft two-layer shadows instead of 1 px borders. No glow, no glassmorphism, and no gradients except the subtle raised-card wash.
- Motion: 140 / 220 / 360 ms with `cubic-bezier(.22,1,.36,1)`. A single 6 px page-enter fade. Everything is disabled under `prefers-reduced-motion`.

### Components
| Component | Description |
|---|---|
| **Site bar** (`templates/partials/site_bar.html`) | Sticky, translucent, 64 px. Brand, primary nav (Overview · Map viewer · Countries · Dams · Hazards), an accessible **More** menu (Water runway, Dam simulator, Methodology, Data sources; arrow keys and Esc work), a live snapshot status, and a search trigger. Below 980 px it collapses to a **slide-in drawer**. Used on **every** page of all three apps. |
| **Search palette** | A `<dialog>` opened with **Ctrl/⌘ K**, **/** or the search button. It searches pages, **wilayas**, **countries** (from the world snapshot) and **dams** (via `/api/dams/?q=`, debounced and abortable), accent-insensitively. Keyboard ↑ ↓ Enter Esc, with ARIA combobox/listbox roles. |
| Buttons | `.ds-btn`: primary teal, ghost and quiet variants, small size, 0.97 press scale, and a busy spinner state. |
| Segmented controls and chips | `.ds-seg` and `.ds-chip`, with `aria-pressed` state. |
| Cards | `.ds-card`, plus `--raised` and `--interactive` variants (2 px lift on hover). |
| Badges | Status badges per band, plus live and proxy/demo badges. |
| Inputs and selects | `.ds-input` and `.ds-select` (custom chevron, focus ring). |
| Tooltips | `[data-tip]` / `[data-tip-title]` on any element. Viewport-clamped and shown on keyboard focus as well as hover. |
| States | `.ds-skeleton` (shimmer), `.ds-state` (empty) and `.ds-state--error`. |
| Toast | `DS.toast()` for feedback such as snapshot loaded, refresh started or layer auto-switched. |
| Leaflet polish | Shared rounded zoom controls, light tooltips and popups (`ds-map-tip`), and app font in maps. |
| Footer | One shared footer with methodology and source links. |

### Legacy harmonisation
On country, dams, dam, hazards, methodology and sources, `pages.css` replaces hard borders and 12 px radii with soft elevation and 16 px radii, makes buttons pills, and strengthens headings, on both the dark and light palettes, without touching their markup.

---

## 4. Dashboard Improvements (`/`)

Files: `world/templates/world/overview.html` (rewritten), `world/static/world/js/overview.js` (new; replaces `world-map.js`), `world/views.py` (`overview` context).

The page now reads top to bottom as a story: **welcome → key figures → explore → zoom into Algeria → what's happening now → how to read it → where numbers come from.**

1. **Welcoming header.** "How is the world's water doing today?" with a plain-language lede, a primary action (**Open the Algeria map viewer**) and **Refresh live data** (busy state, live status text, explanatory tooltip).
2. **Snapshot card.** An SVG **gauge** of the global average WCRI and a **snapshot date selector** that lists every stored world snapshot. Choosing one reloads `/api/world/?version=…` and redraws the gauge, bands, map, ranking and histogram. The **band strip is clickable**: each band filters the map and ranking to that band.
3. **Four KPI cards with hover context** (tooltips explain each figure and its source). Each is clickable:
   - *Need attention* filters the map to Watch, Stressed and Critical.
   - *Drought pressure* opens the hazard board.
   - *Dams catalogued* opens the atlas.
   - *Active events* scrolls to the alerts.
4. **Explore the planet** (one card instead of four separate panels):
   - **Risk category switch** (Index · Drought · Flood · Wildfire · Desertification) recolours the map, rebuilds the **legend**, re-ranks the **ranking** (now layer-aware, with "highest/lowest pressure" titles) and rebuilds the **distribution chart**.
   - **Overlays:** monitored dams and active events (loaded lazily).
   - **Distribution chart.** Five band bars, or ten pressure bins for hazard layers. **Click a bar to highlight those countries on the map**; a "Showing … · clear ✕" chip resets the filter.
   - **Ranking.** Best/Worst toggle, a **text filter**, colour bars, and keyboard-accessible rows. Clicking a row flies the map to the country.
   - **Country detail panel** (on map or ranking click): score, band badge, rank, confidence and coverage, four pressure meters, six pillar tiles, and links to the country sheet and water runway (plus the wilaya map for Algeria). The selection is highlighted on the map; Esc closes the panel.
   - Hover tooltips are now generated at hover time, which fixes the stale-tooltip bug. Scroll-wheel zoom is enabled only after the first click, so page scrolling never hijacks the map.
5. **"Algeria, wilaya by wilaya" preview.** A small real-boundary map (generalised preview copy) with a layer switch (Drought · Water stress · Fire), the top 5 wilayas as clickable bars, and hover tooltips. Clicking any wilaya opens the Map Viewer with that wilaya and layer selected.
6. **Active events (alerts).** NASA EONET events filtered by **period** (7 / 30 / 90 days / all) and **type** (chips), with relative dates and a match count. **Clicking an event switches on the events overlay, flies the map to it and opens its popup.**
7. **How to read it.** The cascade explainer with four clickable pressure cards (global averages, Arabic names kept).
8. **Source freshness.** A compact grid with live badges.

Auto-refresh is preserved: `/api/world/meta/` is polled every 60 s, and a new version reloads the data in place with a toast.

---

## 5. Map Viewer Improvements (`/map/`)

Files:
- Page: `world/templates/world/map_viewer.html`, `world/static/world/js/map-viewer.js`, `static/ds/map-viewer.css`, `static/ds/icons/*.svg`.
- Data: `world/services/wilayas.py`, `world/management/commands/refresh_wilayas.py`, the `RegionSnapshot` model plus migration `0002`.
- Geometry: `scripts/build_wilaya_geo.py` → `static/data/dz-wilayas.geojson`.

### Map technology
**Leaflet** (already vendored and used by the world pages) was kept; there was no reason to switch. No external tiles are used, consistent with the app's no-third-party-tiles policy. Neighbouring countries (Natural Earth, already in the project) are drawn dimmed for geographic context.

### Geographic data — real boundaries, not drawn
- **Source:** geoBoundaries **gbOpen DZA ADM1**, derived from OpenStreetMap (Wambacher), licence **ODbL 1.0**, boundary year 2017: **48 wilayas, ISO 3166-2 codes DZ-01 … DZ-48**. The raw release is kept in `world/data/geo_src/` for provenance; attribution is shown on the map.
- `scripts/build_wilaya_geo.py` keeps **every published vertex**. It only cleans names (a stray U+200E mark in "Bordj Bou Arreridj"), rounds coordinates to 4 decimals (about 11 m), and adds a guaranteed-interior label point and an area per wilaya.
- A separate **generalised preview copy** (`dz-wilayas-lite.geojson`, 46 KB, ~2 km tolerance) is used **only** for the small dashboard thumbnail.
- No region groupings were invented. The project has no official region dataset, so filtering is by risk level and by name, not by made-up "regions".

### Data behind each wilaya — computed, not hard-coded
`refresh_wilayas` samples the **same live, keyless sources** as the country index at an interior point of each wilaya, and runs the **existing `compute_country` WCRI-2.0 mathematics**:

| Layer | Definition | Source | History |
|---|---|---|---|
| Water stress | 100 − aridity score; aridity = annual rain ÷ PET (Hargreaves) | NASA POWER / MERRA-2 monthly | latest |
| Drought | 100 − (0.40·SPI-3 + 0.25·SPI-12 + 0.20·soil percentile + 0.15·dry spell) | NASA POWER + Open-Meteo 92-day | **12 months** (past months omit the daily dry-spell term) |
| Flood risk | 0.75 × GloFAS discharge pressure + 0.25 × EONET floods in the wilaya | Open-Meteo GloFAS + NASA EONET | latest |
| Forest fire risk | 0.65 × fire weather + 0.20 × drought coupling + 0.15 × active fires | Open-Meteo + NASA EONET | latest |
| Vegetation moisture (**proxy**) | Root-zone soil wetness percentile vs the same month of earlier years | NASA POWER GWETROOT | **12 months** |

- Water stress deliberately uses **only local climate** (aridity), not the national World Bank per-capita figure, so wilaya differences are real.
- EONET events are assigned to wilayas by point-in-polygon.
- Catalogued dams from the atlas are also assigned by point-in-polygon and listed per wilaya.
- The current snapshot covers all **48/48 wilayas with climate, forecast and flood signals, 12 months of history, and 0 errors**.
- `refresh_world` (the unattended loop) now also refreshes the wilaya layers and reuses the same caches. A failure there can never break the world refresh.
- API: `GET /api/algeria/wilayas/[?snapshot=…]` returns the layers, layer metadata (labels, formulas, sources), months, per-wilaya dams and events, the snapshot list and the coverage.

### Visual design
- Algeria fills the stage with clear wilaya borders.
- The choropleth uses the palette's pressure ramp; for the health-type layer (vegetation) it is reversed, so green always means "better".
- **Wilaya names** are shown adaptively by zoom and area so labels never pile up, and can be switched off.
- **Selection** has a white outline, drop-shadow and stroke "pulse" animation, and the map flies to the wilaya. Other wilayas dim when filtered out.
- **Loading state:** an animated droplet. **Error state:** a message with **Retry**. **Empty-snapshot state:** explains which command to run.

### Interactions (all 10 requested)
1. **Hover:** a tooltip shows the wilaya name, number, layer value, level and period.
2. **Click** selects a wilaya.
3. The selected wilaya is **highlighted** (outline, glow, pulse, brought to front).
4. **Detail panel**, which contains:
   - the headline value with a level pill;
   - **all five indicators**, each clickable to map that layer;
   - **12-month trend sparklines** for drought and vegetation (click a point to jump to that month);
   - model inputs (aridity, rain, PET, rainfall trend, SPI-3/12, soil percentile, dry days, discharge peak ratio);
   - **dams in the wilaya**, with links to dam sheets;
   - active events;
   - links to the Algeria water runway and country sheet.
5. **Layer switch:** Water Stress, Drought, Flood Risk, Forest Fire Risk, Vegetation (radio group with arrow-key navigation, and mobile chips).
6. **Observation period:** "Latest (live)" plus the last 12 NASA POWER months. Latest-only layers are marked. Picking a month on a latest-only layer switches to drought, and the toast explains why.
7. **Filters:** level chips (Low / Moderate / High / Severe, or Very dry → Moister than usual for vegetation) and a **wilaya search** that selects on an exact name match.
8. **Reset:** a reset-view button plus "Reset filters & view".
9. **Zoom and pan:** smooth, with bounds limited to the region; double-click and wheel zoom work.
10. **Dynamic legend:** a ramp, a direction hint and a count of wilayas per level, updated for every layer and month change. It also explains dam markers when they are shown.

When nothing is selected, the right panel shows **"Algeria at a glance"**: the layer's formula, average, median and count, a clickable stacked bar of wilayas per level, and the top 12 wilayas.

The URL keeps state (`?layer=…&month=…&w=DZ-16`), so views are shareable; the dashboard and search link into it. **Esc** returns to the national view.

### Geographic limitations
See §12.

---

## 5b. Worldwide extension — every country, region by region (second pass)

The Map Viewer now covers **the whole world** with the same approach as Algeria: real first-level boundaries and live per-region layers from the same mathematics. Screenshots: `docs/screenshots/redesign/map-viewer-world.png`, `-united-states.png`, `-russia.png`, `-first-visit-progress.png`.

**Coverage.**
- geoBoundaries publishes ADM1 for **199 countries** in gbOpen and **12 more** only in gbHumanitarian.
- **209** of those map onto the app's gazetteer. The catalogues are versioned in `world/data/geo_admin1/catalog_*.json`.
- Countries with no published ADM1 (e.g. the Holy See) get an honest "no regional map" message; nothing is drawn.

**How a country is built (on first visit).**
1. `GET /api/regions/<ISO2>/` returns **202 + progress** and starts a background job (`world/services/region_jobs.py`, at most two at once).
2. The job:
   - downloads the country's boundaries;
   - fetches Open-Meteo forecast and GloFAS discharge for every region in batched requests;
   - fetches NASA POWER per region (4 parallel requests);
   - assigns EONET events and the country's **1,500 largest catalogued dams** to regions by point-in-polygon;
   - runs `compute_country` per region and stores a `RegionSnapshot`.
3. The page shows the boundaries immediately, then a progress bar ("Fetching NASA POWER climate records · 20/48"), then colours.

Measured first builds:

| Country | Regions | First build |
|---|---|---|
| Brazil | 27 | 17.7 s |
| Spain | 19 | 19.6 s |
| Morocco | 12 | 21.3 s |
| Tunisia | 24 | 29.9 s |
| United States | 56 | 45.6 s |
| Russia | 83 | 73.4 s |

Later visits are instant. Snapshots older than 24 h are served immediately and refreshed in the background (stale-while-revalidate). `refresh_regions --existing`, run by the `refresh_world` loop, keeps every opened country fresh.

**Geometry processing** (`world/services/regions.py`):
- MultiPolygon support.
- Interior label points from the largest polygon, plus area and bounding box per region.
- Countries crossing the **antimeridian** (Russia, Fiji…) are shifted so they draw as one shape.
- Published geometry is kept as-is. Only files with more than 60,000 vertices are lightly generalised, in proportion to the country's size, and the UI says so when it happens.
- Region codes are the ISO 3166-2 codes when the source provides unique ones.
- The local name for regions is used where it is well established (wilayas, states, provinces, governorates, prefectures, federal subjects…).

**Map Viewer, world mode** (`/map/`):
- Countries are coloured from the live world snapshot: water stress from aridity, drought/flood/fire from the country pressures. Vegetation moisture is per-region only, and the page says so.
- Countries with a regional map are drawn solid; those without are faded.
- The side panel shows world statistics, the highest-pressure countries (click to open) and the countries already computed.

**Country mode** (`/map/?c=XX`):
- The other countries stay on the map as dim context and remain clickable to switch country.
- A **World › Country** breadcrumb, a **country picker**, and **browser Back/Forward** move between levels (`pushState`).
- All the Algeria interactions carry over: hover tooltips, selection, the five indicators, 12-month replay, level and name filters, dams, labels, legend counts, detail panel, Esc.
- New for multi-country use:
  - **Label collision avoidance**: bigger regions place their names first; overlapping names wait for a closer zoom.
  - **Main-territory framing**: regions whose boxes touch are clustered, and the view fits the largest cluster, so the contiguous US, metropolitan France or mainland India fill the screen while Alaska, Hawaii or overseas departments stay one zoom-out away.
  - **Per-country attribution**: source and licence in the map footer and the side panel.
  - A neutral note that boundaries are shown as published and imply no position on territorial claims.

**Everywhere else:**
- The dashboard's country panel has a **Regional map** button for every country.
- Country sheets have a **Regional map** button.
- Search has a **Regional maps** result group.
- The Algeria endpoint (`/api/algeria/wilayas/`) is kept for the dashboard preview, and old `/map/?w=DZ-16` links still open Algeria.

---

## 5c. Light and dark themes for every page (third pass)

Before, the app mixed two looks: the overview, maps, dam and hazard pages were always dark, while the country, atlas, methods, sources and water pages were always light. Now **every page has both a light and a dark theme**, and they switch together.

- **Choosing a theme.** A sun/moon button sits in the site bar (and a "Switch to light/dark theme" button in the mobile menu). The choice is saved per browser (`localStorage["aquastate.theme"]`). With no saved choice, the page **follows the system setting**, including live changes.
- **No flash.** `templates/partials/theme_head.html` sets `<html data-theme>` before first paint on all three apps. Switching cross-fades colours for 400 ms (off under reduced motion), and the browser's theme colour updates.
- **One token set** (`static/ds/themes.css`):
  - The tokens (`--t-*`: ground, surfaces, borders, text tiers, links, overlays, tracks, glass, scrim, tooltip, code, map land, edges, lines, hover, selection, no-data, label halo, status inks, shadows) exist in a dark version (the world palette) and a light version (the survey-sheet palette). **No new colours were introduced.**
  - Every legacy variable family is mapped onto them: `--c-*` (design system), `--world-*`, `--sheet-*`, and the `--ground/--text/--accent/…` names shared by the water and pilot apps. So all apps switch together.
- **Hard-coded colours removed.** `scripts/ds_theme_tokens.py` makes about 80 exact, verified replacements of structural literals across the six world stylesheets, the water app and the design-system files. It also converts 41 white overlays to theme overlays.
  - Literals that cannot be edited, because they live in the pilot's compiled Tailwind build, are overridden with tokens, scoped to that page.
  - Inline template colours (the dam breadcrumb; the atlas, methods and sources eyebrows) now use tokens.
  - Status colours stay the same; status pills get per-theme ink (light pastel ink on dark, dark ink on light).
- **Maps and charts follow the theme live, with no reload.** Each one reads the token values and listens for the `ds:theme` event:
  - **Dashboard world map and Algeria preview:** borders, hover, selection, no-data, marker rings. Selection and filters are kept.
  - **Map viewer:** neighbouring land, edges, region lines, pending fill, labels (with a light or dark halo). The country, selection and filters are kept.
  - **Country map and atlas map:** land, edges, outline, markers.
  - **Country rainfall chart:** uses CSS variables inside its SVG, so it needs no redraw.
  - **Water runway and storage-trend charts:** redrawn. The water map's countries, grid and reservoir markers are restyled.
  - **Pilot MapLibre basemap:** recoloured with `setPaintProperty`.
- **Kept on purpose:** the 404 game's night-sky scene stays dark in both themes. It is an illustration, and its overlay text is fixed to light ink.

Screenshots: `docs/screenshots/redesign/theme-light-*.png` and `theme-dark-*.png` (overview, map viewer for France, country sheet, water runway).

---

## 6. Interactivity Improvements

Every visible control was audited. Each one below now performs a real action backed by existing data or APIs. No interaction was faked.

| Where | Interaction | Behaviour |
|---|---|---|
| All pages | Site bar, More menu, mobile drawer | Real navigation; keyboard and Esc support; focus is managed. |
| All pages | Search (Ctrl K, /, button) | Live results across pages, 48 wilayas, 249 countries and 82k dams; Enter navigates. |
| All pages | Tooltips | Context on KPIs, bands, layers, indicators and chart bars, on hover and on focus. |
| Overview | Snapshot selector | Reloads the chosen stored snapshot into every view. |
| Overview | Band strip, histogram bars, "Need attention" KPI | Filter the map and ranking; a clear chip resets. |
| Overview | Layer switch | Map, legend, ranking and chart update together. |
| Overview | Ranking rows, map click | Open the country detail panel and fly the map to the country. |
| Overview | Overlay chips | Lazy-load monitored dams and EONET events. |
| Overview | Alerts period and type | Filter the event list; clicking an event flies the map to it. |
| Overview | Algeria preview | Hover tooltips; click opens the Map Viewer at that wilaya. |
| Overview | Refresh live data | POSTs `/api/world/refresh/` (existing); busy state; auto-update on the new version. |
| Map viewer | See §5 | 10 interactions plus URL state. |
| `/pilot/` | Simulator sliders and map | **Fixed:** `storm` declared in Alpine `x-data`; the `.mjs` MIME type is registered so the MapLibre worker starts. |
| 404 | Game, return buttons, search | See §7. |

Forms: the existing scenario form on `/water/` and the atlas filter form were not changed in this pass and keep their existing behaviour (I did not re-audit their validation). The new inputs (search, wilaya finder, filters) have no invalid states to validate: an empty or unmatched query shows a helpful empty state instead of an error.

---

## 7. 404 Mini-Game — "Catch the Rain"

Files: `templates/404.html`, `static/ds/catch-the-rain.js`, `static/ds/notfound.css`, `world/middleware.py`.

- **Page:** a big "4💧4" with a bobbing droplet, the message **"Looks like this page dried up."**, the requested path, **Back to the dashboard**, **Open the map viewer** and **Search instead**. The game is optional: it only starts on **Start game** and never blocks navigation.
- **Mechanics:**
  - You steer a cute droplet along the ground while rain falls from drifting clouds.
  - A normal drop is worth **+1**; a rare **gold drop is worth +3**.
  - Each drop that hits the dust **costs a life** (3 lives).
  - Spawn rate and fall speed increase with score.
  - A **reservoir gauge** fills and the river in the landscape widens as you catch drops.
- **Controls:** ← → or A / D keys with acceleration and friction; **mouse** follow; **touch** drag on the canvas; **on-screen ◀ ▶ pads** on touch or narrow screens; **P** pauses.
- **Score system:** score, best score (saved in `localStorage` with try/catch, so private mode just doesn't persist), and lives shown as droplets that fade when lost.
- **Game states:** idle (start card, clouds drifting) → playing ⇄ paused (also auto-pauses when the tab is hidden) → game over ("New best — the reservoir thanks you" or "The ground dried out", with a drop count) → **Play again**.
- **Responsive:**
  - The canvas follows its container and is device-pixel-ratio aware (capped at 2×).
  - Its aspect ratio is 16:9 on desktop and taller on phones. Sizes scale with width.
  - The layout stacks on mobile, and the canvas uses `touch-action: none` so play doesn't scroll the page.
- **Visual style:** the palette's teals, blues and amber; a clouds, dunes, palms and river landscape; splash particles. Lightweight: canvas only, no dependencies, about 300 lines.
- **Serving:**
  - With `DEBUG=False`, Django's default handler renders `templates/404.html`.
  - With `DEBUG=True`, `FriendlyNotFoundMiddleware` replaces the technical 404 for HTML requests. It is placed outside `CommonMiddleware`, so APPEND_SLASH redirects still work.
  - `/api/`, `/static/` and `/admin/` are untouched, and `?debug404=1` shows Django's debug page.
  - The status code stays **404**.

---

## 8. Responsive Design

| Width | Behaviour |
|---|---|
| ≥ 1180 px | Full nav, search with label and shortcut; dashboard explorer has the map and a 360 px side panel; Map Viewer has three columns (controls 320, map, detail 380). |
| 980–1180 px | Status and search label hidden; explorer stacks (map, then panel); KPIs 2×2; Algeria and alerts stacked. |
| < 980 px | **Nav collapses to a hamburger drawer**; brand subtitle hidden; site bar 60 px. |
| < 1100 px (Map Viewer) | Single column: map at 72vh with a **floating layer chip bar** and a **Filters** button that opens the controls as a full-screen sheet; the detail panel flows under the map. On user selection it scrolls into view; a shared link with a preselected wilaya does not auto-scroll. The legend sits above the attribution. |
| < 860 px | Dashboard hero stacks; cascade cards 2-up; Algeria preview stacks. |
| < 560 px | Hero buttons full-width; explorer padding reduced; map 340 px; meters and rank rows tighten; 404 HUD spans the width and the actions stack; the game shows the touch pad. |
| Water runway / pilot | Placed under the shared bar: sticky offsets and heights recalculated (`calc(100dvh - var(--site-bar-h))`); their own mobile layouts preserved. |

Measured: **0 px horizontal overflow** on all 11 routes at 1440 and 390 px, and on the overview, Map Viewer and 404 page at 768 px.

---

## 9. Files Modified

| File | Change | Reason |
|---|---|---|
| `static/ds/ds.css` | **New** | Design tokens and shared components: type, spacing, radius, elevation, motion, site bar, buttons, segments, chips, cards, badges, inputs, tooltip, dialog/palette, skeleton, states, toast, Leaflet polish. |
| `static/ds/pages.css` | **New** | Overview layout, legacy-page harmonisation, water/pilot shell integration. |
| `static/ds/ds.js` | **New** | More menu, mobile drawer, search palette, tooltips, toast. |
| `static/ds/map-viewer.css`, `static/ds/icons/*.svg` | **New** | Map Viewer layout and layer icons. |
| `static/ds/catch-the-rain.js`, `static/ds/notfound.css` | **New** | 404 mini-game. |
| `static/ds/favicon.svg` | **New** | App icon (the old favicon request returned 404). |
| `static/fonts/manrope-*.woff2`, `Manrope-OFL.txt` | **New** | Self-hosted Manrope variable font and its licence. |
| `templates/partials/site_bar.html` | **New** | One shared navigation, drawer, search dialog, tooltip and toast hosts. |
| `templates/404.html` | **New** | Friendly 404 page and game markup. |
| `world/templates/world/base.html` | Rewritten | Shared site bar and footer, DS assets, font preload, favicon. |
| `world/templates/world/overview.html` | Rewritten | New dashboard structure (§4). |
| `world/static/world/js/overview.js` | **New** | Dashboard interactivity; supersedes `world-map.js`. |
| `world/static/world/js/world-map.js` | **Deleted** | Fully superseded by `overview.js` (same features plus layer-aware ranking, live tooltips, filters, detail, snapshots); no template referenced it any more. |
| `world/templates/world/map_viewer.html`, `world/static/world/js/map-viewer.js` | **New** | Algeria Map Viewer. |
| `world/services/regions.py` | **New** (replaces the first-pass `wilayas.py`) | ADM1 catalogue, on-demand boundary download and processing (MultiPolygon, antimeridian, labels), per-region layers, monthly history, events, dams. |
| `world/services/region_jobs.py` | **New** | Background builds with progress, at most two concurrent, snapshot saving. |
| `world/management/commands/refresh_regions.py` | **New** | `--country XX` (repeatable), `--existing`, `--all`. |
| `world/management/commands/refresh_wilayas.py` | **New** | Kept as an alias of `refresh_regions --country DZ`. |
| `world/data/geo_admin1/catalog_gbOpen.json`, `catalog_gbHumanitarian.json` | **New** | geoBoundaries ADM1 catalogues (per-country source, licence, year, URL). Downloaded country files are cached there and git-ignored. |
| `world/static/world/js/map-viewer.js`, `world/templates/world/map_viewer.html`, `static/ds/map-viewer.css` | Rewritten / extended | World mode, country drill-down, progress, breadcrumb and picker, history navigation, label collision, main-territory fit, per-country attribution. |
| `world/templates/world/country.html`, `world/static/world/js/overview.js`, `static/ds/ds.js`, `templates/partials/site_bar.html` | Modified | "Regional map" links everywhere; search group; menu copy. |
| `static/ds/themes.css` | **New** | Light and dark token sets; every legacy variable family mapped onto them; per-theme status inks; pilot overrides; theme toggle styles. |
| `templates/partials/theme_head.html` | **New** | Applies the saved or system theme before first paint (included by all three base templates). |
| `scripts/ds_theme_tokens.py` | **New** | Verified literal-to-token replacements (stylesheets) and white-overlay conversion. |
| `static/ds/ds.js`, `templates/partials/site_bar.html` | Modified | Theme toggle (bar and mobile menu), persistence, system-preference following, `ds:theme` event, `DS.cssVar()`. |
| `world/static/world/js/{overview,map-viewer,country-map,atlas-map,country-chart}.js`, `hydro/static/hydro/js/dashboard.js`, `static/js/map.js` | Modified | Map and chart colours come from theme tokens and are restyled or redrawn on `ds:theme`. |
| `world/templates/world/{dam,dams,methodology,sources}.html` | Modified | Theme-dependent inline colours replaced by tokens. |
| `world/models.py`, `world/migrations/0002_region_snapshot.py` | Modified / new | `RegionSnapshot` model. |
| `world/views.py` | Modified | `map_viewer` (with `/map/<ISO2>/`, `?c=`, legacy `?w=`), `api_regions`, `api_region_geo`, `api_region_catalog`, Algeria alias `api_wilayas`; `?version=` on `/api/world/`; snapshot list, attention count and Algeria snapshot in the overview context. |
| `world/urls.py` | Modified | `/map/`, `/map/<ISO2>/`, `/api/regions/…`, `/api/algeria/wilayas/`. |
| `world/services/sources.py` | Modified | Cache keys longer than 180 characters are hashed (48 wilaya codes exceeded the Windows 260-character path limit); existing keys are unchanged. |
| `world/management/commands/refresh_world.py` | Modified | Also refreshes wilaya layers in the unattended loop (failure-isolated). |
| `world/context.py` | **New** | Context processor: active nav item, snapshot time for the site bar. |
| `world/middleware.py` | **New** | Friendly 404 in DEBUG for HTML requests. |
| `config/settings.py` | Modified | `.mjs` MIME type (fixes the pilot map), context processor, middleware. |
| `config/urls.py` | Modified | `/favicon.ico` redirects to the SVG icon. |
| `hydro/templates/hydro/base.html` | Modified | Shared site bar, DS assets, favicon. |
| `dashboard/templates/base.html` | Modified | Shared site bar, DS assets, favicon, skip link. |
| `dashboard/templates/dashboard/partials/_simulator.html` | Modified | Declares `storm` in Alpine `x-data` (runtime error fix). |
| `world/static/world/css/{world,country,atlas,dam,hazards,docs}.css`, `hydro/static/hydro/css/app.css` | Modified by script | Minimum 12 px text, uppercase labels removed, font token. |
| `scripts/ds_normalize_css.py` | **New** | The reviewable script that made the stylesheet changes above. |
| `scripts/build_wilaya_geo.py`, `scripts/check_wilayas.py` | **New** | Boundary build and snapshot summary. |
| `static/data/dz-wilayas.geojson`, `static/data/dz-wilayas-lite.geojson` | **New** | Wilaya boundaries (full) and dashboard preview copy. |
| `world/data/geo_src/geoBoundaries-DZA-ADM1_simplified.geojson` | **New** | Unmodified source release, kept for provenance. |
| `scripts/ui_checks/{interact,states,shoot}.py`, `README.md` | **New** | Browser test scripts used for §11. |
| `docs/screenshots/redesign/*.png` | **New** | Result screenshots. |
| `DESIGN.md`, `README.md`, `docs/ARCHITECTURE.md` | Modified | Type section, new commands and routes, script references. |

---

## 10. Dependencies

- **No new Python or JavaScript runtime dependencies.** No framework was added. Leaflet, HTMX, Alpine and MapLibre were already vendored.
- **New asset:** the Manrope variable font (SIL Open Font License 1.1), self-hosted. Licence included.
- **New data:** geoBoundaries DZA ADM1 (ODbL 1.0). Attribution is shown on the map and in the API payload.
- **Test-only tooling:** Playwright (Python), driving the already-installed Microsoft Edge, for `scripts/ui_checks/`. It is not added to `requirements.txt`.

---

## 11. Testing

Everything below was actually run against the local dev server (`127.0.0.1:8010`) after the final edits.

| Test | Result |
|---|---|
| `python manage.py check` | System check identified no issues |
| `python manage.py test hydro.tests world.tests --keepdb --noinput` | **58 tests OK** |
| `python -m pytest` (core, dashboard, world) | **137 passed** |
| `scripts/ui_checks/shoot.py`, 11 routes × desktop 1440 + mobile 390 | Every route has the expected status (200, or 404 for the unknown URL), **0 console errors** (the 404 page logs only its own intended 404), **0 px overflow** |
| `scripts/ui_checks/interact.py` (theme, world, map, overview, search, game, pilot) | **78/78 passed** after the theme pass, covering: |
| | • Map Viewer: 48 wilaya paths drawn; URL preselect (Tlemcen); layer from URL; indicator click switches layer; legend updates; month on a latest-only layer switches to drought; URL keeps the month; back to the national summary; level chip; hover tooltip; click-to-select on the map (Adrar); exact-name search selects (Oran); dams overlay; mobile filter sheet, chips and no overflow; no console errors |
| | • Overview: Algeria preview map drawn with intact rings; layer switch retitles the ranking; ranking click opens detail; histogram filter and clear chip; KPI band filter; dams overlay; alert period filter (3 events in 7 days vs 200 total); category filter; wilaya preview layer switch; no console errors |
| | • Search and nav: Ctrl K opens; finds a wilaya (Tlemcen), a dam (Beni Haroun) and a country (Morocco); Enter navigates to `/country/MA/`; mobile drawer opens and closes with Esc |
| | • Theme: follows the system preference (dark and light); the toggle switches theme; the page background changes; the dashboard map recolours in place; the choice is saved and survives a reload (overriding the system); the map viewer's neighbouring land recolours; the water runway chart redraws; the pilot follows the toggle; the mobile menu toggle works; no console errors |
| | • World: starts in world mode (233 country shapes); world summary and legend; vegetation explained as per-region; country picker opens Morocco; breadcrumb back to the world; **browser Back** restores the country; Russia (antimeridian) renders its federal subjects and a click selects one (Krasnoyarsk Krai); a country without regions (Holy See) shows an honest message; country sheets link their regional map; no console errors |
| | • Pilot: MapLibre canvas renders; **no console errors** (previously 3 errors) |
| | • 404 at 1440 and 390: status 404; friendly copy; game starts; score and lives tracked; game-over state; restart resets the score; no overflow |
| `scripts/ui_checks/states.py` | **10/10 passed**: Map Viewer error state when the region API fails, then **Retry recovers**; **first-visit build progress** ("Fetching NASA POWER climate records · 20/48"); overview wilaya empty state; events error state; world-map fallback state; no overflow at **768 px** on overview, Map Viewer (world and country) and 404 |
| Both themes, every route | `THEME=light` and `THEME=dark` runs of `shoot.py` over 12 routes at desktop and mobile (48 page views): the expected theme is applied, no console errors, no overflow; contact sheets reviewed and the remaining dark literals fixed (pilot map chrome, score tracks, status chips, dam pills, inline breadcrumbs) |
| Worldwide builds | `refresh_regions` and on-demand builds for Algeria (48), Morocco (12), Tunisia (24), Spain (19), France (13), Brazil (27), India (36), United States (56) and Russia (83) — 0 source errors in every snapshot; screenshots reviewed for framing, labels and attribution |
| Visual review | Desktop, tablet and mobile screenshots of every route inspected; fixes made for a collapsed preview geometry, histogram label overlap, level-pill contrast, 404 heading wrap, mobile legend vs attribution overlap, and unwanted auto-scroll on shared links |

**Not tested:** real phones (only Chromium emulation with touch), Firefox and Safari, and screen readers. The keyboard paths and ARIA roles were implemented and keyboard-tested only through the scripted checks above.

---

## 12. Limitations

1. **48, not 58, wilayas.** The best openly licensed boundary releases (geoBoundaries gbOpen and gbHumanitarian) represent Algeria's **48-wilaya** division. The 10 wilayas created in 2019 (from former delegated wilayas in the south) are inside their parent polygons. Boundaries were **not** redrawn by hand; the limitation is stated in the UI, the GeoJSON metadata and the API.
2. **Vegetation health is a proxy.** The project has no NDVI or satellite-greenness source. The layer is root-zone soil wetness (NASA POWER GWETROOT) relative to the same month of earlier years, and it is labelled "proxy" wherever it appears.
3. **Point sampling on a coarse grid.** Each wilaya is sampled at one interior point. NASA POWER is about a 0.5° grid, so small neighbouring coastal wilayas can share a cell and show similar climate values. GloFAS is also point-sampled: some Saharan points return model discharge that produces a non-zero flood pressure (e.g. Adrar ≈ 33). That is the model's output, not invented, but it should be read as low-confidence.
4. **Coarse percentiles.** With about 10 years of monthly history, soil-moisture percentiles move in steps of about 12.5 points.
5. **Monthly replay covers only drought and vegetation.** Flood, fire and water stress depend on daily or forecast windows or long baselines, so they are latest-only. The UI says so and handles it.
6. **Snapshot history is short.** The world snapshot selector lists every stored snapshot (one at the time of writing); it grows with each refresh. The wilaya store keeps the last 30.
7. **The water runway and pilot apps were restyled, not restructured.** They now share the navigation, type and controls, but keep their own internal layouts. Rebuilding them was out of proportion to this pass.
8. **The palette was kept as requested.** In the first pass, dark and light pages were mixed. The third pass (§5c) replaced the mix with a full light and dark theme on every page, built only from the two existing palettes.
9. **Real-device and cross-browser testing** was not possible here (§11).
10. **Worldwide regions: first visits take time.** Opening a country nobody has opened yet takes about 10–75 s while the live sources are sampled; progress is shown. Only countries that have been opened, plus Algeria, are kept fresh by the refresh loop. `refresh_regions --all` can pre-build everything, but it makes thousands of public-API requests.
11. **Build state is held in memory.** Background-build progress lives in the web process, which is fine for the dev server or a single worker. With several workers each tracks its own builds; the results themselves are shared through the database.
12. **The boundaries come from the source as published.** They are not legal boundaries. Some releases include disputed areas: for example, Morocco's file includes Western Sahara, while the Natural Earth world layer shows it separately. The UI states that no position is taken. Licences differ by country and are shown per country.
13. **Different source vintages.** Each country's file has its own boundary year; some are older than the current administrative division (Algeria's 48 vs 58 wilayas is one example).
14. **Dams per region are the largest 1,500 per country.** For countries with tens of thousands of catalogued dams, only the 1,500 largest (monitored first) are placed into regions; the panel says "Largest dams here".

---

## 13. Final Summary

AquaState now behaves like one product instead of three:

- **Navigation and search** are shared across every page and adapt from desktop to phone.
- **Text** is set in a friendly typeface at a minimum of 12 px, with no uppercase tracking.
- **The original palette** sits on calmer surfaces with fewer borders.
- **The dashboard** guides a non-expert from a single question to explorable, filterable, linked data, every interaction backed by real data.
- **The Map Viewer** gives Algeria's 48 wilayas a real geographic, layer-by-layer reading, computed from the same NASA and Open-Meteo sources and the same published mathematics as the country index, with no invented numbers and with its limits stated.
- **The pilot simulator works again.** Every route is error-free and overflow-free at desktop, tablet and phone widths.
- **A lost visitor** gets a small, polished game instead of a dead end.
