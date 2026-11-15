"""Fetch the full Wikidata dam corpus with coordinates and labels.

Pages of 2,000 rows are cached under world/data/dams_full_raw/. Labels are
resolved through the Wikidata API in batches of 50 and cached in
world/data/dam_labels.json. The build is resumable: rerun after a failure and
it skips pages/ids already present.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
sys.path.insert(0, str(BASE))
RAW = BASE / "world" / "data" / "dams_full_raw"
RAW.mkdir(parents=True, exist_ok=True)
LABELS_FILE = BASE / "world" / "data" / "dam_labels.json"
SEED_OUT = BASE / "world" / "data" / "dam_atlas_full.json"
EXISTING_SEED = BASE / "world" / "data" / "dam_atlas_seed.json"
COUNTRY_FILE = BASE / "world" / "data" / "dam_counts_by_country.json"

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus build)"}
SPARQL = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"
PAGE_SIZE = 2000
TOTAL = 91568

PAGE_QUERY = """
SELECT ?d ?coord ?country WHERE {{
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  OPTIONAL {{ ?d wdt:P17 ?country . }}
}}
ORDER BY ?d
LIMIT {limit} OFFSET {offset}
"""

COUNTRY_QUERY = """
SELECT ?country ?iso2 WHERE { ?country wdt:P297 ?iso2 . }
"""


def get_json(url, params, timeout=180, retries=4):
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 10 * (attempt + 1)
                print(f"  HTTP {r.status_code}; sleeping {wait}s")
                time.sleep(wait)
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(str(last))


def fetch_country_map():
    payload = get_json(SPARQL, {"query": COUNTRY_QUERY, "format": "json"}, timeout=60)
    mapping = {}
    for row in payload["results"]["bindings"]:
        qid = row["country"]["value"].rsplit("/", 1)[-1]
        mapping.setdefault(qid, row["iso2"]["value"].upper())
    return mapping


def fetch_pages():
    for offset in range(0, TOTAL, PAGE_SIZE):
        path = RAW / f"page_{offset:06d}.json"
        if path.exists():
            continue
        print(f"page {offset}", flush=True)
        payload = get_json(
            SPARQL,
            {"query": PAGE_QUERY.format(limit=PAGE_SIZE, offset=offset), "format": "json"},
            timeout=240,
        )
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        time.sleep(1.0)


def parse_qid(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def parse_point(value: str):
    inner = value.replace("Point(", "").replace(")", "").strip()
    parts = inner.split()
    if len(parts) < 2:
        return None
    return float(parts[1]), float(parts[0])


def load_labels(qids: list[str]) -> dict[str, str]:
    labels = json.loads(LABELS_FILE.read_text(encoding="utf-8")) if LABELS_FILE.exists() else {}
    missing = [qid for qid in qids if qid not in labels]
    print(f"labels cached={len(labels)} missing={len(missing)}", flush=True)
    batches = [missing[i : i + 50] for i in range(0, len(missing), 50)]

    def one(batch):
        payload = get_json(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels",
                "languages": "en",
                "languagefallback": "1",
                "format": "json",
            },
            timeout=60,
            retries=6,
        )
        out = {}
        for qid, entity in (payload.get("entities") or {}).items():
            label = ((entity.get("labels") or {}).get("en") or {}).get("value")
            out[qid] = label
        return out

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(one, batch) for batch in batches]
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                labels.update({k: v for k, v in future.result().items() if v})
            except Exception as exc:
                print("  label batch failed:", exc)
            if index % 100 == 0:
                LABELS_FILE.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
                print(f"  labels {index}/{len(batches)}", flush=True)
    LABELS_FILE.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    return labels


def load_geo():
    from world.services import geo

    geo._features.cache_clear()
    features = geo._features()
    boxes = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Polygon":
            rings = geometry.get("coordinates") or []
        elif geometry.get("type") == "MultiPolygon":
            rings = [ring for poly in geometry.get("coordinates", []) for ring in poly]
        else:
            continue
        points = [point for ring in rings for point in ring]
        if not points:
            continue
        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        boxes.append((min(lons), min(lats), max(lons), max(lats), feature))
    return geo, boxes


def country_for_iso(iso2: str) -> str:
    return iso2 or ""


def main():
    fetch_pages()
    country_map = fetch_country_map()
    print("country map", len(country_map), flush=True)

    rows = {}
    for path in sorted(RAW.glob("page_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("results", {}).get("bindings", []):
            qid = parse_qid(row["d"]["value"])
            coord = parse_point(row["coord"]["value"])
            if not coord:
                continue
            lat, lon = coord
            country_qid = (row.get("country") or {}).get("value", "")
            iso2 = country_map.get(parse_qid(country_qid), "") if country_qid else ""
            rows.setdefault(qid, {"lat": lat, "lon": lon, "iso2": iso2})
    print("unique qids", len(rows), flush=True)

    labels = load_labels(sorted(rows))
    existing = {}
    if EXISTING_SEED.exists():
        for row in json.loads(EXISTING_SEED.read_text(encoding="utf-8")):
            existing[row["wikidata_id"]] = row

    geo, boxes = load_geo()

    def assign(iso2, lat, lon):
        if iso2:
            return iso2
        for west, south, east, north, feature in boxes:
            if west <= lon <= east and south <= lat <= north:
                geometry = feature.get("geometry") or {}
                if geo._point_in_polygon(lon, lat, geometry.get("coordinates") or []):
                    return feature["properties"]["iso2"]
        return ""

    out = []
    for qid, row in rows.items():
        old = existing.get(qid, {})
        iso2 = assign(row["iso2"], row["lat"], row["lon"])
        out.append(
            {
                "wikidata_id": qid,
                "name": (old.get("name") or labels.get(qid) or qid)[:240],
                "country_iso2": iso2,
                "lat": round(row["lat"], 4),
                "lon": round(row["lon"], 4),
                "capacity_m3": old.get("capacity_m3"),
                "installed_mw": old.get("installed_mw"),
                "height_m": old.get("height_m"),
                "year_built": old.get("year_built"),
                "source": "Wikidata full corpus",
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "coordinates": old.get("coordinates", 1),
            }
        )
    out.sort(key=lambda row: (row["country_iso2"], row["name"]))
    SEED_OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"written {len(out)} rows · with_country={sum(1 for r in out if r['country_iso2'])} · "
        f"with_label={sum(1 for r in out if r['name'] != r['wikidata_id'])} · "
        f"bytes={SEED_OUT.stat().st_size}",
        flush=True,
    )


if __name__ == "__main__":
    main()
