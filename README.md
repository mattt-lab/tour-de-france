# 🚴 Tour de France 2026

> A live Tour de France companion — stage storylines, the four jerseys, and the road ahead, all in one dark-mode dashboard.

**Live site:** https://mattt-lab.github.io/tour-de-france/tdf-dashboard.html

> **STATUS: FROZEN — 2026 Tour complete.**
> The site displays the final race result (Stage 21, Paris, 2026-07-26) and remains fully browsable. The data pipeline cron is disabled. See [Reactivating for 2027](#reactivating-for-2027) to bring it back to life.

---

## What it does

The dashboard detects where you are in the 21-stage race and shows what's relevant right now:

- **Countdown timer** to the next stage's actual start time (real local start times, not just dates) — always targets whichever stage hasn't started yet, so it points at today's stage before the flag drops and rolls to tomorrow's once it has.
- **Live in-race tracker** — once a stage is actually rolling: km-to-go, the peloton/breakaway/groupetto split with real gaps and speeds on a zoomed group-position bar, and the current jersey holders marked wherever they're actually riding (not assumed to all be in the pack). Updates every 10s. See [Live in-race tracker](#live-in-race-tracker) below.
- **"What to watch for"** — a short AI-written blurb on the countdown card covering the tactical stakes for the *next* stage: is the GC leader vulnerable on this terrain, does a jersey holder need teammates to chase a break. Sourced from current standings + real cycling article content (Velonews) fed to Claude.
- **"What happened"** — the same treatment for the stage that just finished, shown inside its result card: how the stage actually played out, the key moment, who won and how — not just a list of finishing times.
- **Rest day?** Yesterday's stage result, current jersey holders, and tomorrow's stage preview with climbs and storyline.
- **Stage day?** Today's route, terrain, categorized climbs, and official elevation profile, plus the most recent finished stage's result.
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

**No runtime server** for any of the above — all pages are static HTML/CSS/JS; data is fetched client-side from committed JSON at load time. `scripts/fetch_data.py` ran on a schedule via GitHub Actions and committed its output back to the repo during the race; that cron is now disabled (see the FROZEN notice above). (The live tracker below was the one exception — see why.)

---

## Live in-race tracker

The 10-minute Actions cron above is fine for standings and results, but far too slow for "live." Instead, the live tracker's data comes straight from the browser, sourced from **ASO's own live telemetry API** (`racecenter.letour.fr/api/telemetryCompetitor-{year}`) — the same publisher as the rest of this site's scrape, just a different, undocumented endpoint. While a stage is on the road it returns `RaceStatus: true` and a `Riders[]` array with each rider's bib, distance-to-finish, speed, road gradient, and local weather. There's no lat/lon — rider position is relative (km to finish), so the dashboard derives groups itself by clustering riders whose distance-to-finish is within 0.15km of each other, the same technique used by a couple of other open-source Tour trackers whose source I read while building this.

That endpoint has no CORS headers, so a browser `fetch()` from GitHub Pages is blocked outright. Getting genuinely live (~10s) updates instead of routing through the slow Actions pipeline means something has to add CORS — that's `cloudflare/tdf-telemetry-proxy.js`, a small Worker that just relays any path under the ASO API with `Access-Control-Allow-Origin: *` added. It requires **no API key** (the ASO endpoint itself needs no auth, and neither does the relay) — just a one-time manual deploy to a free Cloudflare account; see the comment block at the top of that file for the exact steps. Once deployed, paste the resulting `*.workers.dev` URL into the `TDF_PROXY` constant near the top of `tdf-dashboard.html`'s script.

Because the real feed is empty except during an actual live stage, `tdf-dashboard.html?mockLive=1` forces the tracker on with realistic fixture data (`mockTelemetry()`/`mockRoster()` in the script) so the rendering, clustering, and zoom-window logic can be tested any day, not just on race days.

Jersey holders (`YGPW` in the feed) are marked with the same colored dot used on the Standings page, both inline next to their name and as a tick above their group's marker on the bar — and are guaranteed a visible slot in their group's rider list rather than getting lost behind a "+114" truncation. Hovering a group's row highlights its marker on the bar and vice versa. Each row also shows a bubble sized by rider count (deliberately monochrome gray, not gold/green/red/white — those colors already mean "jersey," so the bubble doesn't compete with them for the same visual language), and clicking a row expands it to the group's full rider list instead of just the truncated summary.

