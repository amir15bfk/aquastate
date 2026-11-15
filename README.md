# AquaState — World Water & Climate Observatory

**Water is the secret of life. This is its ledger.**

AquaState is the merged product of two NASA Space Apps projects:

- the country-scale **water app** — live NASA POWER / Open-Meteo data, a 250-country gazetteer, the WRI water-state index, Smart Horizon, the water runway and a Leaflet survey sheet;
- the dam-scale **space app** — the signed HRI deep index (SSI, CMI, SRRI, SAI, EESI), the Φ buffer bridge, the signed waterfall, scenarios and historical analogs.

The merged app adds the world layer: a country Water-Climate Resilience Index (**WCRI-2.0**), four live pressures (drought, flood, wildfire, desertification), an interactive world choropleth, a global dam atlas, and an unattended refresh loop.

---

## Quick start

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo --country DZ --country TN --force
python manage.py seed_hydro_data --reset --as-of 2026-11-13 --country DZA,TUN --years 10 --seed 42
python manage.py load_dam_atlas --reset     # notable/pilot/curated layer
python manage.py dedupe_dams                # merge only curated/pilot duplicates
python manage.py load_full_dam_atlas        # full Wikidata corpus with coordinates
python manage.py bootstrap_world            # fetch live sources, compute WCRI, write a snapshot
python manage.py compute_indices --all      # deep DRI snapshots for the 10 pilot dams
python manage.py refresh_regions --country DZ   # pre-build Algeria's 48 wilayas for the Map viewer (other countries build on first visit)
python manage.py runserver 127.0.0.1:8010
```

Loading the atlas before `bootstrap_world` matters: countries with monitored dams then use a capacity-weighted dam centroid instead of the national flag centroid. If you load the atlas later, run `bootstrap_world` again.

Open <http://127.0.0.1:8010/>.

For unattended refresh in a second terminal:

```powershell
python manage.py refresh_world --loop --interval 900
```

Or run `.\start.ps1`, which starts the refresher and the server together.

### Offline / cached mode

`bootstrap_world --offline` uses the source cache in `world/data/cache/` and never calls the network. The source status table on `/sources/` shows exactly what is live, cached or missing.

---

## What you can do

| Page | What it answers |
|---|---|
| `/` | Where is water stress becoming climate risk? Interactive world explorer (layers, ranking, distribution, country detail), Algeria preview, filterable active events, snapshot picker. |
| `/map/` | **Map viewer** — the world, then any of 209 countries' first-level regions (geoBoundaries ADM1: wilayas, states, provinces…) coloured by water stress, drought, flood, forest-fire risk or vegetation moisture (proxy), with a monthly replay, filters and a region detail panel. Regions are computed from live sources the first time a country is opened (`/map/?c=MA`). |
| `/country/<ISO2>/` | What is the country index, what is driving it, which dams are in the country, and what is the water system doing? |
| `/water/<ISO2>/` | The original water-state sheet: water runway, Smart Horizon, reservoir ledger, scenarios, sub-index arithmetic. |
| `/dam/<slug>/` | The deep DRI page for the 10 pilot dams: ring, buffer bridge, waterfall, sub-index stack, analogs. |
| `/dams/` | The global dam atlas: 82,000+ catalogued dams from the full Wikidata corpus, search, country filter, monitored-only filter, viewport map. |
| `/hazards/` | The four pressures, top countries, active EONET events, and what each pressure does and does not claim. |
| `/methodology/` | The merged index mathematics and the WCRI / WRI / DRI relationship. |
| `/sources/` | The live source ledger, refresh commands, coverage and attribution. |
| `/pilot/` | The space app's full split-screen simulator for the 10 pilot dams. |

### Index hierarchy

- **WCRI-2.0** — country index on the world map.
- **WRI-2.0** — country water system / water runway.
- **DRI-2.0** — dam deep index, ported from the signed HRI-1.0 mathematics.

The scores are deliberately separate. A forecast never rewrites an observed score; a national index never rewrites a dam index.

---

## Index summary

### WCRI-2.0

| Pillar | Weight |
|---|---:|
| Water availability & storage | 0.22 |
| Drought & soil | 0.20 |
| Groundwater | 0.14 |
| Flood resilience | 0.14 |
| Wildfire resilience | 0.14 |
| Desertification resilience | 0.16 |

```
base = 0.22·W + 0.20·D + 0.14·G + 0.14·F + 0.14·R + 0.16·L
penalty = 0.12·max(0, 30 − min(pillars))
        + 0.05·max(0, 45 − D)·max(0, 45 − R)/45
        + 0.05·max(0, 45 − D)·max(0, 45 − L)/45
