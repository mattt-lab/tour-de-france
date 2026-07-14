#!/usr/bin/env python3
"""fetch_drama.py — Generate a short "what to watch for" color-commentary
blurb for the dashboard's Stage Day topper, using current standings +
real cycling article content (not just headlines) fed to Claude.

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
Falls back to the single best-matching article's own description if
ANTHROPIC_API_KEY isn't set.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STALE_HOURS = 4
NEWS_FEED = "https://www.velonews.com/feed/"
MODEL = "claude-haiku-4-5-20251001"

DATA_DIR = Path("data")

# Article categories that are almost never useful "what to watch for"
# race-tactics context, even though they're Tour-adjacent — lifestyle,
# gear, and gossip pieces the feed mixes in alongside real race analysis.
CLICKBAIT_PATTERNS = [
    r"\bhotel room\b", r"\bphoto epic\b", r"\bgallery\b", r"\bquiz\b",
    r"\bbuyer'?s guide\b", r"\bshop\b", r"\bdeal(s)?\b", r"\bgear\b",
    r"\bshock (mid-season )?move\b", r"\bpodcast\b", r"\bwatch:\b",
    r"\bwant(s)? just one thing\b",
]
# Terms that mark an article as genuine race-tactics/preview content.
RELEVANT_PATTERNS = [
    r"\bstage \d+\b", r"\bpreview\b", r"\bclimb(s)?\b", r"\bgc\b",
    r"\byellow jersey\b", r"\battack(s|ed|ing)?\b", r"\bbreak\s?away\b",
    r"\bcrash(ed)?\b", r"\bwins?\b", r"\bwon\b", r"\brest day\b",
    r"\bpoints? classification\b", r"\bpolka dot\b", r"\bmountains? classification\b",
]


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


def clean_description(html):
    text = re.sub(r"<figure>.*?</figure>", "", html, flags=re.DOTALL)
    text = re.sub(r"Read the full article at.*", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_articles(limit=25):
    req = urllib.request.Request(NEWS_FEED, headers={"User-Agent": "TdFDashboard/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        xml = r.read().decode("utf-8", errors="replace")

    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    articles = []
    for item in items[:limit]:
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item)
        desc_m = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", item, re.DOTALL)
        link_m = re.search(r"<link>(.*?)</link>", item)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        description = clean_description(desc_m.group(1)) if desc_m else ""
        link = link_m.group(1).strip() if link_m else None
        articles.append({"title": title, "description": description, "link": link})
    return articles


def fetch_article_body(url, max_paragraphs=6, max_chars=1500):
    """RSS <description> is just a one-sentence teaser; the actual article
    page has real paragraphs. Pull the first few for genuine tactical
    detail (climb order, historical context, etc.) instead of a stub."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")

    body_idx = html.find('class="o-rte-text')
    if body_idx == -1:
        return None
    # Stop before the next stage's embedded schedule block, if this page
    # is a multi-stage roundup, so we don't pull in unrelated content.
    end_idx = html.find('id="stage-', body_idx)
    chunk = html[body_idx: end_idx if end_idx != -1 else body_idx + 8000]

    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.DOTALL)
    text_parts = []
    for p in paragraphs[:max_paragraphs]:
        clean = re.sub(r"<[^>]+>", "", p).strip()
        if clean and "ADVERTISEMENT" not in clean:
            text_parts.append(clean)
    text = " ".join(text_parts)
    return text[:max_chars] if text else None


def score_article(a, spotlight_names):
    text = f"{a['title']} {a['description']}".lower()
    if any(re.search(p, text) for p in CLICKBAIT_PATTERNS):
        return -10
    score = sum(2 for p in RELEVANT_PATTERNS if re.search(p, text))
    score += sum(3 for name in spotlight_names if name and name.lower() in text)
    return score


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

    existing = load_json("drama.json")
    if existing and existing.get("stage") == stage_n and existing.get("phase") == phase:
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(existing["generatedAt"])).total_seconds() / 3600
        if age_h < STALE_HOURS:
            print("Drama blurb still fresh for this stage/phase — skipping.")
            return

    try:
        all_articles = fetch_articles()
    except Exception as e:
        print(f"Article fetch failed: {e}")
        all_articles = []

    names = relevant_names(spotlight, standings)
    scored = sorted(all_articles, key=lambda a: score_article(a, names), reverse=True)
    relevant = [a for a in scored if score_article(a, names) > 0][:5]
    print(f"Selected {len(relevant)} relevant articles of {len(all_articles)} fetched:")
    for a in relevant:
        print(f"  - {a['title']}")

    # RSS <description> is just a one-sentence teaser. Fetch the real body
    # text for the top 2 articles so there's actual tactical detail to
    # work with, not just headlines restated as prose.
    for a in relevant[:2]:
        if not a.get("link"):
            continue
        try:
            body = fetch_article_body(a["link"])
            if body:
                a["description"] = body
                print(f"  fetched full body for: {a['title']} ({len(body)} chars)")
        except Exception as e:
            print(f"  body fetch failed for {a['title']}: {e}")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    text = None

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = build_prompt(phase, spotlight, standings, relevant)
            resp = client.messages.create(
                model=MODEL,
                max_tokens=220,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
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
