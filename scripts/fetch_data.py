#!/usr/bin/env python3
"""
fetch_data.py — Fetch 2026 Tour de France classifications and stage results
from the official letour.fr site.

There is no free JSON API for the Tour (ProCyclingStats is Cloudflare-gated),
so this scrapes the same AJAX endpoints letour.fr's own rankings page uses.
Each classification tab loads through a two-hop AJAX chain:

  1. GET /en/rankings/stage-{n}                       -> page embeds a
     data-ajax-stack map of {code: hop1_url} for all 12 codes (6 general,
     6 stage-specific).
  2. GET hop1_url                                       -> wrapper page that
     embeds a second hash-keyed URL ending in /subtab for the same code.
  3. GET hop2_url                                       -> HTML fragment
     containing the actual <table class="rankingTable">.

Classification codes:
  General (cumulative):  itg=GC, ipg=points(green), img=mountains(polka),
                          ijg=youth(white), etg=teams, icg=combativity
  Stage (that day only):  ite, ipe, ime, ije, ete, ice (same order)

Writes:
  data/standings.json        — general classifications for the latest stage
  data/stage-results/{n}.json — stage-specific classifications for stage n

Runs every ~30 min during stage hours via GitHub Actions; a rest day only
needs an occasional refresh since nothing changes.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from selectolax.parser import HTMLParser

BASE = "https://www.letour.fr"
UA = "TdFDashboard/1.0 (+https://github.com/mattt-lab/tour-de-france)"

GENERAL_CODES = {"itg": "gc", "ipg": "points", "img": "mountains", "ijg": "youth", "etg": "teams", "icg": "combativity"}
STAGE_CODES = {"ite": "stage", "ipe": "points", "ime": "mountains", "ije": "youth", "ete": "teams", "ice": "combativity"}

DATA_DIR = Path("data")
STAGE_RESULTS_DIR = DATA_DIR / "stage-results"
STALE_HOURS = 20  # on non-stage days, only refresh once per day

session = requests.Session()
session.headers.update({"User-Agent": UA})


def get(url, **kw):
    r = session.get(url, timeout=20, **kw)
    r.raise_for_status()
    return r.text


def current_stage_number():
    """The default /en/rankings page auto-loads the latest available stage."""
    html = get(f"{BASE}/en/rankings")
    m = re.search(r"Stage (\d+)", html)
    if not m:
        raise RuntimeError("could not detect current stage number from letour.fr")
    return int(m.group(1))


def hop_to_table(stage_html, stage, code):
    # The page embeds one data-ajax-stack block per top-level tab (General /
    # Stage ranking); the code we want may be in either, so scan all blocks.
    m2 = None
    for m in re.finditer(r"data-ajax-stack = \{([^}]*)\}", stage_html):
        m2 = re.search(r"&quot;" + code + r"&quot;:&quot;([^&]*)&quot;", m.group(1))
        if m2:
            break
    if not m2:
        return None
    hop1_url = BASE + m2.group(1).replace("\\/", "/")
    hop1_html = get(hop1_url)
    m3 = re.search(r'data-tabs-ajax="([^"]*' + code + r'[^"]*subtab)"', hop1_html)
    if not m3:
        return None
    hop2_url = BASE + m3.group(1)
    return get(hop2_url)


def parse_ranking_table(html):
    """Some classifications (e.g. stage KOM points) render one mini-table per
    climb rather than a single combined table, so tables are parsed one at a
    time and their rows merged, each tagged with that table's own headers."""
    if not html:
        return []
    tree = HTMLParser(html)
    rows = []
    for table in tree.css("table.rankingTable"):
        headers = [th.text(strip=True).lower().replace(".", "").replace(" ", "_") for th in table.css("thead th")]
        if not headers:
            continue
        for tr in table.css("tbody tr"):
            cells = [td.text(strip=True) for td in tr.css("td")]
            if len(cells) != len(headers):
                continue
            rows.append(dict(zip(headers, cells)))
    return rows


def fetch_classifications(stage, codes):
    stage_html = get(f"{BASE}/en/rankings/stage-{stage}")
    out = {}
    for code, label in codes.items():
        table_html = hop_to_table(stage_html, stage, code)
        out[label] = parse_ranking_table(table_html)
        print(f"  {code} ({label}): {len(out[label])} rows")
    return out


def is_stage_day(route):
    today = datetime.now(timezone.utc).date().isoformat()
    return any(s["date"] == today and s["type"] != "rest" for s in route["stages"])


def should_fetch(route):
    """Always fetch on a stage day. Otherwise (rest day / off day) only
    refresh once every STALE_HOURS, since nothing changes between stages."""
    if is_stage_day(route):
        return True
    try:
        existing = json.loads((DATA_DIR / "standings.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    updated = existing.get("_meta", {}).get("updated")
    if not updated:
        return True
    age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds() / 3600
    return age_h >= STALE_HOURS


def main():
    route = json.loads((DATA_DIR / "route.json").read_text(encoding="utf-8"))
    if not should_fetch(route):
        print("Not a stage day and standings were refreshed recently — skipping.")
        return

    stage = current_stage_number()
    print(f"Latest stage: {stage}")

    print("Fetching general classifications...")
    general = fetch_classifications(stage, GENERAL_CODES)

    print("Fetching stage classifications...")
    stage_specific = fetch_classifications(stage, STAGE_CODES)

    DATA_DIR.mkdir(exist_ok=True)
    STAGE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # letour.fr's general/cumulative classification tables (itg etc.) come
    # back empty while a stage is on the road, even though the underlying
    # GC through the previous stage hasn't changed — a site quirk tied to
    # the live-stage page context, not a real data change. Never let an
    # empty scrape blank out standings we already have; keep the last good
    # values (and the stage number they belong to) until real data for the
    # new stage actually lands.
    try:
        existing_standings = json.loads((DATA_DIR / "standings.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing_standings = {}

    def keep_or_new(key):
        return general[key] if general[key] else existing_standings.get(key, [])

    standings_out = {
        "stage": stage if general["gc"] else existing_standings.get("stage", stage),
        "_meta": {"updated": datetime.now(timezone.utc).isoformat()},
        "gc": keep_or_new("gc"),
        "points": keep_or_new("points"),
        "mountains": keep_or_new("mountains"),
        "youth": keep_or_new("youth"),
        "teams": keep_or_new("teams"),
        "combativity": keep_or_new("combativity"),
    }
    (DATA_DIR / "standings.json").write_text(json.dumps(standings_out, indent=2), encoding="utf-8")

    stage_out = {
        "stage": stage,
        "result": stage_specific["stage"],
        "points": stage_specific["points"],
        "mountains": stage_specific["mountains"],
        "youth": stage_specific["youth"],
        "teams": stage_specific["teams"],
        "combativity": stage_specific["combativity"],
    }
    (STAGE_RESULTS_DIR / f"{stage}.json").write_text(json.dumps(stage_out, indent=2), encoding="utf-8")

    print(f"Wrote data/standings.json and data/stage-results/{stage}.json")


if __name__ == "__main__":
    sys.exit(main())
