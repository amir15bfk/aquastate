import json
import time
import requests

qids = [f"Q{n}" for n in range(100000, 100050)]
start = time.time()
r = requests.get(
    "https://www.wikidata.org/w/api.php",
    params={
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "labels",
        "languages": "en",
        "languagefallback": "1",
        "format": "json",
    },
    headers={"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus build)"},
    timeout=60,
)
print("status", r.status_code, "bytes", len(r.content), "secs", round(time.time() - start, 2))
if r.status_code == 200:
    data = r.json().get("entities", {})
    print("entities", len(data))
    for qid, entity in list(data.items())[:3]:
        print(qid, entity.get("labels", {}).get("en", {}).get("value"))
else:
    print(r.text[:400])
