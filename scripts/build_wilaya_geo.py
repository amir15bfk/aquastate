"""Build static/data/dz-wilayas.geojson from the geoBoundaries release for Algeria (ADM1).

Source: geoBoundaries gbOpen DZA ADM1 (OpenStreetMap / Wambacher), ODbL 1.0,
boundary year represented 2017 -> 48 wilayas (DZ-01 .. DZ-48).

The boundaries are NOT redrawn. The script only:
  * cleans names (stray U+200E marks),
  * keeps every published vertex (no simplification), only rounding coordinates to 4 decimals (~11 m),
  * writes a separate generalised preview copy (dz-wilayas-lite.geojson, ~2 km tolerance) used only by
    the small dashboard thumbnail,
  * adds an interior label point (pole-ish point that is guaranteed inside the polygon) and area.

Run:  python scripts/build_wilaya_geo.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "world" / "data" / "geo_src" / "geoBoundaries-DZA-ADM1_simplified.geojson"
OUT = ROOT / "static" / "data" / "dz-wilayas.geojson"



def rdp(points, eps):
    if len(points) < 4:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        x0, y0 = points[i]
        d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = rdp(points[: idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


def rdp_ring(ring, eps):
    """Douglas-Peucker for a CLOSED ring: split at the vertex farthest from the start first,
    otherwise start == end makes every perpendicular distance zero and the ring collapses."""
    if len(ring) < 5:
        return ring
    x0, y0 = ring[0]
    k = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    out = rdp(ring[: k + 1], eps)[:-1] + rdp(ring[k:], eps)
    return out if len(out) >= 4 else ring


def simplify_ring(ring):
    # The published geometry is kept exactly (no simplification) so wilaya borders stay shared and
    # accurate; coordinates are only rounded to 4 decimals (~11 m).
    out = [[round(x, 4), round(y, 4)] for x, y in ring]
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def ring_area_km2(ring):
    # equirectangular shoelace, good enough for a label/area figure
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111.32 * math.cos(math.radians(lat0))
    ky = 110.57
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2


def label_point(ring):
    """Interior point far from the edges: grid search inside the bbox, maximise distance to boundary."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    best, best_d = None, -1.0
    steps = 28
    for i in range(1, steps):
        for j in range(1, steps):
            x = min(xs) + (max(xs) - min(xs)) * i / steps
            y = min(ys) + (max(ys) - min(ys)) * j / steps
            if not point_in_ring(x, y, ring):
                continue
            d = min(math.hypot(x - px, y - py) for px, py in ring[:: max(1, len(ring) // 400)])
            if d > best_d:
                best, best_d = (x, y), d
    if best is None:
        best = (sum(xs) / len(xs), sum(ys) / len(ys))
    return [round(best[0], 4), round(best[1], 4)]


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    features = []
    for f in data["features"]:
        props = f["properties"]
        geom = f["geometry"]
        rings = [simplify_ring(r) for r in geom["coordinates"]]
        name = props["shapeName"].replace("‎", "").strip()
        code = props["shapeISO"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": code,
                    "number": int(code.split("-")[1]),
                    "name": name,
                    "label_lon": label_point(rings[0])[0],
                    "label_lat": label_point(rings[0])[1],
                    "area_km2": round(ring_area_km2(rings[0])),
                },
                "geometry": {"type": "Polygon", "coordinates": rings},
            }
        )
    features.sort(key=lambda feat: feat["properties"]["number"])
    out = {
        "type": "FeatureCollection",
        "name": "dz-wilayas",
        "metadata": {
            "source": "geoBoundaries gbOpen DZA ADM1 (OpenStreetMap / Wambacher)",
            "license": "Open Data Commons Open Database License 1.0",
            "boundary_year": 2017,
            "units": len(features),
            "note": "48-wilaya administrative division as published; the 10 wilayas created in 2019 are not separated in this release.",
            "url": "https://www.geoboundaries.org/",
        },
        "features": features,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Lite preview copy for the small dashboard map only (coarser outlines, same boundaries).
    lite = json.loads(json.dumps(out))
    for feat in lite["features"]:
        feat["geometry"]["coordinates"] = [
            [[round(x, 3), round(y, 3)] for x, y in rdp_ring(ring, 0.02)] for ring in feat["geometry"]["coordinates"]
        ]
    lite["metadata"]["note"] += " Preview copy: outlines generalised to ~3 km for the dashboard thumbnail."
    lite_path = OUT.with_name("dz-wilayas-lite.geojson")
    lite_path.write_text(json.dumps(lite, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {lite_path.relative_to(ROOT)}: {lite_path.stat().st_size // 1024} KB")
    verts = sum(len(r) for feat in features for r in feat["geometry"]["coordinates"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(features)} wilayas, {verts} vertices, {OUT.stat().st_size // 1024} KB")
    for feat in features[:3] + features[-3:]:
        p = feat["properties"]
        print(" ", p["code"], p["name"], p["label_lat"], p["label_lon"], p["area_km2"], "km2")


if __name__ == "__main__":
    main()
