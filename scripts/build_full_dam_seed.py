"""Assemble the full dam corpus seed from cached coordinate pages + batch labels."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
RAW = BASE / "world" / "data" / "dams_full_raw"
LABEL_CACHE = BASE / "world" / "data" / "dam_labels_sparql"
COUNTRY_CACHE = BASE / "world" / "data" / "country_qid_iso2.json"
EXISTING_SEED = BASE / "world" / "data" / "dam_atlas_seed.json"
OUT = BASE / "world" / "data" / "dam_atlas_full.json"
LABEL_CACHE.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; full dam labels)"}
SPARQL = "https://query.wikidata.org/sparql"


def post_query(query, timeout=180, retries=3):
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(SPARQL, data={"query": query, "format": "json"}, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(10 * (attempt + 1))
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(str(last))


def country_map():
    if COUNTRY_CACHE.exists():
        return json.loads(COUNTRY_CACHE.read_text(encoding="utf-8"))
    query = "SELECT ?country ?iso2 WHERE { ?country wdt:P297 ?iso2 . }"
    payload = post_query(query, timeout=60)
    mapping = {}
    for row in payload["results"]["bindings"]:
        qid = row["country"]["value"].rsplit("/", 1)[-1]
        mapping.setdefault(qid, row["iso2"]["value"].upper())
    COUNTRY_CACHE.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    return mapping


def labels_for(qids, key):
    cache = LABEL_CACHE / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    values = " ".join(f"wd:{qid}" for qid in sorted(set(qids)))
    query = (
        "SELECT ?d ?dLabel WHERE { VALUES ?d { "
        + values
        + ' } SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    )
    payload = post_query(query)
    labels = {}
    for row in payload["results"]["bindings"]:
        qid = row["d"]["value"].rsplit("/", 1)[-1]
        label = (row.get("dLabel") or {}).get("value")
        if label and qid not in labels:
            labels[qid] = label
    cache.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    return labels


def parse_point(value):
    inner = value.replace("Point(", "").replace(")", "").strip().split()
    if len(inner) < 2:
        return None
    return float(inner[1]), float(inner[0])


def main():
    country = country_map()
    existing = {}
    if EXISTING_SEED.exists():
        for row in json.loads(EXISTING_SEED.read_text(encoding="utf-8")):
            existing[row["wikidata_id"]] = row

    # Load the country geometry once for the few records without an ISO code.
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
        boxes.append(
            (
                min(p[0] for p in points),
                min(p[1] for p in points),
                max(p[0] for p in points),
                max(p[1] for p in points),
                feature,
            )
        )

    def assign(iso2, lat, lon):
        if iso2:
            return iso2
        for west, south, east, north, feature in boxes:
            if west <= lon <= east and south <= lat <= north:
                geometry = feature.get("geometry") or {}
                kind = geometry.get("type")
                coords = geometry.get("coordinates") or []
                if kind == "Polygon" and geo._point_in_polygon(lon, lat, coords):
                    return feature["properties"]["iso2"]
                if kind == "MultiPolygon":
                    for polygon in coords:
                        if geo._point_in_polygon(lon, lat, polygon):
                            return feature["properties"]["iso2"]
        return ""

    rows = {}
    page_files = sorted(RAW.glob("page_*.json"))
    for index, path in enumerate(page_files, start=1):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bindings = payload.get("results", {}).get("bindings", [])
        qids = [row["d"]["value"].rsplit("/", 1)[-1] for row in bindings]
        labels = labels_for(qids, path.stem)
        print(f"{index}/{len(page_files)} {path.name} rows={len(bindings)} labels={len(labels)}", flush=True)
        for row in bindings:
            qid = row["d"]["value"].rsplit("/", 1)[-1]
            point = parse_point(row["coord"]["value"])
            if not point:
                continue
            lat, lon = point
            country_qid = (row.get("country") or {}).get("value", "")
            iso2 = country.get(country_qid.rsplit("/", 1)[-1], "") if country_qid else ""
            old = existing.get(qid, {})
            rows[qid] = {
                "wikidata_id": qid,
                "name": (old.get("name") or labels.get(qid) or qid)[:240],
                "country_iso2": assign(iso2, lat, lon),
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "capacity_m3": old.get("capacity_m3"),
                "installed_mw": old.get("installed_mw"),
                "height_m": old.get("height_m"),
                "year_built": old.get("year_built"),
                "source": "Wikidata full corpus",
                "source_url": f"https://www.wikidata.org/wiki/{qid}",
                "coordinates": old.get("coordinates", 1),
            }
    out = sorted(rows.values(), key=lambda row: (row["country_iso2"], row["name"]))
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"written={len(out)} with_country={sum(1 for r in out if r['country_iso2'])} "
        f"with_name={sum(1 for r in out if r['name'] != r['wikidata_id'])} bytes={OUT.stat().st_size}",
        flush=True,
    )


if __name__ == "__main__":
    main()
