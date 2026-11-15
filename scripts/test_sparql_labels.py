import time
import requests

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus labels)"}
ENDPOINT = "https://query.wikidata.org/sparql"

QUERY = """
SELECT ?d ?coord ?country ?dLabel WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  OPTIONAL { ?d wdt:P17 ?country . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY ?d
LIMIT 2000 OFFSET 0
"""

start = time.time()
r = requests.get(ENDPOINT, params={"query": QUERY, "format": "json"}, headers=HEADERS, timeout=240)
print("status", r.status_code, "bytes", len(r.content), "secs", round(time.time() - start, 1))
if r.status_code == 200:
    rows = r.json()["results"]["bindings"]
    print("rows", len(rows))
    for row in rows[:5]:
        print(row["d"]["value"].rsplit("/", 1)[-1], row.get("dLabel", {}).get("value"))
else:
    print(r.text[:500])
