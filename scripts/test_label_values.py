import json
import time
import requests
from pathlib import Path

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; label batch)"}
ENDPOINT = "https://query.wikidata.org/sparql"
raw = json.loads(Path(r"F:\amir\nasa space app\aquastate-world\world\data\dams_full_raw\page_000000.json").read_text(encoding="utf-8"))
qids = [row["d"]["value"].rsplit("/", 1)[-1] for row in raw["results"]["bindings"]]
values = " ".join(f"wd:{qid}" for qid in qids)
query = "SELECT ?d ?dLabel WHERE { VALUES ?d { " + values + " } SERVICE wikibase:label { bd:serviceParam wikibase:language \"en\". } }"
start = time.time()
r = requests.post(ENDPOINT, data={"query": query, "format": "json"}, headers=HEADERS, timeout=240)
print("qids", len(qids), "status", r.status_code, "bytes", len(r.content), "secs", round(time.time() - start, 1))
if r.status_code == 200:
    rows = r.json()["results"]["bindings"]
    print("rows", len(rows))
    for row in rows[:5]:
        print(row["d"]["value"].rsplit("/", 1)[-1], row.get("dLabel", {}).get("value"))
else:
    print(r.text[:500])
