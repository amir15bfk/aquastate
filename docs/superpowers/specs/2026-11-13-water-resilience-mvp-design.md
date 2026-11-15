# AquaState — Water State & Hydrological Resilience MVP

**Date:** 2026-11-13  
**Status:** approved-by-directive (the brief says "start now")
**Stack:** Django 5, SQLite, server-rendered templates, vanilla JS, Leaflet (vendored).

## 1. Intent

Build a country-agnostic water-state dashboard that answers one question in one screen:

> **Are we covered until the next rain?**

It must show a mathematically explainable national Water Resilience Index, its sub-indexes, the Smart Horizon verdict, and the live spatial evidence (dams, soil moisture, groundwater, forecast, history) on a map beside the explanation.

The MVP index is **100% deterministic**. AI slots exist as an extension surface but are disabled and cannot change the core score without an explicit policy.

## 2. Goals / non-goals

### Goals
- Deterministic, auditable index with five sub-indexes and a visible aggregation formula.
- Smart Horizon: forward simulation that says **OK** when current storage is low but remaining water covers demand until a forecast refill, and the refill is enough.
- Country switch across 250 ISO countries. Algeria and Tunisia have curated reservoir/aquifer inventories; every country gets live satellite/forecast data and a national reference pool when no inventory exists.
- Real open data where available: NASA POWER (MERRA-2) soil moisture + precipitation climatology; Open-Meteo precipitation/ET0 forecast; Natural Earth outlines; OSM reservoir import adapter.
- Side-by-side map and explainability on desktop; responsive stacked layout on phone.
- Reserved AI-agent slots with audit records, contract, and tests proving they are off by default.
- A working demo with seeded data, tests, and evidence.

### Non-goals
- No operational reservoir telemetry or official agency data claims.
- No AI model in the default index path.
- No auth, alerts, payments, or mobile native app.
- No full global dam inventory: DZ/TN curated, other countries use a clearly labelled reference pool or OSM import.

## 3. Data model (Django `hydro` app)

- **Country**: ISO2/ISO3, name, region, subregion, area, population, centroid, bbox, `data_profile` JSON, `last_refresh`.
- **Reservoir**: country FK, name, lat/lon, capacity/storage/dead storage (Mm³), surface area (km²), inflow (Mm³/day), demand allocation (Mm³/day), `storage_source` (`reference`, `modeled`, `blended`, `osm`), `reference_storage_pct`, `is_reference_pool`, `metadata`.
- **Aquifer**: country FK, name, volume (km³), recharge/extraction (Mm³/day), trend (m/yr), `source`, `is_fossil`.
- **ClimateDay**: country FK, date, precip_mm, soil_surface, soil_root, et0_mm, source, unique (country, date).
- **ForecastDay**: country FK, reservoir FK nullable, date, precip_mm, et0_mm, temp_max_c, source, fetched_at.
- **StorageYear**: reservoir FK, year, end_storage_pct, source.
- **IndexSnapshot**: country FK, created_at, base_index, final_index, status, verdict, pillars JSON, horizon JSON, narrative, confidence, formula_version, data_quality JSON, ai_trace JSON, scenario JSON.
- **AIAgentSlot**: name, stage, description, enabled (default false), max_delta, weight, contract_version, endpoint.
- **AIContribution**: snapshot FK, slot FK, stage, proposed JSON, applied bool, delta, confidence, rationale, created_at.

`Country` rows are created lazily from the bundled 250-country gazetteer. Demo seed creates Algeria and Tunisia.

## 4. Data sources and honesty rules

| Source | Use | Freshness | Marking |
|---|---|---|---|
| NASA POWER API (`PRECTOTCORR`, `GWETTOP`, `GWETROOT`) | 10-year daily climate, soil-moisture percentile, 14-day rain normal, root-zone trend | fetched on seed/refresh | **Live satellite reanalysis** |
| Open-Meteo forecast (`precipitation_sum`, `et0_fao_evapotranspiration`, `temperature_2m_max`) | 16-day rain/ET0 forecast at reservoir coordinates | fetched on seed/refresh | **Live forecast** |
| Curated public dam capacity table | DZ/TN reservoir inventory | static reference | **Reference inventory** |
| Mass-balance reconstruction from climate | current reservoir storage + 10-year history | recomputed on refresh | **Modeled / blended** |
| Curated aquifer reports | DZ/TN groundwater pillars | static reference | **Reference estimate** |
| NASA POWER root-zone | groundwater proxy for countries without aquifer data | fetched | **Proxy** |
| Natural Earth 1:110m | country outline / map fallback | static | **Reference** |
| OpenStreetMap Overpass | optional reservoir import for any country | on demand | **OSM, community-mapped** |
| Deterministic fallback generator | offline/dev/test when APIs fail | static | **Synthetic fallback** (low confidence) |

No value is shown as "live" unless the API call succeeded and `fetched_at` is stored. Reservoir storage is never presented as telemetry.

## 5. Index mathematics (`WRI-1.0`)

