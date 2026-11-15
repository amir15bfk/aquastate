import json
import time
import requests

QUERY = """
SELECT ?iso2 (COUNT(DISTINCT ?d) AS ?n) WHERE {
  ?d wdt:P31/wdt:P279* wd:Q12323 .
  ?d wdt:P625 ?coord .
  ?d wdt:P17 ?country .
  ?country wdt:P297 ?iso2 .
}
GROUP BY ?iso2
ORDER BY DESC(?n)
"""

start = time.time()
r = requests.get(
    "https://query.wikidata.org/sparql",
    params={"query": QUERY, "format": "json"},
    headers={"User-Agent": "AquaStateWorld/2.0 (local demo; full dam corpus build)"},
    timeout=180,
)
print("status", r.status_code, "bytes", len(r.content), "secs", round(time.time() - start, 1))
if r.status_code == 200:
    rows = r.json()["results"]["bindings"]
    data = {row["iso2"]["value"]: int(row["n"]["value"]) for row in rows}
    print("countries", len(data), "dams", sum(data.values()))
    print(json.dumps(dict(list(data.items())[:30]), indent=1))
    open(r"F:\amir\nasa space app\aquastate-world\world\data\dam_counts_by_country.json", "w", encoding="utf-8").write(json.dumps(data, indent=1))
else:
    print(r.text[:1000])
