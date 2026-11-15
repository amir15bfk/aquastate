# AquaState — Architecture

## Stack

- Python 3.14.4, Django 6.1.3, SQLite (WAL-friendly timeout).
- Server-rendered Django templates, vanilla JS, vendored Leaflet.
- Pydantic/numpy only for the ported pilot data/index path; the world layer uses stdlib `math`, `statistics`, `urllib`/`requests`.
- No tile server, no API key, no LLM in the index path.

## Apps

```text
config/                 Django settings and root URLs
hydro/                  the water app
  models.py             Country, Reservoir, Aquifer, ClimateDay, ForecastDay,
                        StorageYear, IndexSnapshot, AIAgentSlot, AIContribution
  services/             gazetteer, open_data, data_service, storage,
                        statistics, index_engine (WRI-2.0)
  templates/hydro/      water-state sheet, method and sources legacy views
  tests/                43 tests

core/                   the space app's deep index
  models.py             Country, Basin, Dam, observations, climatology, IndexSnapshot
  services/
    indices/            SSI, CMI, SRRI, SAI, EESI
    buffer.py           Q_out, autonomy, SCS-CN, Φ
    hri.py              HRI/DRI synthesis, continuous guard
    analog.py           historical analogs
    scenario.py         validated overrides
    snapshots.py        compute + persist
  management/commands/  seed_hydro_data, compute_indices
  tests/                122 pytest tests (unchanged signed fixtures)

dashboard/              the space app's split-screen pilot UI
  views.py              /pilot/ dashboard and HTMX partials
  templates/            base, index, partials

world/                  the new world layer
  models.py             CountryProfile, CountryIndexSnapshot, DamAtlas,
                        HazardEvent, HazardCountryScore, SourceStatus,
                        RefreshRun, WorldSnapshot
  services/
    sources.py          NASA POWER, Open-Meteo, GloFAS, EONET, World Bank
    statistics.py       mid-rank percentile, SPI helpers, Hargreaves PET
    country_index.py    WCRI-2.0
    geo.py              point-in-polygon event assignment
    refresh.py          single-flight file lock
  management/commands/  bootstrap_world, refresh_world, load_dam_atlas,
                        dedupe_dams, load_full_dam_atlas
  templates/world/      overview, country, dams, dam, hazards, method, sources
  static/world/         world.css, country.css, atlas.css, dam.css, hazards.css,
                        docs.css, overview.js, map-viewer.js, country-map.js, country-chart.js,
                        atlas-map.js
  tests/                15 tests

static/data/            countries-world.geojson (Natural Earth 50m, 243 features)
scripts/                build_world_geo.py, build_dam_atlas.py
world/data/             dam_atlas_seed.json, dams_raw/, cache/
docs/                   PRODUCT, DESIGN, INDEX_MATH, DATA_SOURCES, ARCHITECTURE, QA
```

## Data flow

```text
NASA POWER monthly ─┐
Open-Meteo forecast ─┤
Open-Meteo GloFAS ───┼→ world/services/sources.py (TTL cache, retry, batch)
NASA EONET ──────────┤
World Bank ──────────┘
        ↓
country_index.compute_country
  water / drought / groundwater / flood / fire / desertification
        ↓
CountryProfile + CountryIndexSnapshot + HazardCountryScore
        ↓
WorldSnapshot payload → /api/world/ → overview.js
        ↓
Country page → WCRI waterfall + hazard strip + dam table
Dam page → DRI (core.services.snapshots) + waterfall + sub-indices
```

The pilot dam path is independent: `core.services.snapshots.compute_dam_state` reads the seeded `core` tables and returns the signed DRI. The world layer never mutates the DRI core.

## Index boundaries

- **WCRI** — country index, world map. Uses `world/services/country_index.py`.
- **WRI** — country water system. Uses `hydro/services/index_engine.py`; the `/water/<ISO2>/` page.
- **DRI** — dam deep index. Uses `core/services/hri.py`; the `/dam/<slug>/` page for pilot dams.

The scores are not summed together. A low WRI can coexist with a good WCRI if the hazards are mild; a dam can recharge while its country is stressed. That is intentional.

## Auto-refresh

1. `bootstrap_world` checks `SourceStatus` TTLs.
2. Sources are fetched with batching (50 coordinates per Open-Meteo call) and retry/backoff.
3. Each country is recomputed; profiles, snapshots and hazard scores are upserted in one transaction.
4. A new `WorldSnapshot` is written with `version=wcri-YYYYMMDDHHMMSS`; the previous current snapshot is retired.
5. `/api/world/meta/` exposes version, updated time, next refresh, source status and whether a refresh is running.
6. `overview.js` polls meta every 60 s; a version change reloads the snapshot into the map, ranking and charts without a page reload.
7. `refresh_world --loop --interval 900` is the unattended scheduler; `start.ps1` runs it beside the server.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | world overview |
| GET | `/country/<ISO2>/` | merged country sheet |
| GET | `/water/<ISO2>/` | water-state sheet |
| GET | `/dams/` | dam atlas (search, filters, pagination) |
| GET | `/dam/<slug>/` | pilot DRI or inventory card |
| GET | `/hazards/` | four-pressure board |
| GET | `/methodology/`, `/sources/` | method and source ledger |
| GET | `/api/world/` | snapshot payload (ETag, 60 s cache) |
| GET | `/api/world/meta/` | version, source status, next refresh |
| POST | `/api/world/refresh/` | single-flight background refresh |
| GET | `/api/world/country/<ISO2>/` | profile + WRI + dams + events |
| GET | `/api/dams/` | atlas rows; `q`, `country`, `monitored`, `bbox`, `page` |
| GET | `/api/events/` | EONET GeoJSON |
| GET | `/api/country/<ISO2>/` | WRI payload (legacy water app) |
| GET | `/api/pilot/dams/<slug>/` | DRI payload (pilot app) |
| GET | `/health/` | water-layer health |

## Commands

```powershell
python manage.py bootstrap_world [--offline] [--force] [--limit N]
python manage.py refresh_world [--loop] [--interval 900]
python manage.py load_dam_atlas [--reset]
python manage.py dedupe_dams
python manage.py load_full_dam_atlas          # 82k full Wikidata corpus
python scripts/fetch_full_dam_corpus.py       # resumable raw pages + labels
python scripts/build_full_dam_seed.py         # assemble the full seed
python manage.py seed_demo --country DZ --country TN --force
python manage.py seed_hydro_data --reset --as-of 2026-11-13 --country DZA,TUN --years 10 --seed 42
python manage.py compute_indices --all --as-of 2026-11-13
```

## Tests

```powershell
python manage.py check
python manage.py test hydro.tests world.tests --keepdb --noinput   # 58 tests
python -m pytest -q core/tests dashboard/tests                     # 122 tests
```

The pilot tests keep the original signed fixtures. The world tests cover percentiles, PET, WCRI scoring, missing data, pages, APIs, atlas search and event GeoJSON.


## Regional layers (Map viewer)

`world/services/regions.py` downloads a country's ADM1 boundaries from geoBoundaries on first use
(`world/data/geo_admin1/<ISO3>.geojson`, catalogue in `catalog_*.json`), samples NASA POWER, Open-Meteo and
GloFAS at an interior point of every region and runs the same `compute_country` mathematics. First visits are
built in a background thread (`world/services/region_jobs.py`) and reported to the page as progress; results
are stored as `RegionSnapshot(region=<ISO2>)`. `refresh_regions --existing` (called by `refresh_world`) keeps every
opened country fresh. APIs: `/api/regions/`, `/api/regions/<ISO2>/`, `/api/regions/<ISO2>/geo/`.
