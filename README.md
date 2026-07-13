# 🚴 Tour de France 2026

> A live Tour de France companion — stage storylines, the four jerseys, and the road ahead, all in one dark-mode dashboard.

---

## What it does

The dashboard detects where you are in the 21-stage race and shows what's relevant right now:

- **Rest day?** Yesterday's stage result, current jersey holders, and tomorrow's stage preview with climbs and storyline.
- **Stage day?** Today's route, terrain, and categorized climbs, plus the most recent finished stage's result.
- **Between the Tour?** A countdown to the Grand Départ, or a wrap once the Tour is over.

---

## Pages

| File | Description |
|---|---|
| `tdf-dashboard.html` | Main hub — phase-aware: rest day, stage day, between stages, countdown, or complete |
| `tdf-route.html` | All 21 stages — terrain, distance, categorized climbs, filterable by stage type |
| `tdf-standings.html` | GC (yellow), Points (green), Mountains (polka dot), Youth (white), and Team classifications |

---

## Data source

There's no free JSON API for the Tour — [ProCyclingStats](https://www.procyclingstats.com/) sits behind a Cloudflare bot challenge and returns a "Just a moment…" interstitial to plain scrapers. Instead, `scripts/fetch_data.py` pulls from **letour.fr**, the official Tour site, which is not Cloudflare-gated.

The classification tabs on letour.fr load through a two-hop AJAX chain (the same requests a browser makes when you click a jersey tab):

```
GET /en/rankings/stage-{n}
    → page embeds a data-ajax-stack map: {code: hop1_url} for 12 codes
      (6 cumulative "general" + 6 "stage"-specific)

GET hop1_url
    → wrapper page embeds a second hash-keyed URL ending in /subtab

GET hop2_url
    → HTML fragment containing the actual <table class="rankingTable">
```

| Code | Classification | Code | Classification |
|---|---|---|---|
| `itg` / `ite` | General (GC) | `ijg` / `ije` | Youth (white) |
| `ipg` / `ipe` | Points (green) | `etg` / `ete` | Teams |
| `img` / `ime` | Mountains (polka dot) | `icg` / `ice` | Combativity |

`g` = cumulative/general classification, `e` = that stage only.

Route, climbs, and stage storylines (`data/route.json`) are hand-curated — the full 21-stage route is published before the race starts and doesn't change, so it's committed as static data rather than scraped.

**No runtime server.** All pages are static HTML/CSS/JS; data is fetched client-side from committed JSON at load time. `scripts/fetch_data.py` runs on a schedule via GitHub Actions and commits its output back to the repo.

---

## Data pipeline

```
GitHub Actions (every 30 min)
    └─ scripts/fetch_data.py
          ├─ skips entirely on non-stage days if standings were
          │  refreshed within the last 20h (rest days / off days)
          ├─ GET letour.fr classifications (general + stage)  → data/standings.json
          └─ GET letour.fr stage result                        → data/stage-results/<n>.json

GitHub Pages serves data/*.json same-origin → no CORS issues
```

---

## Data freshness

| Data | Source | Freshness |
|---|---|---|
| Route, climbs, stage storylines | Hand-curated (`data/route.json`) | Fixed for the season |
| GC / Points / Mountains / Youth / Teams | letour.fr | Refetched every 30 min on stage days, ~daily otherwise |
| Stage results | letour.fr | Same as above |

---

## Running locally

Pages fetch JSON at runtime, so they need to be served over HTTP (not opened as `file://`):

```bash
npx serve .
# or
python -m http.server 8080
```

Then open `http://localhost:8080/tdf-dashboard.html`.

To seed/refresh data manually:

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_data.py
```

---

## Setup (GitHub Pages)

1. Push this repo to GitHub.
2. Enable GitHub Pages (Settings → Pages → Deploy from branch: `main`, root `/`).
3. Trigger the `Update Tour de France Data` workflow manually once to seed the JSON files (or just wait for the next scheduled run).

---

## Tech stack

| Layer | Choice |
|---|---|
| Hosting | GitHub Pages (static) |
| Data pipeline | GitHub Actions + Python (`requests`, `selectolax`) |
| Frontend | Vanilla HTML/CSS/JS — no framework, no bundler |
| Data source | letour.fr (official site, scraped) |

---

## Possible follow-ups

- AI-written stage preview/wrap card (Claude Haiku) with a stale-guard so it never shows the wrong stage.
- Abandon/DNF tracking for the team & rider status view.
- Live in-stage gap/breakaway status while a stage is on the road.

---

*Built for personal use. Not affiliated with the Tour de France, ASO, or letour.fr.*
