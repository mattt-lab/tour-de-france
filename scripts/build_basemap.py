#!/usr/bin/env python3
"""One-off: build a lightweight France/Spain outline for the route map
background, pre-projected into the same fixed pixel frame the dashboard
and route page's JS uses (see MAP_BOUNDS in tdf-dashboard.html /
tdf-route.html) so the basemap and stage dots line up exactly.

Source: johan/world.geo.json (public domain, Natural-Earth-derived, very
low resolution — ~50 points per country, ideal for a stylized background).
Run manually; not part of the scheduled data pipeline.
"""
import json
from pathlib import Path

import requests

# Must match MAP_BOUNDS / MAP_W / MAP_H constants in the frontend JS exactly.
LON_MIN, LON_MAX = -1.0, 7.8
LAT_MIN, LAT_MAX = 40.7, 49.3
W, H = 520, 508

SOURCES = {
    "france": "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/FRA.geo.json",
    "spain": "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/ESP.geo.json",
}


def proj(lon, lat):
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * W
    y = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * H
    return x, y


def ring_in_bounds(ring):
    """Keep rings whose bounding box overlaps our fixed frame at all, so
    disjoint landmasses (Corsica, Balearics, ...) are dropped even though
    most of a kept country's own points may fall outside the frame (e.g.
    only Catalonia's sliver of Spain is actually visible)."""
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return not (max(lons) < LON_MIN or min(lons) > LON_MAX or max(lats) < LAT_MIN or min(lats) > LAT_MAX)


def ring_to_path(ring):
    pts = [proj(lon, lat) for lon, lat in ring]
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} "
    d += " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts[1:])
    d += " Z"
    return d


def main():
    out = {}
    for name, url in SOURCES.items():
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        geom = r.json()["features"][0]["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        paths = []
        for poly in polys:
            ring = poly[0]  # exterior ring only; these low-res shapes have no holes
            if ring_in_bounds(ring):
                paths.append(ring_to_path(ring))
        out[name] = " ".join(paths)
        print(f"{name}: kept {len(paths)} ring(s)")

    Path("data/basemap.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Wrote data/basemap.json")


if __name__ == "__main__":
    main()
