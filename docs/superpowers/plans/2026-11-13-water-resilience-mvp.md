# Plan — Water State & Hydrological Resilience MVP

**Date:** 2026-11-13 · **Status:** complete · **Index version:** WRI-1.0

## Build sequence

- [x] Frame the product: one question, deterministic core, Smart Horizon verdict, country-agnostic data.
- [x] Load a 250-country gazetteer, Natural Earth outlines, a hydrologic centroid, and World Bank population.
- [x] Model Country, Reservoir, Aquifer, ClimateDay, ForecastDay, StorageYear, IndexSnapshot, AI slots, AI contributions.
- [x] Implement NASA POWER and Open-Meteo adapters with timestamps, fallback, and source labels.
- [x] Implement curated Algeria/Tunisia inventories and a labelled national reference pool for other countries.
- [x] Implement mass-balance storage reconstruction and ten-year history.
- [x] Implement five sub-indexes, weights, bottleneck penalty, confidence, and full explainability payload.
- [x] Implement the 45-day Smart Horizon with 2-day runoff lag, dynamic relief threshold, per-major-reservoir reserve test, and refill sufficiency.
- [x] Decouple the score from the verdict (no score rewrite); headline status says “OK until rain” only when the forward gate is secured.
- [x] Implement the framed-sheet Django shell, map, runway, pillar ledger, scenario controls, and partial-page updates.
- [x] Implement the water runway, trend chart, map layers, reservoir detail, and keyboard-accessible ledger.
- [x] Implement AI-ready contracts, five disabled slots, bounded advisory trace, and core immutability tests.
- [x] Add methodology and source-ledger pages, audit API, health endpoint, and README.
- [x] Add 43 tests across statistics, engine, data lifecycle, AI boundary, views and API.
- [x] Run live seed for Algeria and Tunisia; verify NASA POWER + Open-Meteo.
- [x] Verify country-agnostic live profile for France (reference pool, hydrologic centroid).
- [x] Run the design gate at 1440/768/390; 0 FAIL, 0 WARN for Algeria, Tunisia what-if and methodology.
- [x] Run interactive smoke: scenario fetch, URL update, map init, 16 markers, mobile 390 no overflow, no JS errors.

## Key decisions and deviations

- **No horizon floor.** The math review flagged a hard jump to 60 as non-monotone and capable of turning Critical into OK. The implementation keeps `WRI` as the current/scenario state and reports a separate `headline_status` + horizon verdict. This still says “OK until rain” when coverage is secured.
- **Per-reservoir and refill tests.** Aggregate storage cannot mask a major empty reservoir; the refill must add at least two days of demand and 2% of live capacity.
- **Django 6.1.3.** Python 3.14 exposed a template-context bug in Django 5.0.6's test client; 6.1.3 is the supported runtime.
- **Hydrologic centroid.** Climate is sampled at the demand-weighted reservoir centre, not the country centroid, so a desert centroid cannot misrepresent a northern dam system.
- **World Bank population.** mledoze has no population and Natural Earth misses France's ISO; World Bank + name-matched outlines fixed the country-agnostic fallback.
- **Monospace figures.** IBM Plex Mono is the intentional numeric face (allowed by the app-screen style); the generic lint warns but the design inspector passes.

## Evidence

- `python manage.py test hydro.tests --keepdb --noinput` → **Ran 43 tests ... OK**.
- `node .../inspect.mjs --app` → **0 FAIL, 0 WARN** at 1440, 768, 390 for DZ, TN what-if, methodology.
- `node scripts/smoke_ui.mjs` → DZ/TN scenario updates, 16 markers, no JS errors, 390 no overflow.
- Live seed → NASA POWER/Open-Meteo rows and sources; FR live profile → reference pool, WRI 47.7, OK until rain.
- Audit endpoint → formula, weights, horizon gate, source ledger, AI trace.