WCRI = clamp(base − penalty, 0, 100)
```

Bands: **Resilient ≥70 · Stable 55–70 · Watch 40–55 · Stressed 25–40 · Critical <25**.
Coverage below 40% of the weight is `NO_DATA`, not a fake score.

### WRI-2.0 improvements

Mid-rank percentiles, SPI-3/SPI-12, confidence-weighted effective weights, the Φ buffer bridge, a continuous low-storage guard, source-freshness confidence, data coverage and country rank.

### DRI-2.0

The signed HRI mathematics is preserved as regression tests, including Beni Haroun:
`HRI_now=38.616 · HRI_proj=83.293 · Φ=0.94977 · HRI=81.05 · RECHARGING`.

See `docs/INDEX_MATH.md` for the full formulas and fixtures.

---

## Live data and auto-refresh

| Source | Use | Cadence | Key |
|---|---|---|---|
| NASA POWER / MERRA-2 monthly | 10-year rainfall, temperature, soil wetness, PET inputs | 24 h | none |
| NASA POWER / MERRA-2 daily | recent rain/soil near the hydrologic centroid | 6 h | none |
| Open-Meteo forecast | 16-day rain, ET0, temperature, humidity, wind, 92-day fire baseline | 30 min | none |
| Open-Meteo GloFAS flood | 60-day past + 16-day forecast river discharge | 60 min | none |
| NASA EONET | open drought, flood, wildfire, dust and temperature events | 30 min | none |
| World Bank | population, freshwater per capita, withdrawal, forest/arable land | 7 days | none |
| Wikidata | full dam corpus with coordinates + labels | 30 days | none |
| Natural Earth 50m | country geometry | static | none |

The refresh orchestrator uses a single-flight file lock, source TTLs, retries/backoff and a DB snapshot. The page polls `/api/world/meta/` every 60 seconds and updates the map when the snapshot version changes; the **Refresh live data** button starts a background refresh.

**Latest run in this workspace** (`refresh_world`, snapshot `wcri-20261115002208`): 249 countries scored, 82,394 catalogued dams, 33 monitored, 200 active events, average WCRI **61.5**, bands 70 resilient / 108 stable / 62 watch / 9 stressed / 0 critical — in 181 seconds.

---

## The dam atlas

The atlas is built from the **full Wikidata dam corpus with coordinates**, plus curated public inventories:

- **91,568** coordinate statements collapse to **82,394 unique dam items** across **172** countries;
- **78,645** rows have an English label; the remainder fall back to their Wikidata ID;
- **33** monitored rows (10 pilot dams with the full DRI + curated DZ/TN reservoirs);
- a notable subset still carries capacity/height/installed power; most full-corpus rows carry location and name only;
- searchable table, country filter, monitored-only filter, paginated; viewport map capped at 500 markers for speed;
- inventory rows are explicitly “not monitored”; no score is invented.

Raw build pages are cached under `world/data/dams_full_raw/`; labels under `world/data/dam_labels_sparql/`. The build is resumable. Coverage is honest: Wikidata itself is incomplete and occasionally duplicates or mislabels structures; it is a catalogue, not an operational inventory.

---

## Evidence

| Check | Result |
|---|---|
| `python manage.py check` | System check identified no issues |
| `python manage.py test hydro.tests world.tests --keepdb --noinput` | **Ran 58 tests · OK** |
| `python -m pytest -q core/tests dashboard/tests` | **122 passed** |
| `python manage.py refresh_world` | new snapshot `wcri-20261115002208`, 249 scored, average 61.5, 181 s |
| `python manage.py load_dam_atlas --reset` | notable/curated layer loaded, then deduped to 5,359 / 33 |
| `python manage.py load_full_dam_atlas` | **new=77,035 · total=82,394 · monitored=33 · countries=172** |
| `python manage.py compute_indices --all` | Beni Haroun **81.05 RECHARGING**, Bakhadda **19.90 CRITICAL** |

Screenshots: `docs/screenshots/world-full.png`, `country-full.png`, `dam-full.png`, `hazards-full.png`, `dams-atlas.png`.

---

## Data honesty

- **Live** means a fetch succeeded and a timestamp was stored. **Cached** is the last good copy.
- Reservoir storage is **modeled/blended**, not SCADA telemetry.
- Groundwater is a labelled **proxy** where no aquifer inventory exists; GRACE is not ingested in this MVP.
- Flood is GloFAS river discharge, not a local flood warning.
- Fire is fire weather, not an ignition forecast.
- Desertification is a pressure index, not a land-cover map.
- The dam atlas is the full Wikidata corpus, but Wikidata is not a complete physical census; some structures are unlabelled or duplicated.
- The app is a screening decision aid, **not for operational, safety or investment decisions**.

## Credits

NASA POWER / MERRA-2, Open-Meteo and GloFAS, NASA EONET, World Bank, Natural Earth, Wikidata and Wikipedia contributors, OpenStreetMap contributors, IBM Plex (SIL OFL), Leaflet (BSD-2-Clause).
