"""Build the global notable-dam atlas from Wikidata + Wikipedia sitelinks.

The query returns dams that have an English Wikipedia article, which is a
useful proxy for "notable enough to catalogue". It is not a claim that every
small structure on Earth is present. The raw pages are kept so the build is
auditable and can be re-run without re-querying if it fails part-way.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

import requests

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
RAW = BASE / "world" / "data" / "dams_raw"
OUT = BASE / "world" / "data" / "dam_atlas_seed.json"
RAW.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (NASA Space Apps challenge; local demo)"}
ENDPOINT = "https://query.wikidata.org/sparql"

PAGE_QUERY = """
SELECT ?d ?coord ?article ?country ?iso2 ?height ?capacity ?inception WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  ?article schema:about ?d ; schema:isPartOf <https://en.wikipedia.org/> .
  OPTIONAL { ?d wdt:P17 ?country . }
  OPTIONAL { ?country wdt:P297 ?iso2 . }
  OPTIONAL { ?d wdt:P2048 ?height . }
  OPTIONAL { ?d wdt:P2109 ?capacity . }
  OPTIONAL { ?d wdt:P571 ?inception . }
}
ORDER BY ?d
LIMIT {limit} OFFSET {offset}
"""

COUNTRY_QUERY = """
SELECT ?country ?iso2 WHERE { ?country wdt:P297 ?iso2 . }
"""


def fetch(query: str, retries: int = 3):
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                ENDPOINT,
                params={"query": query, "format": "json"},
                headers=HEADERS,
                timeout=150,
            )
            if response.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            print("  retry", attempt + 1, exc)
            time.sleep(3 * (attempt + 1))
    return None


def parse_point(value: str):
    inner = value.replace("Point(", "").replace(")", "").strip()
    parts = inner.split()
    if len(parts) < 2:
        return None, None
    return float(parts[1]), float(parts[0])


def article_name(url: str) -> str:
    if "/wiki/" not in url:
        return ""
    name = urllib.parse.unquote(url.split("/wiki/", 1)[1])
    return name.replace("_", " ").strip()


def to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# Country QID -> ISO2, for rows where the direct P297 join is missing.
country_map = {}
payload = fetch(COUNTRY_QUERY)
if payload:
    for row in payload.get("results", {}).get("bindings", []):
        qid = row["country"]["value"].rsplit("/", 1)[-1]
        country_map.setdefault(qid, row["iso2"]["value"].upper())

all_rows = []
limit = 1000
for page in range(0, 40):
    offset = page * limit
    cache_file = RAW / f"page_{offset:05d}.json"
    if cache_file.exists():
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        print(f"fetching offset {offset}")
        payload = fetch(PAGE_QUERY.replace("{limit}", str(limit)).replace("{offset}", str(offset)))
        if payload is None:
            print("  page failed; stopping with what we have")
            break
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        time.sleep(1.5)
    rows = payload.get("results", {}).get("bindings", [])
    print(f"  rows {len(rows)}")
    if not rows:
        break
    all_rows.extend(rows)
    if len(rows) < limit:
        break

by_qid: dict[str, dict] = {}
for row in all_rows:
    qid = row["d"]["value"].rsplit("/", 1)[-1]
    lat, lon = parse_point(row["coord"]["value"])
    if lat is None:
        continue
    country_qid = (row.get("country") or {}).get("value", "").rsplit("/", 1)[-1]
    iso2 = (row.get("iso2") or {}).get("value", "").upper() or country_map.get(country_qid, "")
    name = article_name(row.get("article", {}).get("value", ""))
    if not name:
        continue
    height = (row.get("height") or {}).get("value")
    capacity = (row.get("capacity") or {}).get("value")
    inception = (row.get("inception") or {}).get("value", "")
    existing = by_qid.get(qid)
    candidate = {
        "wikidata_id": qid,
        "name": name,
        "country_iso2": iso2,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "height_m": to_float(height),
        "installed_mw": to_float(capacity),
        "year_built": int(inception[:4]) if inception[:4].isdigit() else None,
        "inception": inception or None,
        "source": "Wikidata / Wikipedia",
        "source_url": row.get("article", {}).get("value", ""),
        "coordinates": 1,
    }
    if existing:
        existing["coordinates"] += 1
        # Prefer a row that has a country code and a name without a parenthetical.
        if not existing.get("country_iso2") and candidate["country_iso2"]:
            existing["country_iso2"] = candidate["country_iso2"]
        for field in ("height_m", "installed_mw", "year_built"):
            if existing.get(field) is None and candidate.get(field) is not None:
                existing[field] = candidate[field]
    else:
        by_qid[qid] = candidate

rows = sorted(by_qid.values(), key=lambda row: (row["country_iso2"], row["name"]))
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"dams={len(rows)} with_country={sum(1 for r in rows if r['country_iso2'])} raw_rows={len(all_rows)}")
print(f"bytes={OUT.stat().st_size}")
