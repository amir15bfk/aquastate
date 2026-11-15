# AquaState — Product Context

**Mode:** Operate (a working analytical dashboard, not a marketing page).
**One-sentence product:** AquaState tells a water analyst, in one screen, whether a country's stored water and its next forecast rain together cover demand — and shows the arithmetic behind that answer.

## Who it serves

Hydrologists, water-agency analysts, and resilience officers who need a defensible country-level read in under a minute, then need to inspect a dam or a sub-index without leaving the screen.

## The one question

**"Are we covered until the next rain?"**

Every element on the overview serves that question: the horizon verdict, the water runway, the map of dams, and the five sub-index explanations.

## Product truth

- The score is 100% deterministic mathematics. No AI agent touches the MVP index.
- Every number carries its formula, inputs, source, confidence, and contribution.
- The Smart Horizon rule is explicit: low storage today is not a crisis if the forward balance stays above the emergency reserve until a forecast refill arrives.
- Data honesty matters more than completeness: real satellite/forecast sources are marked live; reference reservoir inventories and reconstructed storage histories are marked as estimates.
- Country-agnostic: 250 ISO countries are selectable. Algeria ships with a curated inventory; Tunisia is the second curated profile; every other country gets a national reference pool from live satellite data (and can import OSM reservoirs when available).

## Jobs

1. Glance at the verdict and the days of runway.
2. Switch country.
3. Stress the forecast (dry / forecast / rain-in-2-days) and demand to see when the verdict flips.
4. Expand any sub-index and read its arithmetic.
5. Select a reservoir on the map and inspect its storage, cover days, and rain response.
6. Refresh live forecast/soil data and see the freshness stamp.
7. Read the methodology and the source ledger.

## Non-goals

- No AI-generated adjustments in the MVP.
- No real-time SCADA reservoir telemetry (not openly available); reservoir storage is a labelled reference estimate.
- No user accounts, alerts delivery, or mobile app.
- No claims of official agency endorsement.

## Assumptions (inferred from the brief; no interview)

- English UI for the MVP.
- SQLite is the right storage for a single-instance challenge demo; the ORM is portable to Postgres.
- Leaflet with a bundled Natural Earth vector basemap (country fills, borders, graticule) is the chosen map; no external raster tiles or keys.
- NASA POWER (MERRA-2) and Open-Meteo are acceptable open, keyless sources.
- Reservoir capacity/storage figures are screening-level references, not official operational data.