The group-position bar is a proportional zoom, not the full stage: the groups occupy the middle 70% of the bar (15% padding each side) so a few km of real gap reads as visible space instead of collapsing on a 150+ km axis. An earlier version paired this with a small full-stage minimap above the bar to show where the crop sat, but in practice the minimap itself read as an unexplained box rather than a clear "you are here" — a plain caption ("Zoomed to km 101–111 of the 161 km stage") said the same thing more legibly, so that's what shipped instead.

Not yet built: the event ticker (breakaway formed, jersey changes, crashes) sourced from Bluesky/journalist chatter — deliberately deferred; see Possible follow-ups.

**Time trials (ITT/TTT) are excluded on purpose.** The group/gap/zoom logic assumes a mass-start field with a peloton, a breakaway, and a groupetto — none of that exists on a time trial, where riders start solo at intervals. Rather than mislabel whichever pair of riders happens to be closest together as "Peloton," or show a road-distance-based gap estimate that doesn't mean what it looks like it means, the tracker is skipped entirely on `itt`/`ttt` stage days. The card falls back to a plain status line that calls out the time-trial format explicitly (e.g. "Individual Time Trial underway — riders set off solo at intervals...") rather than the generic "Stage N is underway" text. A dedicated time-trial view (per-rider provisional gap to the current best time) would be a separate feature, not a variation of this one.

---

## Data pipeline

```
GitHub Actions cron (every 10 min during the race; DISABLED post-race)
    ├─ scripts/fetch_data.py
    │     ├─ skips entirely on non-stage days if standings were
    │     │  refreshed within the last 20h (rest days / off days)
    │     ├─ GET letour.fr classifications (general + stage)  → data/standings.json
    │     │  (never lets an empty live-stage scrape overwrite data
    │     │  already on file — see Data freshness below)
    │     └─ GET letour.fr stage result                        → data/stage-results/<n>.json
    │
    ├─ scripts/fetch_drama.py       ("what to watch for" — the NEXT stage)
    │     ├─ generates once per stage, then short-circuits on every
    │     │  later run until the spotlighted stage changes — no
    │     │  timer-based re-roll, no wasted Claude calls
    │     ├─ GET Velonews RSS + full article bodies for the
    │     │  best-matching current headlines
    │     ├─ Claude (Haiku) writes 2-4 sentences from standings +
    │     │  articles → data/drama.json
    │     └─ falls back to the best-matching article's own text if
    │        ANTHROPIC_API_KEY isn't set
    │
    └─ scripts/fetch_recap.py       ("what happened" — the LAST stage)
          ├─ same approach, pointed at whichever stage most recently
          │  concluded (result field size >= 20) instead of the one
          │  coming up; generates once per concluded stage
          └─ writes data/recap.json, shown inside the Stage Result card

GitHub Pages serves data/*.json same-origin → no CORS issues
Dashboard re-fetches everything and re-renders every 60s client-side
```

Both blurbs key strictly on stage *number* (not phase) when the dashboard decides whether to render them — the same upcoming stage can be labeled 'between'/'rest' one day and 'stage' the next without needing new commentary, so requiring both fields to match was hiding valid blurbs right at that day-rollover instant. Article relevance scoring (`scripts/news_utils.py`, shared by both scripts) also explicitly boosts exact stage-number mentions and penalizes mentions of a *different* specific stage — a generic keyword match plus rider-name overlap isn't enough to tell a Stage 10 article apart from a Stage 11 one when the same riders feature in both.

---

## Data freshness

| Data | Source | Freshness |
|---|---|---|
| Route, climbs, stage storylines | Hand-curated from official ASO stage profiles (`data/route.json`) | Fixed for the season |
| Stage start times | letour.fr itinerary tab (`data/stage-times.json`) | Fixed for the season |
| GC / Points / Mountains / Youth / Teams | letour.fr | Refetched every 10 min on stage days, ~daily otherwise |
| Stage results | letour.fr | Same as above |
| "What to watch for" blurb (next stage) | Claude + Velonews RSS (`data/drama.json`) | Generated once per stage, not on a timer |
| "What happened" recap (last stage) | Claude + Velonews RSS (`data/recap.json`) | Generated once per concluded stage, not on a timer |
| Live tracker (groups, gaps, jerseys, weather) | ASO telemetry API, via the Cloudflare Worker relay | Polled client-side every 10s, only while a stage is actually live |
| Dashboard page itself | Client-side fetch | Re-fetches and re-renders every 60s while the tab is open |

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

## Setup (for a future Tour)

