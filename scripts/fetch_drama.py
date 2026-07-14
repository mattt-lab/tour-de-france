#!/usr/bin/env python3
"""fetch_drama.py — Generate a short "what to watch for" color-commentary
blurb for the dashboard's Stage Day topper, using current standings +
real cycling news headlines fed to Claude.

Writes data/drama.json:
  { "stage": <n>, "phase": "stage"|"rest"|"between", "generatedAt": iso,
    "text": "..." }

The frontend validates `stage`/`phase` against what it computes locally
before rendering (same stale-guard pattern as the F1/World Cup dashboards'
AI cards) — so a mismatch (e.g. a new stage started since this last ran)
just shows nothing rather than stale commentary.

Regenerates only when the current stage/phase context has changed, or the
existing file is more than STALE_HOURS old — Claude calls cost money and
the "what to watch for" framing doesn't need to change every 30 minutes.
Falls back to a plain headline stitch if ANTHROPIC_API_KEY isn't set.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STALE_HOURS = 4
NEWS_FEED = "https://www.velonews.com/feed/"
MODEL = "claude-haiku-4-5-20251001"

DATA_DIR = Path("data")


def load_json(path):
    try:
        return json.loads((DATA_DIR / path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def current_context():
    route = json.loads((DATA_DIR / "route.json").read_text(encoding="utf-8"))
    standings = load_json("standings.json")
    today = datetime.now(timezone.utc).date().isoformat()
    stages = route["stages"]

    today_stage = next((s for s in stages if s["date"] == today and s["n"] > 0), None)
    rest_today = next((s for s in stages if s["date"] == today and s["type"] == "rest"), None)
    upcoming = sorted((s for s in stages if s["n"] > 0 and s["date"] >= today), key=lambda s: s["n"])
    upcoming = upcoming[0] if upcoming else None

    if today_stage:
        phase, spotlight = "stage", today_stage
    elif rest_today:
        phase, spotlight = "rest", upcoming
    else:
        phase, spotlight = "between", upcoming

    return phase, spotlight, standings


def fetch_headlines(limit=12):
    req = urllib.request.Request(NEWS_FEED, headers={"User-Agent": "TdFDashboard/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        xml = r.read().decode("utf-8", errors="replace")
    titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", xml)
    # Feed/channel metadata repeats the site name ("Velo") as a title;
    # actual articles are longer than that.
    articles = [t.strip() for t in titles if t.strip() and t.strip() != "Velo"]
    return articles[:limit]


def build_prompt(phase, spotlight, standings, headlines):
    lines = []
    if standings:
        gc = standings.get("gc", [])[:5]
        if gc:
            lines.append("Current GC top 5: " + "; ".join(
                f"{r['rider']} ({r['team']}, {r['gap'] if r['gap'] != '-' else 'leader'})" for r in gc
            ))
        for key, label in [("points", "Points/green jersey"), ("mountains", "Mountains/polka dot"), ("youth", "Youth/white jersey")]:
            rows = standings.get(key, [])
            if rows:
                lines.append(f"{label} leader: {rows[0]['rider']} ({rows[0]['team']})")

    if spotlight:
        climbs = spotlight.get("climbs") or []
        climb_desc = "; ".join(f"{c['name']} (Cat {c['category']})" for c in climbs) if climbs else "no categorized climbs"
        lines.append(
            f"{'Today' if phase == 'stage' else 'Next up'}: Stage {spotlight['n']}, "
            f"{spotlight['start']} to {spotlight['finish']}, {spotlight['distanceKm']}km, "
            f"terrain: {spotlight['typeLabel']}. Climbs: {climb_desc}."
        )

    headline_block = "\n".join(f"- {h}" for h in headlines) if headlines else "(no current headlines available)"

    return f"""You are writing a short "what to watch for" blurb for a personal Tour de France 2026 dashboard, read by someone who already knows the standings — don't just restate numbers, add insight.

Context:
{chr(10).join(lines)}

Recent cycling news headlines (use only what's actually relevant, ignore anything unrelated):
{headline_block}

Write 2-4 sentences of color commentary about what's actually at stake — is a GC leader vulnerable on this terrain, is a rival team likely to attack, does a jersey holder need teammates to control a breakaway, are there tactical or physical factors (heat, climb steepness, crosswinds) that matter. Sports-journalist tone: specific, active verbs, no cliches, no generic filler. Do not start with "As the Tour..." or similar throat-clearing. Output only the blurb text, no preamble."""


def main():
    phase, spotlight, standings = current_context()
    stage_n = spotlight["n"] if spotlight else None

    existing = load_json("drama.json")
    if existing and existing.get("stage") == stage_n and existing.get("phase") == phase:
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(existing["generatedAt"])).total_seconds() / 3600
        if age_h < STALE_HOURS:
            print("Drama blurb still fresh for this stage/phase — skipping.")
            return

    try:
        headlines = fetch_headlines()
    except Exception as e:
        print(f"Headline fetch failed: {e}")
        headlines = []

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    text = None

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = build_prompt(phase, spotlight, standings, headlines)
            resp = client.messages.create(
                model=MODEL,
                max_tokens=220,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
        except Exception as e:
            print(f"Claude call failed: {e}")

    if not text and headlines:
        text = "In the news: " + " ".join(headlines[:2]) + "."

    if not text:
        print("No blurb generated (no API key and no headlines) — leaving drama.json untouched.")
        return

    out = {
        "stage": stage_n,
        "phase": phase,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    (DATA_DIR / "drama.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote data/drama.json for stage {stage_n} ({phase})")


if __name__ == "__main__":
    sys.exit(main())
