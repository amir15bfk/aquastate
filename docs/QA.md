# AquaState — QA and Evidence

**Date:** 2026-11-15. Environment: Windows, Python 3.14.4, Django 6.1.3.

## Automated tests

| Command | Result |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py test hydro.tests world.tests --keepdb --noinput` | **Ran 58 tests · OK** |
| `python -m pytest -q core/tests dashboard/tests` | **122 passed in 20.58s** |

The 122 pilot tests include the signed HRI fixtures. The 58 Django tests include the original water-app suite (43) and the new world suite (15).

## Data build evidence

```
python manage.py refresh_world            # latest snapshot wcri-20261115002208
  WCRI wcri-20261115002208: 249/249 scored, average 61.5, 200 events, 181.3s
  bands 70 resilient / 108 stable / 62 watch / 9 stressed / 0 critical
  errors 0
```

```
python manage.py load_dam_atlas --reset
  Atlas rows loaded: 5331
  Pilot dams linked: 10
  Curated reservoirs linked: 28

python manage.py dedupe_dams
  merged groups=8 deleted=8 total=5359 monitored=33

python scripts/fetch_full_dam_corpus.py
  46 pages of 2,000 coordinate records cached
  unique QIDs 82,363
  labels resolved in 46 batch SPARQL queries

python manage.py load_full_dam_atlas
  Full corpus loaded: new=77035 total=82394 monitored=33 countries=172
```

The full corpus collapses 91,568 coordinate statements to 82,363 unique dam items; 78,645 have an English label and the rest fall back to their Wikidata ID. The notable/curated layer remains intact with 33 monitored dams.

```
python manage.py compute_indices --all --as-of 2026-11-13
  DZA Beni Haroun:  HRI=81.05  RECHARGING
  DZA Bakhadda:     HRI=19.90  CRITICAL
  DZA Brezina:      HRI=34.01  STRESSED
  DZA Keddara:      HRI=76.25  STABLE
  TUN Sidi Salem:   HRI=71.85  STABLE
  ... 10/10 snapshots
```

## Page and API checks

All return HTTP 200 via the Django test client:

`/`, `/api/world/`, `/api/world/meta/`, `/country/DZ/`, `/country/US/`, `/dams/`, `/dam/beni-haroun/`, `/dam/QTEST/`, `/hazards/`, `/methodology/`, `/sources/`, `/water/DZ/`, `/pilot/`.

Automated assertions cover:

- world page contains the map and a ranked country;
- `/api/world/` ETag and country payload;
- country sheet contains the index, hazards, water card and dam table;
- atlas search returns the expected row;
- inventory-only dam renders the “not monitored” explanation;
- method and source pages contain the new versions;
- events GeoJSON shape;
- refresh endpoint is POST-only;
- meta endpoint exposes the snapshot version and sources.

## Visual inspection

Screenshots at 1440×1900 / 1440×1700 / 1440×1400:

- `docs/screenshots/world-full.png` — world hero, index card, 540px choropleth, pressure panel, 10-row ledger, active events, hazard cards, cascade.
- `docs/screenshots/country-full.png` — country index 44.3, four hazard cards, country map, dam table, WCRI waterfall, water system card, confidence.
- `docs/screenshots/dam-full.png` — DRI 81.0 RECHARGING, buffer bridge, waterfall, sub-index stack, analogs, country context.
- `docs/screenshots/hazards-full.png` — four pressure cards and active event table.
- `docs/screenshots/dams-atlas.png` — 82,394 catalogue, viewport map, filters, table.
- `docs/screenshots/world-desktop.png` — earlier first-fold capture.

The review found and fixed: white-on-white country theme (specificity), monthly precipitation unit bug (mm/day → monthly total), Open-Meteo 429 handling, lowercase `nan` in GloFAS, duplicate atlas rows, events assigned to the wrong country (nearest centroid → point-in-polygon), Antarctica/polar framing, coverage shown as 1% instead of 100%, and raw m³ capacity instead of Mm³.

## Known limitations

- The country climate is a point sample at a hydrologic centroid, not a gridded national average.
- Groundwater is a proxy for countries without aquifer inventories.
- The atlas is the full Wikidata corpus, but Wikidata is not a complete physical census and can duplicate or mislabel structures.
- All 249 profiled countries are drawn; the six polar/sub-Antarctic profiles use point markers rather than distorting polygons. Antarctica has no profile.
- The full all-in-one `manage.py test` discovery is not used; run the two canonical commands above (a Django test-package name collision between app `tests` packages).
- The pilot simulator is mounted at `/pilot/`; the merged dam page links to it rather than duplicating the HTMX simulator inline in v1.

## Reproduce

```powershell
python manage.py migrate
python manage.py seed_demo --country DZ --country TN --force
python manage.py seed_hydro_data --reset --as-of 2026-11-13 --country DZA,TUN --years 10 --seed 42
python manage.py load_dam_atlas --reset
python manage.py dedupe_dams
python manage.py load_full_dam_atlas
python manage.py bootstrap_world
python manage.py compute_indices --all
python manage.py runserver 127.0.0.1:8010
```
