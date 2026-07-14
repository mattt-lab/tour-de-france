"""Shared helpers for fetch_drama.py (pre-stage "what to watch for") and
fetch_recap.py (post-stage narrative recap) — article fetching/scoring
and the Claude call wrapper are identical between the two, only the
prompt and relevance keywords differ."""
import json
import re
import urllib.request
from pathlib import Path

NEWS_FEED = "https://www.velonews.com/feed/"
MODEL = "claude-haiku-4-5-20251001"
DATA_DIR = Path("data")

# Article categories that are almost never useful race-tactics/narrative
# context, even though they're Tour-adjacent — lifestyle, gear, and
# gossip pieces the feed mixes in alongside real race analysis.
CLICKBAIT_PATTERNS = [
    r"\bhotel room\b", r"\bphoto epic\b", r"\bgallery\b", r"\bquiz\b",
    r"\bbuyer'?s guide\b", r"\bshop\b", r"\bdeal(s)?\b", r"\bgear\b",
    r"\bshock (mid-season )?move\b", r"\bpodcast\b", r"\bwatch:\b",
    r"\bwant(s)? just one thing\b",
]


def load_json(path):
    try:
        return json.loads((DATA_DIR / path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


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
    page has real paragraphs. Pull the first few for genuine detail
    (climb order, race narrative, etc.) instead of a stub."""
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


def score_article(a, relevant_patterns, names):
    text = f"{a['title']} {a['description']}".lower()
    if any(re.search(p, text) for p in CLICKBAIT_PATTERNS):
        return -10
    score = sum(2 for p in relevant_patterns if re.search(p, text))
    score += sum(3 for name in names if name and name.lower() in text)
    return score


def select_relevant(articles, relevant_patterns, names, limit=5):
    scored = sorted(articles, key=lambda a: score_article(a, relevant_patterns, names), reverse=True)
    return [a for a in scored if score_article(a, relevant_patterns, names) > 0][:limit]


def select_for_stage(articles, stage_n, relevant_patterns, names, limit=5):
    """Both the preview (fetch_drama.py) and recap (fetch_recap.py) blurbs
    are about one specific stage number, but a generic \\bstage \\d+\\b
    relevance match plus rider-name overlap isn't enough to tell "about
    Stage 10" apart from "about Stage 11" when the same riders feature in
    both — confirmed in practice: a Stage 10 recap article outranked the
    real Stage 11 preview article for the Stage 11 blurb purely on name
    overlap. Explicitly boost exact-stage-number mentions and penalize
    mentions of a *different* specific stage."""
    def score(a):
        base = score_article(a, relevant_patterns, names)
        text = f"{a['title']} {a['description']}"
        if re.search(rf"\bstage\s*{stage_n}\b", text, re.IGNORECASE):
            base += 10
        other_stages = set(re.findall(r"\bstage\s*(\d+)\b", text, re.IGNORECASE))
        if other_stages and str(stage_n) not in other_stages:
            base -= 8
        return base

    scored = sorted(articles, key=score, reverse=True)
    return [a for a in scored if score(a) > 0][:limit]


def enrich_with_bodies(articles, count=2):
    """Fetch the real article body for the top N selected articles —
    RSS descriptions are one-sentence teasers, actual pages have detail."""
    for a in articles[:count]:
        if not a.get("link"):
            continue
        try:
            body = fetch_article_body(a["link"])
            if body:
                a["description"] = body
                print(f"  fetched full body for: {a['title']} ({len(body)} chars)")
        except Exception as e:
            print(f"  body fetch failed for {a['title']}: {e}")
    return articles


def call_claude(prompt, api_key, max_tokens=220):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()
