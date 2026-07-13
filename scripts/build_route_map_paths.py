#!/usr/bin/env python3
"""One-off: bake the manually vision-traced route-line waypoints (read off
assets/route-map.jpg, the official ASO overall-route poster, by cropping
and grid-overlaying each region) into percentage-of-image coordinates.

Percentages (not raw pixels) so the frontend overlay lines up correctly
regardless of the image's rendered display size. Run manually if the
route map image or route ever changes; not part of the scheduled pipeline.
"""
import json
from pathlib import Path

IMG_W, IMG_H = 1600, 1957

# Waypoints traced directly from the map image (pixel space, 1600x1957),
# one polyline per stage's actual drawn route curve.
STAGE_PATHS_PX = {
    1: [(830,1500),(845,1515),(830,1508)],
    2: [(695,1558),(735,1538),(770,1522),(838,1508)],
    3: [(895,1462),(910,1430),(875,1395),(840,1375),(818,1340)],
    4: [(795,1235),(850,1260),(810,1280),(760,1285),(695,1265)],
    5: [(655,1195),(620,1200),(590,1215),(555,1220),(525,1210)],
    6: [(525,1210),(545,1240),(565,1265),(555,1290),(540,1300)],
    7: [(525,1190),(530,1150),(525,1110),(530,1070),(525,1035),(520,1010)],
    8: [(655,975),(635,990),(620,1010)],
    9: [(720,940),(755,955),(760,985),(785,965),(800,935),(815,905),(835,890)],
    10: [(825,1010),(860,990),(900,975),(915,955),(890,940),(860,950)],
    11: [(890,890),(885,850),(875,800),(870,750),(855,715),(835,690)],
    12: [(860,700),(900,715),(950,725),(1000,730),(1050,725),(1090,715),(1105,700)],
    13: [(1140,690),(1180,660),(1220,625),(1260,595),(1290,575),(1310,560)],
    14: [(1355,545),(1320,510),(1285,495),(1290,530),(1315,530)],
    15: [(1205,720),(1195,760),(1180,790),(1160,810),(1170,850),(1190,870),(1210,880)],
    16: [(1250,715),(1225,720)],
    17: [(1195,905),(1150,935),(1130,955)],
    18: [(1130,955),(1120,1000),(1130,1040),(1160,1075),(1200,1090),(1290,1055)],
    19: [(1175,1080),(1155,1040),(1150,1000),(1170,965),(1195,975),(1215,975)],
    20: [(1245,1010),(1230,995),(1215,980),(1215,975)],
    21: [(755,415),(790,430),(820,415),(840,400),(855,390)],
}

out = {
    "imageWidth": IMG_W,
    "imageHeight": IMG_H,
    "stages": {
        str(n): [[round(x / IMG_W * 100, 3), round(y / IMG_H * 100, 3)] for x, y in pts]
        for n, pts in STAGE_PATHS_PX.items()
    },
}

Path("data/route-map-paths.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"Wrote data/route-map-paths.json with {len(out['stages'])} stage paths")