All units: storage in Mm³, area in km², precipitation/ET0 in mm/day. `1 mm over 1 km² = 0.001 Mm³`.

### 5.1 Per-reservoir primitives

For reservoir *i*:

- usable `U_i = max(0, S_i − D_i)`
- evaporation `E_i = ET0 × A_i × 0.001 × 0.7`  (pan/convert factor 0.7)
- net burn `b_i = max(0.05, d_i + E_i − q_i)` where `d_i` is allocated demand and `q_i` base inflow.
- runway `cover_days_i = U_i / b_i`
- storage ratio `r_i = S_i / C_i` (reported, not used directly for the score)
- emergency reserve ratio `ε = 0.03` of live capacity (about 8–10 days of national demand in the demo). Individual reservoirs must stay above 1% of live capacity while they are major demand nodes.

### 5.2 Sub-indexes

**B — Storage buffer (weight 0.36)**  
`B = 100 × [Σ_i d_i × min(1, cover_days_i / 90)^0.85] / Σ_i d_i`  
If demand allocation is zero, capacity weights are used. A 90-day runway scores 100; 30 days ≈ 39; 60 days ≈ 71.

**M — Soil moisture (weight 0.18)**  
Current 7-day mean surface soil wetness (`GWETTOP`) compared with the same 28-day calendar window in the prior 10 years.  
`p = percentile rank`; `a = 50 + 50 × tanh((current − normal) / max(0.05, 0.25 × normal))`  
`M = 0.7p + 0.3a`, clipped 0–100. Falling back to root-zone if surface is unavailable.

**G — Groundwater (weight 0.16)**  
With aquifer records, volume-weighted:
`abstraction = 100 × clamp((1.25 − extraction/recharge) / 0.75, 0, 1)`  
`trend = 100 × clamp(0.5 + trend_m_per_year / 3, 0, 1)`  
`G_a = 0.55 × abstraction + 0.45 × trend`.
Without aquifer records, use root-zone percentile and Sen trend as a labelled proxy:
`G = 0.6 × percentile + 0.4 × trend_score`.

**F — Forecast opportunity (weight 0.14)**  
`F = 100 × min(1, (P14 / max(1, Pnormal14)) / 1.25)`  
where `P14` is the scenario-adjusted 14-day forecast total and `Pnormal14` is the 10-year same-window normal. A normal fortnight scores 80, 1.25× normal scores 100.

**T — Trend resilience (weight 0.16)**  
Annual end-storage history. Sen's slope `β` (% capacity/year), Mann–Kendall two-sided p-value.  
`T_raw = 100 × clamp(0.5 + β/4, 0, 1)`; `T = 50 + (T_raw − 50) × (1 − p)` (so an insignificant trend is pulled toward neutral 50).

### 5.3 Aggregation

`base = 0.36B + 0.18M + 0.16G + 0.14F + 0.16T`  
Bottleneck penalty `= 0.15 × max(0, 35 − min(B,M,G,F,T))`  
`WRI_base = clamp(base − penalty, 0, 100)`.

Status bands: **OK ≥ 60**, **Watch 45–59.9**, **Stressed 30–44.9**, **Critical < 30**.

### 5.4 Smart Horizon rule

A 45-day daily simulation per reservoir (the first 16 days carry forecast rain; zero rain is assumed after that):

```
rain_gain_i(t) = P_i(t − 2) × (C_i / 300) × 0.60   # 300 mm characteristic depth, 2-day runoff lag
inflow_i(t)    = q_i + rain_gain_i(t)
S_i(t+1)       = clamp(S_i(t) + inflow_i(t) − d_i − E_i(t), 0, C_i)
```

- **Relief event**: first day in the 16-day forecast where the demand-weighted 3-day rain total ≥ `clamp(5 × daily_demand / national_response, 5, 25)` mm. This scales the trigger to the deficit instead of using a flat 8 mm.
- `relief_day` = event day + 1 + 2-day runoff lag.
- `covered_to_relief`: the aggregate usable ratio stays ≥ 3% **and** every major reservoir stays ≥ 1% of capacity through `relief_day`.
- `post_relief_ok`: the reserve at relief is above 3%, and the refill adds at least `max(2 × daily demand, 2% of live capacity)`. The verdict is "OK until rain", not a promise of long-term sustainability.
- `secured` = relief exists, `relief_day ≤ horizon`, `covered_to_relief`, `post_relief_ok`.
- `buffered` = no relief in horizon, but runway ≥ 2 × horizon and reserve stays above ε.
- `tight` = relief exists but coverage or refill test fails.
- `exposed` = no relief and runway < 2 × horizon (or a relief beyond the horizon with insufficient reserve).

**No score rewrite.** `WRI_final = WRI_base` always. If the horizon is `secured` (or `buffered`), the index's **headline status** is `OK` with the horizon verdict “OK until rain” / “OK, buffered”, while the current-state (or scenario) score remains visible and unchanged. This is the Smart Horizon behaviour: the current level is not the binding constraint, but the arithmetic is not fudged. Under a what-if scenario the score is labelled scenario score and the forecast pillar moves; the horizon gate still does not rewrite it. The API exposes both `index.value` and `index.headline_label` / `index.headline_status` (forward-looking verdict).

