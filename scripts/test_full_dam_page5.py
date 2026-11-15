import time
import requests

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus build)"}
ENDPOINT = "https://query.wikidata.org/sparql"

PAGE = """
SELECT ?d ?coord ?country WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  OPTIONAL { ?d wdt:P17 ?country . }
}
ORDER BY ?d
LIMIT 2000 OFFSET 50000
"""

for label, query in (("full+country offset 50k", PAGE),):
    start = time.time()
    r = requests.get(ENDPOINT, params={"query": query, "format": "json"}, headers=HEADERS, timeout=180)
    print(label, r.status_code, len(r.content), round(time.time() - start, 1))
    if r.status_code == 200:
        rows = r.json()["results"]["bindings"]
        print(" rows", len(rows), "first", rows[0] if rows else None)
    else:
        print(r.text[:400])
