"""Build the 250-country world GeoJSON from Natural Earth 50m.

Natural Earth 50m covers 238 of the 250 gazetteer entries. The remaining small
islands become labelled point features at their gazetteer centroid so every
country can still be coloured and clicked.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
GAZETTEER = json.loads((BASE / "hydro" / "data" / "countries.json").read_text(encoding="utf-8"))
NE50 = Path(r"C:\Users\PC\AppData\Local\Temp\ne50.json")
OUT = BASE / "static" / "data" / "countries-world.geojson"

by_name = {row["name"].lower(): row for row in GAZETTEER}
by_official = {row.get("official", "").lower(): row for row in GAZETTEER if row.get("official")}
by_iso2 = {row["iso2"]: row for row in GAZETTEER}


def round_coords(value, digits=3):
    if isinstance(value, list):
        return [round_coords(item, digits) for item in value]
    if isinstance(value, (int, float)):
        return round(value, digits)
    return value


def find_iso2(props):
    for key in ("ISO_A2", "ISO_A2_EH"):
        code = (props.get(key) or "").upper()
        if code and code != "-99" and code in by_iso2:
            return code
    name = (props.get("NAME") or "").lower()
    row = by_name.get(name) or by_official.get(name)
    if row:
        return row["iso2"]
    # A few Natural Earth names differ from the gazetteer.
    aliases = {
        "united states of america": "US",
        "russian federation": "RU",
        "democratic republic of the congo": "CD",
        "republic of the congo": "CG",
        "tanzania": "TZ",
        "vietnam": "VN",
        "laos": "LA",
        "syria": "SY",
        "south korea": "KR",
        "north korea": "KP",
        "czechia": "CZ",
        "czech republic": "CZ",
        "macedonia": "MK",
        "north macedonia": "MK",
        "swaziland": "SZ",
        "eswatini": "SZ",
        "ivory coast": "CI",
        "cote d'ivoire": "CI",
        "myanmar": "MM",
        "burma": "MM",
        "cape verde": "CV",
        "cabo verde": "CV",
        "east timor": "TL",
        "timor-leste": "TL",
        "brunei": "BN",
        "united kingdom": "GB",
        "france": "FR",
        "norway": "NO",
        "kosovo": "XK",
        "somaliland": "SO",
        "western sahara": "EH",
        "taiwan": "TW",
    }
    return aliases.get(name)


ne = json.loads(NE50.read_text(encoding="utf-8"))
features = []
seen = set()
# Polar and sub-Antarctic territories distort the world framing as polygons.
# They are still drawn as point markers from the gazetteer so every profiled
# country is coloured. Antarctica has no profile and is omitted entirely.
SKIP_POLYGON = {"AQ", "TF", "GS", "BV", "HM", "SJ", "UM"}
SKIP_POINT = {"AQ"}
for feature in ne.get("features", []):
    props = feature.get("properties") or {}
    iso2 = find_iso2(props)
    if not iso2 or iso2 in seen or iso2 in SKIP_POLYGON:
        continue
    row = by_iso2[iso2]
    seen.add(iso2)
    features.append(
        {
            "type": "Feature",
            "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": round_coords(feature["geometry"]["coordinates"]),
            },
            "properties": {
                "iso2": iso2,
                "name": row["name"],
                "kind": "polygon",
            },
        }
    )

for iso2, row in by_iso2.items():
    if iso2 in seen or iso2 in SKIP_POINT:
        continue
    features.append(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(row["lon"], 3), round(row["lat"], 3)]},
            "properties": {"iso2": iso2, "name": row["name"], "kind": "point"},
        }
    )

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
print(f"features={len(features)} polygons={sum(1 for f in features if f['properties']['kind']=='polygon')} points={sum(1 for f in features if f['properties']['kind']=='point')}")
print(f"bytes={OUT.stat().st_size}")