### 5.5 Confidence

`confidence = Σ w_i × c_i` where `c_i` depends on source freshness/kind: live API 0.9–0.95, cached < 24h 0.85, modeled 0.65, curated reference 0.7, synthetic fallback 0.35. Confidence never changes the score; it is reported beside it.

### 5.6 Scenario controls

- Rain scenario: `forecast` (default, 1.0), `dry` (0.0), `whatif` (a labelled simulated 20 mm event on day 2 + forecast × 0.5).
- Demand factor: 0.8–1.5 (default 1.0), applied to `d_i`.
- Horizon: 7 / 14 / 30 days (default 14).
- Query parameters: `?rain=forecast|dry|whatif&demand=1.0&horizon=14`. Scenario computations are not persisted; the default snapshot is.

## 6. AI-ready architecture

`hydro/ai/`:
- `contracts.py`: `AgentContext`, `AgentSuggestion`, `AgentStage` enum (`post_subindex_advice`, `horizon_narrative`, `confidence_calibration`, `anomaly_explanation`), JSON-schema-like validation.
- `registry.py`: `BUILTIN_SLOTS` (five disabled slots) seeded into `AIAgentSlot`; `active_slots()` returns only enabled slots.
- `pipeline.py`: deterministic `apply_agent_suggestions(result, suggestions, policy)`. Bounded deltas (`≤ max_delta`), stage allow-list, no effect on pillars unless `policy.allow_subindex_adjustment=True` (default false), full audit trace. AI suggestions never alter formulas or inputs.
- Settings: `AI_AGENTS_ENABLED = False`, `AI_MAX_DELTA = 5.0`.
- API: `/api/ai/slots/` lists slots and policy; `/api/country/<iso>/audit/` returns full math + AI trace.
- Tests: disabled slots produce no contributions; a test slot is bounded; the default result is byte-identical with and without the registry; a malicious oversized delta is clamped/rejected.

## 7. HTTP surface

- `GET /` → redirect to `/country/DZ/`.
- `GET /country/<iso2>/` → dashboard (full HTML), query params for scenario.
- `GET /api/country/<iso2>/` → index + map + explainability JSON.
- `GET /api/country/<iso2>/audit/` → audit JSON (formulas, inputs, sources, AI trace).
- `GET /api/countries/` → gazetteer.
- `POST /api/country/<iso2>/refresh/` → refresh live sources (CSRF-protected; JSON).
- `POST /api/country/<iso2>/import-osm/` → optional OSM import.
- `GET /api/ai/slots/` → reserved slots.
- `GET /methodology/` → readable methodology + formulas.
- `GET /sources/` → source ledger and freshness.
- `GET /health/` → JSON status.

## 8. Dashboard composition

- 228px tinted sidebar + 48px top bar; white sheet inset 8px.
- Title row: `Algeria` h1 + "National water state" + freshness/refresh.
- Two-column body: map column (1fr) and 400px explainability rail.
- **Left:** Leaflet map with a bundled Natural Earth vector basemap (country fills, borders, graticule, labels), reservoir circles, soil toggle, selected-reservoir drawer, dam ledger (name, capacity, storage %, runway, rain day, status).
- **Right:** verdict card (horizon label, current-state score, cover days, rain day, horizon-gate note); **water runway** SVG; five `<details>` sub-index rows with formula/inputs/source/contribution; trend card (Sen slope, p, sparkline); confidence + lineage.
- **Scenario bar** above the map/rail: rain scenario segmented control, demand stress, horizon, reset.
- **Phone:** single column; map 320px; rail below; scenario bar scrolls/wraps; table becomes rows.
- All key numbers are server-rendered; scenario updates are progressive enhancement via `fetch`. Without JS, the form submits GET and the page recomputes server-side.

## 9. Verification plan

- Django system check, migrations, seed (offline + live), runserver.
- Unit tests: math primitives, weights, bands, horizon secured/dry/buffered, Mann–Kendall/Sen, AI gates, source fallbacks.
- View tests: dashboard 200 for DZ/TN, country switch, unknown country 404, scenario changes verdict, API schema, methodology/sources pages, audit JSON.
- Live smoke: Open-Meteo + NASA POWER fetch succeeds; seeded snapshot has real timestamps.
- Visual: run the design-taste `lint.mjs` and `inspect.mjs --app` at 1440/768/390; fix fails; read screenshots. Run impeccable detector once at the end.
- Evidence: command outputs, test summary, seeded data excerpts, HTTP responses, screenshots list.

## 10. Deliberate limits

- Reservoir storage cannot be claimed as live. The UI says "modeled + reference" and keeps the source visible.
- The national reference pool is a screening construct, not a dam. It is labelled on the map and in the ledger.
- The rainfall-runoff response is a screening coefficient (`C/300 × 0.6`), not a calibrated hydrological model.
- `WRI-1.0` is a decision aid, not an official water accounting standard.
