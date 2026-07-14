#!/usr/bin/env python3
"""fetch_recap.py — Generate a short narrative recap of the most recently
concluded stage ("Pogačar led the entire race but was challenged on the
final climb... kept his head and beat Vingegaard to the line"), shown
alongside the Stage Result card on the dashboard.

Writes data/recap.json:
  { "stage": <n>, "generatedAt": iso, "text": "..." }

Companion to fetch_drama.py (which previews the *next* stage) — same
approach (real article bodies + standings fed to Claude, stale-guard
matched by stage number on the frontend, generate-once/short-circuit),
just pointed at the stage that just finished instead of the one coming
up. Falls back to the single best-matching article's own text if
ANTHROPIC_API_KEY isn't set.
"""
import json
import os
import sys
from datetime import datetime, timezone

from news_utils import DATA_DIR, load_json, fetch_articles, select_for_stage, enrich_with_bodies, call_claude

# Terms that mark an article as genuine stage-result coverage, as opposed
# to general Tour news unrelated to how this specific stage played out.
RELEVANT_PATTERNS = [
    r"\bstage \d+\b", r"\bwins?\b", r"\bwon\b", r"\bwinner\b", r"\bsprint(s|ed|ing)?\b",
    r"\battack(s|ed|ing)?\b", r"\bbreak\s?away\b", r"\bcrash(ed)?\b",
    r"\byellow jersey\b", r"\bresults?\b", r"\bsolo\b", r"\bpeloton\b",
]


def most_recently_concluded():
    """Same "field size >= 20" concluded-stage check the frontend and
    fetch_drama.py both use, applied across every stage so this doesn't
    depend on today's date — a recap can be generated for a stage whose
    result only just landed, whichever day that happens to be."""
    route = load_json("route.json") or {}
    concluded = []
    for s in route["stages"]:
        if s["n"] <= 0:
            continue
        result = load_json(f"stage-results/{s['n']}.json")
        if result and len(result.get("result", [])) >= 20:
            concluded.append((s, result))
    if not concluded:
        return None, None
    concluded.sort(key=lambda pair: pair[0]["n"])
    return concluded[-1]


def relevant_names(stage, result):
    names = [stage.get("start"), stage.get("finish")]
    for r in (result.get("result") or [])[:5]:
        if r.get("rider"):
            names.append(r["rider"].split()[-1])
    return names


def build_prompt(stage, result, standings, articles):
    top5 = (result.get("result") or [])[:5]
    lines = [
        f"Stage {stage['n']}: {stage['start']} to {stage['finish']}, "
        f"{stage['distanceKm']}km, terrain: {stage['typeLabel']}.",
        "Top 5 on the stage: " + "; ".join(
            f"{r['rank']}. {r['rider']} ({r['team']}) "
            f"{r['gap'] if r.get('gap') and r['gap'] != '-' else r.get('times', '')}"
            for r in top5
        ),
    ]
    if standings:
        gc = standings.get("gc", [])[:3]
        if gc:
            lines.append("GC top 3 after this stage: " + "; ".join(
                f"{r['rider']} ({r['gap'] if r['gap'] != '-' else 'leader'})" for r in gc
            ))

    article_block = "\n\n".join(f"- {a['title']}: {a['description']}" for a in articles) if articles else "(no relevant articles available)"

    return f"""You are writing a short recap blurb for a personal Tour de France 2026 dashboard, summarizing a stage that just finished. The reader already sees the top-5 results table right next to this text — don't restate it, capture the drama: how the stage actually played out, who attacked, who cracked, what it means for the GC.

Context:
{chr(10).join(lines)}

Recent cycling articles (title + summary) — use only what's genuinely about this stage's race action, ignore anything about hotels, gear, podcasts, or other lifestyle content even if it slipped through:
{article_block}

Write 2-4 sentences of recap in sports-journalist style: specific, active verbs, no cliches, no generic filler. Do not start with "Stage N..." or restate the numeric results. Output only the blurb text, no preamble."""


def main():
    stage, result = most_recently_concluded()
    if not stage:
        print("No concluded stage yet — nothing to recap.")
        return
    stage_n = stage["n"]

    force = os.environ.get("FORCE_RECAP", "").strip().lower() == "true"
    existing = load_json("recap.json")
    if not force and existing and existing.get("stage") == stage_n:
        print(f"Already have a recap for stage {stage_n} — skipping (no inference cycles spent).")
        return
    elif force:
        print("FORCE_RECAP set — bypassing the already-generated guard.")

    standings = load_json("standings.json")

    try:
        all_articles = fetch_articles()
    except Exception as e:
        print(f"Article fetch failed: {e}")
        all_articles = []

    names = relevant_names(stage, result)
    relevant = select_for_stage(all_articles, stage_n, RELEVANT_PATTERNS, names)
    print(f"Selected {len(relevant)} relevant articles of {len(all_articles)} fetched:")
    for a in relevant:
        print(f"  - {a['title']}")
    relevant = enrich_with_bodies(relevant)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    text = None

    if api_key:
        try:
            text = call_claude(build_prompt(stage, result, standings, relevant), api_key)
        except Exception as e:
            print(f"Claude call failed: {e}")

    if not text and relevant:
        top = relevant[0]
        text = top["description"] or top["title"]

    if not text:
        print("No recap generated (no API key and no relevant articles) — leaving recap.json untouched.")
        return

    out = {
        "stage": stage_n,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    (DATA_DIR / "recap.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote data/recap.json for stage {stage_n}")


if __name__ == "__main__":
    sys.exit(main())
