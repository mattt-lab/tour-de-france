#!/usr/bin/env python3
"""One-off: geocode every stage start/finish town via Nominatim (OSM) and
write data/geo.json mapping town name -> {lat, lon}. Run manually whenever
route.json's town list changes; not part of the scheduled fetch pipeline."""
import json
import time
import urllib.parse
from pathlib import Path

import requests

UA = "TdFDashboard/1.0 (personal project; contact: mattt-lab github)"

# Manual overrides for small towns/ski stations Nominatim resolves poorly
# or ambiguously; query string used instead of the raw town name.
QUERY_OVERRIDES = {
    "Nevers Magny-Cours": "Magny-Cours, France",
    "Le Markstein Fellering": "Le Markstein, France",
    "Plateau de Solaison": "Solaison, Haute-Savoie, France",
    "Gavarnie-Gèdre": "Gavarnie, France",
    "Paris (Champs-Élysées)": "Paris, France",
    "Cantal": "Aurillac, France",
    "Haute-Savoie": "Annecy, France",
}

route = json.loads(Path("data/route.json").read_text(encoding="utf-8"))
towns = set()
for s in route["stages"]:
    if s.get("start"):
        towns.add(s["start"])
    if s.get("finish"):
        towns.add(s["finish"])

session = requests.Session()
session.headers.update({"User-Agent": UA})

geo = {}
existing_path = Path("data/geo.json")
if existing_path.exists():
    geo = json.loads(existing_path.read_text(encoding="utf-8"))

for town in sorted(towns):
    if town in geo:
        continue
    query = QUERY_OVERRIDES.get(town, f"{town}, France")
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    r = session.get(url, timeout=15)
    results = r.json()
    if not results:
        print(f"NO RESULT: {town} ({query})")
        time.sleep(1)
        continue
    geo[town] = {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}
    print(f"{town}: {geo[town]}")
    time.sleep(1)  # Nominatim usage policy: max 1 req/sec

Path("data/geo.json").write_text(json.dumps(geo, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nWrote data/geo.json with {len(geo)} towns")