1. Push this repo to GitHub.
2. Enable GitHub Pages (Settings → Pages → Deploy from branch: `main`, root `/`).
3. Add an `ANTHROPIC_API_KEY` repo secret (Settings → Secrets and variables → Actions) if you want the AI-written "what to watch for" blurb — without it, `fetch_drama.py` still runs and falls back to a plain headline stitch.
4. Deploy `cloudflare/tdf-telemetry-proxy.js` to a free Cloudflare Workers account (see the comment block at the top of that file) and paste the resulting URL into the `TDF_PROXY` constant in `tdf-dashboard.html` — needed only for the live in-race tracker; everything else works without it.
5. Follow the reactivation steps below, then trigger the `Update Tour de France Data` workflow manually once to seed the JSON files.

Since each blurb only generates once per stage, to force a fresh one on demand rather than deleting the JSON by hand: Actions tab → **Update Tour de France Data** → **Run workflow** → check **force_drama** (next-stage preview) and/or **force_recap** (last-stage recap).

---

## Tech stack

| Layer | Choice |
|---|---|
| Hosting | GitHub Pages (static) |
| Data pipeline | GitHub Actions + Python (`requests`, `selectolax`, `anthropic`) |
| Frontend | Vanilla HTML/CSS/JS — no framework, no bundler |
| Data source | letour.fr (official site, scraped) + ASO live telemetry API (live tracker) |
| Preview + recap blurbs | Claude Haiku + Velonews RSS |
| Live tracker relay | Cloudflare Worker (CORS relay only, no logic) |

---

## Possible follow-ups

- Abandon/DNF tracking for the team & rider status view.
- Event ticker on the live tracker (breakaway formed, jersey changes, crashes) sourced from Bluesky/journalist chatter — deliberately deferred out of the initial live-tracker build.

---

## Reactivating for 2027

The following changes were made on **2026-07-28** to freeze the project. Reverse/redo them when setting up for the next Tour.

### 1. Re-enable the cron (`.github/workflows/update-data.yml`)

```yaml
# Change this:
on:
  # FROZEN 2026-07-28: cron disabled — Tour complete (Stage 21, Paris, 2026-07-26).
  # To reactivate for 2027, uncomment the schedule block below.
  # schedule:
  #   - cron: '*/10 * * * *'
  workflow_dispatch:

# Back to this:
on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 min all day; script exits early on non-stage days
  workflow_dispatch:
```

### 2. Rebuild the season's route data

Unlike the standings/results (scraped live), the route itself has no automated source and is entirely specific to the 2026 route:

- `data/route.json` — hand-curated stage-by-stage route, climbs, and storylines. Rewrite by hand from the official 2027 route announcement, following the existing field structure (`n`, `date`, `start`, `finish`, `distanceKm`, `type`, `climbs[]`, `storyline`).
- `data/stage-times.json` — real per-stage local start times. Re-run `scripts/fetch_stage_times.py` once the 2027 itinerary is published on letour.fr.
- `data/profiles.json` — official elevation profile image URLs per stage. Re-run `scripts/fetch_stage_profiles.py`.
- `data/geo.json` — town → lat/lon geocoding, a one-off input used while building the route map. Re-run `scripts/geocode_stages.py` if needed.
- `assets/route-map.jpg` + `data/route-map-paths.json` — the official ASO route poster and its per-stage bounding boxes are entirely specific to the published route graphic; both need retracing against the new poster once ASO publishes it (this was originally done stage-by-stage by comparing the poster image against each stage's start/finish cities).

### 3. Bump `TDF_YEAR` in `tdf-dashboard.html`

The live in-race tracker's Cloudflare Worker calls (`telemetryCompetitor-${TDF_YEAR}`, `allCompetitors-${TDF_YEAR}`, `team-${TDF_YEAR}`) are the only places the year is parameterized in code — change the `const TDF_YEAR = 2026;` line near the top of the script. `cloudflare/tdf-telemetry-proxy.js` itself needs **no changes** — it's a generic path-forwarder, not year-specific.

### 4. Review `TEAM_COLORS` in `tdf-standings.html`

Team rosters and sponsors can change between seasons — check the 23-team color map against the new season's WorldTour team list and update any renamed, new, or dropped teams.

### 5. Clear stale data files

```
data/standings.json
data/drama.json
data/recap.json
data/stage-results/   (all files)
```

(`route.json`, `stage-times.json`, `profiles.json`, `geo.json`, and `route-map-paths.json` get *replaced* per step 2 above, not just cleared.)

### 6. Version numbers and analytics (optional)

Each page carries its own version footer — bump it if you want a visible marker for the new season. The GA4 property (`G-9K08FK3SWH`) is intentionally shared across this project and its sibling F1/World Cup dashboards — no change needed unless you want separate analytics for this one.

---

*Built for personal use. Not affiliated with the Tour de France, ASO, or letour.fr.*
