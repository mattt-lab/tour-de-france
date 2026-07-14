#!/usr/bin/env python3
"""fetch_drama.py — Generate a short "what to watch for" color-commentary
blurb for the dashboard's Stage Day topper, using current standings +
real cycling article content (not just headlines) fed to Claude.

Writes data/drama.json:
  { "stage": <n>, "phase": "stage"|"rest"|"between", "generatedAt": iso,
    "text": "..." }

The frontend validates `drama.stage` against the stage it's currently
spotlighting before rendering (same stale-guard pattern as the F1/World
Cup dashboards' AI cards) — so a mismatch (a new stage started since this
last ran) just shows nothing rather than stale commentary. `phase` is
informational only; matching is by stage number so the same upcoming
stage doesn't need new commentary just because its phase label changed
(e.g. 'between' the evening before -> 'stage' once its own day arrives).

Generates exactly once per stage, then short-circuits on every later run
(the workflow polls every 10 min) until the spotlighted stage changes —
Claude calls cost money and the framing doesn't need to change mid-wait.
Pass FORCE_DRAMA=true (the workflow's force_drama input does this) to
bypass and regenerate anyway. Falls back to the single best-matching
article's own description if ANTHROPIC_API_KEY isn't set.
"""
import json
import os
import sys
from datetime import datetime, timezone

from news_utils import DATA_DIR, load_json, fetch_articles, select_for_stage, enrich_with_bodies, call_claude

# Terms that mark an article as genuine race-tactics/preview content.
RELEVANT_PATTERNS = [
    r"\bstage \d+\b", r"\bpreview\b", r"\bclimb(s)?\b", r"\bgc\b",
    r"\byellow jersey\b", r"\battack(s|ed|ing)?\b", r"\bbreak\s?away\b",
    r"\bcrash(ed)?\b", r"\bwins?\b", r"\bwon\b", r"\brest day\b",
    r"\bpoints? classification\b", r"\bpolka dot\b", r"\bmountains? classification\b",
]


def current_context():
    route = load_json("route.json") or {}
    standings = load_json("standings.json")
    today = datetime.now(timezone.utc).date().isoformat()
    stages = route["stages"]

    today_stage = next((s for s in stages if s["date"] == today and s["n"] > 0), None)
    rest_today = next((s for s in stages if s["date"] == today and s["type"] == "rest"), None)
    # Strictly *after* today, not >= — otherwise once today's own stage has
    # concluded, this re-selects that same (now-finished) stage as "upcoming"
    # and the blurb previews a race that already happened.
    upcoming = sorted((s for s in stages if s["n"] > 0 and s["date"] > today), key=lambda s: s["n"])
    upcoming = upcoming[0] if upcoming else None

    # letour.fr's finish-classification table is empty while a stage is
    # still on the road and jumps straight to the full field once it
    # closes, so field size is a reliable "has this stage concluded" —
    # matches the frontend's identical check so stage/phase always agree.
    today_result = load_json(f"stage-results/{today_stage['n']}.json") if today_stage else None
    today_concluded = bool(today_result and len(today_result.get("result", [])) >= 20)

    if today_stage and not today_concluded:
        phase, spotlight = "stage", today_stage  # covers both pre-start and live
    elif rest_today:
        phase, spotlight = "rest", upcoming
    else:
        phase, spotlight = "between", upcoming  # no stage today, or today's already concluded

    return phase, spotlight, standings


def relevant_names(spotlight, standings):
    names = []
    if spotlight:
        names += [spotlight.get("start"), spotlight.get("finish")]
    if standings:
        for key in ("gc", "points", "mountains", "youth"):
            rows = standings.get(key, [])[:3]
            names += [r["rider"].split()[-1] for r in rows if r.get("rider")]
    return names


def build_prompt(phase, spotlight, standings, articles):
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

    if articles:
        article_block = "\n\n".join(f"- {a['title']}: {a['description']}" for a in articles)
    else:
        article_block = "(no relevant articles available)"

    return f"""You are writing a short "what to watch for" blurb for a personal Tour de France 2026 dashboard, read by someone who already knows the standings — don't just restate numbers, add insight.

Context:
{chr(10).join(lines)}

Recent cycling articles (title + summary) — use only what's genuinely relevant to today's race tactics or storylines, ignore anything about hotels, gear, podcasts, or other lifestyle content even if it slipped through:
{article_block}

Write 2-4 sentences of color commentary about what's actually at stake — is a GC leader vulnerable on this terrain, is a rival team likely to attack, does a jersey holder need teammates to control a breakaway, are there tactical or physical factors (heat, climb steepness, crosswinds) that matter. Sports-journalist tone: specific, active verbs, no cliches, no generic filler. Do not start with "As the Tour..." or similar throat-clearing. Output only the blurb text, no preamble."""


def main():
    phase, spotlight, standings = current_context()
    stage_n = spotlight["n"] if spotlight else None

    # Keyed on stage number only, not phase: the same upcoming stage can be
    # labeled 'between'/'rest' and then 'stage' as its own day arrives
    # without needing new commentary — matching both fields would burn an
    # extra Claude call right at that day-rollover instant for nothing.
    force = os.environ.get("FORCE_DRAMA", "").strip().lower() == "true"
    existing = load_json("drama.json")
    if not force and existing and existing.get("stage") == stage_n:
        print("Already have a blurb for this stage — skipping (no inference cycles spent).")
        return
    elif force:
        print("FORCE_DRAMA set — bypassing the already-generated guard.")

    try:
        all_articles = fetch_articles()
    except Exception as e:
        print(f"Article fetch failed: {e}")
        all_articles = []

    names = relevant_names(spotlight, standings)
    relevant = select_for_stage(all_articles, stage_n, RELEVANT_PATTERNS, names)
    print(f"Selected {len(relevant)} relevant articles of {len(all_articles)} fetched:")
    for a in relevant:
        print(f"  - {a['title']}")
    relevant = enrich_with_bodies(relevant)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    text = None

    if api_key:
        try:
            text = call_claude(build_prompt(phase, spotlight, standings, relevant), api_key)
        except Exception as e:
            print(f"Claude call failed: {e}")

    if not text and relevant:
        # No API key: use the single best-matching article's own summary
        # rather than stitching headlines together.
        top = relevant[0]
        text = top["description"] or top["title"]

    if not text:
        print("No blurb generated (no API key and no relevant articles) — leaving drama.json untouched.")
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
