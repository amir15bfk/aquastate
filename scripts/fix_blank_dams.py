import json
import math
from pathlib import Path

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
seed_path = BASE / "world" / "data" / "dam_atlas_full.json"
seed = json.loads(seed_path.read_text(encoding="utf-8"))
gaz = json.loads((BASE / "hydro" / "data" / "countries.json").read_text(encoding="utf-8"))


def distance(lat1, lon1, lat2, lon2):
    dlat = lat1 - lat2
    dlon = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlon * dlon)


for row in seed:
    if row["country_iso2"]:
        continue
    best = min(
        gaz,
        key=lambda c: distance(row["lat"], row["lon"], float(c.get("lat") or 0), float(c.get("lon") or 0)),
    )
    row["country_iso2"] = best["iso2"]
    print(row["wikidata_id"], row["name"], "->", best["iso2"], best["name"])

seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
print("updated", sum(1 for row in seed if row["country_iso2"]), "/", len(seed))
