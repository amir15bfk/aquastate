import json
import time
import requests

HEADERS = {"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus build)"}
ENDPOINT = "https://query.wikidata.org/sparql"

US_PAGE = """
SELECT ?d ?coord ?country WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  ?d wdt:P17 ?country .
  ?country wdt:P297 "US" .
}
ORDER BY ?d
LIMIT 10000 OFFSET 0
"""

NO_COUNTRY_COUNT = """
SELECT (COUNT(?d) AS ?n) WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  FILTER NOT EXISTS { ?d wdt:P17 ?c . }
}
"""

for label, query in (("US 10k", US_PAGE), ("no-country count", NO_COUNTRY_COUNT)):
    start = time.time()
    r = requests.get(ENDPOINT, params={"query": query, "format": "json"}, headers=HEADERS, timeout=240)
    print(label, r.status_code, len(r.content), round(time.time() - start, 1))
    if r.status_code == 200:
        data = r.json()
        rows = data["results"]["bindings"]
        print(" rows", len(rows), "first", rows[0] if rows else None)
    else:
        print(r.text[:500])
