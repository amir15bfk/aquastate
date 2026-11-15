# AquaState — Data Sources, Lineage and Honesty

**Last verified:** 2026-11-15. All adapters are keyless.

Every value carries a source kind: `live`, `cached`, `modeled`, `reference`, `proxy`, `unavailable` or `synthetic`. The UI and `/api/world/meta/` expose the ledger. The source page is `/sources/`.

## 1. Live world sources

| Source | What is fetched | Use | Cadence | Endpoint |
|---|---|---|---|---|
| NASA POWER / MERRA-2 monthly | `PRECTOTCORR`, `T2M`, `T2M_MAX`, `T2M_MIN`, `GWETROOT`, `GWETTOP`, 2016→current year | 10-year climatology, SPI, aridity, soil trends, Hargreaves PET | 24 h | `power.larc.nasa.gov/api/temporal/monthly/point` |
| NASA POWER / MERRA-2 daily | recent rain/soil at the hydrologic centroid | water-state profile | 6 h | `power.larc.nasa.gov/api/temporal/daily/point` |
| Open-Meteo forecast | 16-day rain, ET0, Tmax, Tmin, RHmin, wind; 92-day past window | fire weather, dry spell, drought context | 30 min | `api.open-meteo.com/v1/forecast` |
| Open-Meteo GloFAS flood | 60-day past + 16-day forecast `river_discharge` | flood pressure | 60 min | `flood-api.open-meteo.com/v1/flood` |
| NASA EONET | open drought, floods, wildfires, dustHaze, tempExtremes events | event pressure and the active-events rail | 30 min | `eonet.gsfc.nasa.gov/api/v3/events` |

**Important unit note.** NASA POWER `PRECTOTCORR` on the monthly endpoint is a **daily mean (mm/day)**. The adapter multiplies by the number of days in the month before any annual sum or SPI window. This was a real calibration bug found during the build (Hungary was initially scored on 18 mm/year instead of its true annual total).

**Important parser note.** The GloFAS multi-location response can emit lowercase `nan` for invalid locations (e.g. the pole). Python's `json` rejects lowercase `nan`; the adapter normalises `:nan`/`,nan` to `null` before parsing, and the payload sanitizer removes any non-finite values.

## 2. Reference sources

| Source | What | Use | Cadence |
|---|---|---|---|
| World Bank | population, renewable internal freshwater per capita, freshwater withdrawal %, forest area %, arable land % (2010–2025) | water availability, land pressure, population | 7 days |
| Wikidata full dam corpus | every dam item with a coordinate, plus English labels where available: name, country, coordinates; capacity/height for a notable subset | global dam atlas | 30 days |
| Natural Earth 50m | country geometry | world choropleth and country maps | static |
| Curated public inventories | DZ/TN reservoir capacities, coordinates, reference storage | monitored water state | static |

The dam atlas is a **cached build**, never a request-path dependency. The full pull uses 46 pages of 2,000 coordinate records plus batched SPARQL label queries:

- **91,568 coordinate statements** collapse to **82,363 unique dam items** in the seed;
- after linking the curated/pilot layer the table is **82,394 rows**, **33 monitored**, **172 countries**;
- **78,645** rows have an English label; the remainder fall back to their Wikidata ID;
- a notable subset (about 5,300) carries capacity, height or installed power.

Country geometry: **249 features** — 233 polygons + 16 small-island/sub-Antarctic point markers — so every profiled country is drawn and coloured. Antarctica has no country profile and is omitted. Boundaries are Natural Earth, not legal.

The full build is resumable: raw pages are in `world/data/dams_full_raw/`, labels in `world/data/dam_labels_sparql/`, and `load_full_dam_atlas` inserts only new QIDs so monitored rows are never overwritten.

## 3. Modeled / proxy data

| Output | How | Label |
|---|---|---|
| Reservoir storage | mass-balance reconstruction from public capacity, allocated demand, NASA rain, ET0 and base inflow; blended with reference percentages for DZ/TN | modeled/blended |
| Groundwater | root-zone wetness percentile + Sen/Mann–Kendall trend when no aquifer inventory | proxy |
| Drought | empirical SPI and soil percentile | modeled |
| Fire weather | VPD, dry spell, wind, soil percentile | modeled |
| Desertification | aridity + P/soil trends + forest change | modeled |
| Country index | deterministic aggregation of the above | modeled |
| Dam DRI | signed HRI-1.0 equations; bathymetry/climate/demand from the seeded pilot dataset | modeled |

No mapped aquifer → labelled root-zone proxy, never a hidden zero. No dam inventory → a visible national reference pool or an inventory-only atlas row, never an invented dam name.

## 4. Refresh and cache

- `settings.WCRI_*_TTL_*` controls source freshness.
- `world/services/sources.py` writes raw responses to `world/data/cache/` with a `_fetched_at` timestamp. Dates are serialized and restored explicitly.
- `world/services/refresh.py` is a single-flight file lock (`world/data/.refresh.lock`); stale locks are reclaimed after two hours.
- `python manage.py bootstrap_world` fetches what is due, recomputes WCRI and writes a new `WorldSnapshot`.
- `python manage.py refresh_world --loop --interval 900` runs it unattended.
- The page polls `/api/world/meta/` every 60 s; when the snapshot version changes it refreshes the choropleth and prompts a ledger reload.
- The **Refresh live data** button starts one background refresh; concurrent clicks return HTTP 409.

**Latest observed run:** snapshot `wcri-20261115002208` — 249 countries scored, average **61.5**, 70 resilient / 108 stable / 62 watch / 9 stressed / 0 critical, 200 active events, 181 s. Sources: NASA monthly 249 countries, World Bank 5 indicators, Open-Meteo forecast/flood in 50-country batches, EONET 200 events.

## 5. Failure modes

| Failure | Behaviour |
|---|---|
| NASA POWER down | Cached monthly/daily or `unavailable` pillars; coverage falls; map may show `NO_DATA` |
| Open-Meteo 429 | Retries with backoff; batches spaced; cached batch reused |
| GloFAS malformed `nan` | Normalised to `null`; country flood pillar may be unavailable |
| World Bank timeout | Empty bank; water uses aridity only with lower confidence |
| Wikidata query timeout | Atlas build uses cached raw pages; no request-path impact |
| Geometry missing | Country profile still exists; small islands use point markers |
| Source stale | UI labels “updated …” and the source ledger marks `due` |

## 6. Attribution

- NASA POWER / MERRA-2 — NASA Langley Research Center.
- Open-Meteo and GloFAS — Open-Meteo contributors.
- NASA EONET — NASA Earth Observatory.
- World Bank Open Data — World Bank.
- Natural Earth — public domain.
- Wikidata / Wikipedia — CC0 / CC BY-SA contributors.
- OpenStreetMap — © OpenStreetMap contributors, ODbL.
- IBM Plex — SIL Open Font License.
- Leaflet — BSD-2-Clause.

## 7. Disclaimer

AquaState is a screening and storytelling tool. It is **not** an operational flood, fire or drought warning system, not official water accounting, and not a basis for safety or investment decisions.
