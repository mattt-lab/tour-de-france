#!/usr/bin/env python3
"""One-off: pull each stage's actual local start time from letour.fr's
itinerary tab (the first "kilometers from start" row's scheduled time),
writing data/stage-times.json mapping stage number -> "HH:MM" local time.
Powers the countdown timer on the dashboard. Run manually if the route
changes; not part of the scheduled pipeline (start times are fixed once
published)."""
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

times = {}
for n in stage_numbers:
    r = session.get(f"https://www.letour.fr/en/stage-{n}", timeout=20)
    html = r.text
    idx = html.find('id="itinerary"')
    idx2 = html.find('id="profil"')
    chunk = html[idx:idx2] if idx != -1 and idx2 != -1 else ""
    # First data row after the header = the start line. Grab the first
    # 4 HH:MM-like tokens that follow (caravan, 43/41/39km/h estimates —
    # all equal at km 0, i.e. the actual scheduled start time).
    start_time = None
    tbody_idx = chunk.find('class="tbody"')
    if tbody_idx != -1:
        # Isolate just the first <tr>...</tr> (the km-0 / start row) so we
        # don't accidentally read a later checkpoint's time.
        row_start = chunk.find('<tr', tbody_idx)
        row_end = chunk.find('</tr>', row_start)
        first_row = chunk[row_start:row_end]
        times_found = re.findall(r'(\d{1,2}:\d{2})', first_row)
        if times_found:
            start_time = times_found[-1]  # last cell = scheduled start (caravan cell precedes it)
    if start_time:
        times[str(n)] = start_time
        print(f"stage {n}: {start_time}")
    else:
        print(f"stage {n}: NOT FOUND")
    time.sleep(0.5)

Path("data/stage-times.json").write_text(json.dumps(times, indent=2), encoding="utf-8")
print(f"\nWrote data/stage-times.json with {len(times)} stages")
