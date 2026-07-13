#!/usr/bin/env python3
"""One-off: pull the official ASO stage-profile image URL for each stage
from its letour.fr detail page (/en/stage-{n}) and write data/profiles.json
mapping stage number -> image URL. These are the real elevation profile
charts the Tour publishes (silhouette, climb categories, gradients, km
markers) — far better than a hand-built approximation. Run manually
whenever the route changes; not part of the scheduled data pipeline
(the images themselves don't change once published)."""
import json
import re
import time
from pathlib import Path

import requests

UA = "TdFDashboard/1.0 (personal project; contact: mattt-lab github)"
session = requests.Session()
session.headers.update({"User-Agent": UA})

route = json.loads(Path("data/route.json").read_text(encoding="utf-8"))
stage_numbers = sorted({s["n"] for s in route["stages"] if s["n"] > 0})

profiles = {}
for n in stage_numbers:
    r = session.get(f"https://www.letour.fr/en/stage-{n}", timeout=20)
    m = re.search(r'id="profil".*?data-src="([^"]+)"', r.text, re.DOTALL)
    if m:
        profiles[str(n)] = m.group(1)
        print(f"stage {n}: OK")
    else:
        print(f"stage {n}: NOT FOUND")
    time.sleep(0.5)

Path("data/profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")
print(f"\nWrote data/profiles.json with {len(profiles)} stages")
