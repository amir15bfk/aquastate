import json
from pathlib import Path

BASE = Path(r"F:\amir\nasa space app\aquastate-world")
seed_path = BASE / "world" / "data" / "dam_atlas_full.json"
seed = json.loads(seed_path.read_text(encoding="utf-8"))
fix = {
    "Q990992": "NL",
    "Q13134580": "NL",
    "Q3173415": "NL",
    "Q1264377": "NL",
    "Q3139992": "NL",
    "Q821765": "NL",
    "Q821492": "NL",
    "Q122187133": "NL",
    "Q2467477": "NL",
    "Q104877438": "NL",
    "Q22985475": "CY",
}
for row in seed:
    if row["wikidata_id"] in fix:
        row["country_iso2"] = fix[row["wikidata_id"]]
seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
print("fixed", len(fix), "blank", sum(1 for r in seed if not r["country_iso2"]))
