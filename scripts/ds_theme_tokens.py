"""Replace structural colour literals with light/dark theme tokens (see static/ds/themes.css).

Each rule is an exact substring replacement in one file and must match at least once, so a stale rule
fails loudly instead of silently doing nothing. Status/palette colours (band greens, ambers, reds) are left
alone on purpose: they read the same in both themes. The 404 game scene is an illustration and keeps its
own night-sky colours in both themes.

python scripts/ds_theme_tokens.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = "world/static/world/css/"
DS = "static/ds/"

RULES: dict[str, list[tuple[str, str]]] = {
    W + "world.css": [
        ("color: #06211e", "color: var(--t-accent-ink)"),
        ("background: rgba(8, 16, 18, .92);", "background: var(--t-bar);"),
        ("border-color: #2c464b", "border-color: var(--t-border-strong)"),
        ("background: linear-gradient(180deg, #101e21 0%, #0c1618 100%);", "background: linear-gradient(180deg, var(--t-raised) 0%, var(--t-surface) 100%);"),
        ("#071113", "var(--t-map-bg)"),
        (".signal-bar { height: 4px; background: #122023;", ".signal-bar { height: 4px; background: var(--t-track);"),
        ("background: rgba(7, 17, 19, .8) !important; color: #718684 !important;", "background: var(--t-glass) !important; color: var(--t-faint) !important;"),
        ("color: #9bb0ae !important;", "color: var(--t-muted) !important;"),
        ("background: #122023 !important; color: #edf5f4 !important; border-color: #1e3034 !important;", "background: var(--t-raised) !important; color: var(--t-text) !important; border-color: var(--t-border) !important;"),
        ("background: #122023 !important; color: #edf5f4 !important; border: 1px solid #2c464b;", "background: var(--t-raised) !important; color: var(--t-text) !important; border: 1px solid var(--t-border-strong);"),
        ("background: rgba(13, 23, 25, .96);", "background: var(--t-glass);"),
        ("border: 1px solid #2c464b; border-radius: 8px;", "border: 1px solid var(--t-border-strong); border-radius: 8px;"),
        ("background: #1b3034;", "background: var(--t-raised-2);"),
        (".status-no_data { background: #41565a; }", ".status-no_data { background: var(--t-nodata); }"),
        (".cascade-arrow { color: #2c464b;", ".cascade-arrow { color: var(--t-border-strong);"),
    ],
    W + "dam.css": [
        ("body.world-body.dam-body { background: #071012;", "body.world-body.dam-body { background: var(--t-bg);"),
        ("border: 1px solid #2c464b;", "border: 1px solid var(--t-border-strong);"),
        ("border-color: #1e3034;", "border-color: var(--t-border);"),
        ("color: #a9b8b6;", "color: var(--t-muted);"),
        ("stroke: #1e3034;", "stroke: var(--t-border);"),
        ("background: #122023;", "background: var(--t-track);"),
    ],
    W + "hazards.css": [
        ("background: #071012;", "background: var(--t-bg);"),
        ("background: #122023;", "background: var(--t-track);"),
    ],
    W + "country.css": [
        (".crumb span { color: #b9c4bf;", ".crumb span { color: var(--t-faint);"),
        ("background: #14201d; color: #fff; border: 1px solid #14201d;", "background: var(--t-solid-bg); color: var(--t-solid-ink); border: 1px solid var(--t-solid-bg);"),
        (".btn-light:hover { background: #21312c; }", ".btn-light:hover { background: var(--t-solid-hover); }"),
        ("color: #14201d; border-color: #c9d1cb;", "color: var(--t-text); border-color: var(--t-border-strong);"),
        (".btn-light.ghost:hover { background: #e9eeea; }", ".btn-light.ghost:hover { background: var(--t-ov2); }"),
        (".ch-bar { height: 5px; background: #e9eeea;", ".ch-bar { height: 5px; background: var(--t-track);"),
        ("background: #e9efec; border: 1px solid #e3e8e4;", "background: var(--t-map-bg); border: 1px solid var(--t-border);"),
        (".country-map .leaflet-container { background: #e9efec; }", ".country-map .leaflet-container { background: var(--t-map-bg); }"),
        ("#f0f3f0", "var(--t-rule)"),
        (".pill-ref { background: var(--t-rule); color: #5b6763; }", ".pill-ref { background: var(--t-ov2); color: var(--t-muted); }"),
        ("border-left: 2px solid #e3e8e4;", "border-left: 2px solid var(--t-border);"),
        (".cascade-light-steps > span { color: #b9c4bf;", ".cascade-light-steps > span { color: var(--t-faint);"),
        (".pillar-bar { height: 4px; background: #eef1ef;", ".pillar-bar { height: 4px; background: var(--t-track);"),
        (".water-verdict { margin: 0 0 10px; color: #0d4e4a;", ".water-verdict { margin: 0 0 10px; color: var(--t-link);"),
    ],
    W + "atlas.css": [
        ("background: #e9efec; border: 1px solid #e3e8e4;", "background: var(--t-map-bg); border: 1px solid var(--t-border);"),
        (".atlas-map .leaflet-container { background: #e9efec; }", ".atlas-map .leaflet-container { background: var(--t-map-bg); }"),
        ("border: 1px solid #c9d1cb;", "border: 1px solid var(--t-border-strong);"),
        ("background: #fff; color: var(--sheet-ink);", "background: var(--t-surface); color: var(--sheet-ink);"),
    ],
    W + "docs.css": [
        ("color: #3c4a46", "color: var(--t-soft)"),
        ("background: #eef1ef;", "background: var(--t-ov2);"),
        ("#f0f3f0", "var(--t-rule)"),
        (".formula { background: #14201d; color: #e7f1f2;", ".formula { background: var(--t-code-bg); color: var(--t-code-ink);"),
    ],
    "hydro/static/hydro/css/app.css": [
        ("#bfd9dd", "var(--t-border-strong)"),
        ("#cfe2e5", "var(--t-border-strong)"),
        ("#e7eef0", "var(--t-ov2)"),
        ("rgba(246, 247, 242, 0.82)", "var(--t-glass)"),
        ("rgba(231, 241, 242, 0.92)", "var(--t-glass)"),
        ("background: #24322e;", "background: var(--t-solid-hover);"),
        ("background: var(--text);\n  color: #fff;", "background: var(--text);\n  color: var(--t-bg);"),
        ("border-color: var(--text);\n  color: #fff;", "border-color: var(--text);\n  color: var(--t-bg);"),
    ],
    DS + "ds.css": [
        ("background: rgba(8, 16, 18, .86);", "background: var(--t-bar);"),
        ("#2d4a4f", "var(--t-border-strong)"),
        ("rgba(2, 6, 7, .6)", "var(--t-scrim)"),
        ("rgba(2, 6, 7, .62)", "var(--t-scrim)"),
        (".ds-seg button.is-active { background: var(--c-text); color: #0a1416; }", ".ds-seg button.is-active { background: var(--c-text); color: var(--t-bg); }"),
        ("background: #f4f8f7; color: #0d1719;", "background: var(--t-tip-bg); color: var(--t-tip-ink);"),
        (".ds-tip .tip-muted { color: #53605c; }", ".ds-tip .tip-muted, .ds-map-tip .tip-muted { color: var(--t-tip-muted); }"),
        (".leaflet-popup-tip { background: #f4f8f7; }", ".leaflet-popup-tip { background: var(--t-tip-bg); }"),
        ("border-bottom: 1px solid rgba(255, 255, 255, .06);", "border-bottom: 1px solid var(--t-border);"),
        ("border-top: 1px solid rgba(255, 255, 255, .06);", "border-top: 1px solid var(--t-border);"),
    ],
    DS + "pages.css": [
        ("#c3d2d0", "var(--t-soft)"),
        ("background: #071012 !important;", "background: var(--t-map-bg) !important;"),
        ("border-color: rgba(255, 255, 255, .06) !important;", "border-color: var(--t-border) !important;"),
        ("border-color: #e6ebe7 !important;", "border-color: var(--t-border) !important;"),
    ],
    DS + "map-viewer.css": [
        ("#24393d", "var(--t-border-strong)"),
        ("background: #dfe9e8;", "background: var(--t-knob);"),
        ("background: #071012", "background: var(--t-map-bg)"),
        ("rgba(7, 16, 18, .7)", "var(--t-glass)"),
        ("rgba(7, 16, 18, .9)", "var(--t-glass)"),
        ("rgba(13, 23, 25, .92)", "var(--t-glass)"),
        ("rgba(13, 23, 25, .9)", "var(--t-glass)"),
        ("color: #f4f8f7;\n  text-shadow: 0 1px 2px rgba(0, 0, 0, .9), 0 0 6px rgba(0, 0, 0, .7);", "color: var(--t-label);\n  text-shadow: var(--t-label-halo);"),
        ("border-left: 1px solid rgba(255, 255, 255, .06);", "border-left: 1px solid var(--t-border);"),
        ("border-right: 1px solid rgba(255, 255, 255, .06);", "border-right: 1px solid var(--t-border);"),
        ("border-top: 1px solid rgba(255, 255, 255, .06);", "border-top: 1px solid var(--t-border);"),
    ],
    DS + "notfound.css": [
        (".nf-lede { color: #c3d2d0;", ".nf-lede { color: var(--t-soft);"),
        (".nf-overlay strong { font-size: 22px; font-weight: 800; color: var(--c-text); }", ".nf-overlay strong { font-size: 22px; font-weight: 800; color: #edf5f4; }"),
        (".nf-pad__btn { flex: 1; height: 56px; border-radius: var(--r-md); border: 1px solid var(--c-border); background: rgba(255, 255, 255, .04);", ".nf-pad__btn { flex: 1; height: 56px; border-radius: var(--r-md); border: 1px solid var(--c-border); background: var(--t-ov2);"),
    ],
}

# White overlays in the DS layer (surfaces, tracks, hovers) -> theme overlays by strength.
OVERLAY_FILES = [DS + "ds.css", DS + "pages.css", DS + "map-viewer.css"]
OVERLAY = re.compile(r"rgba\(255,\s*255,\s*255,\s*(0?\.\d+)\)")


def overlay_token(alpha: float) -> str:
    if alpha <= 0.035:
        return "var(--t-ov1)"
    if alpha <= 0.05:
        return "var(--t-ov2)"
    if alpha <= 0.08:
        return "var(--t-ov3)"
    if alpha <= 0.12:
        return "var(--t-ov4)"
    return "var(--t-ov5)"


def main():
    for rel, rules in RULES.items():
        path = ROOT / rel
        s = path.read_text(encoding="utf-8")
        for old, new in rules:
            n = s.count(old)
            if not n:
                raise SystemExit(f"rule did not match in {rel}: {old!r}")
            s = s.replace(old, new)
        path.write_text(s, encoding="utf-8")
        print(f"{rel}: {len(rules)} rules")
    for rel in OVERLAY_FILES:
        path = ROOT / rel
        s = path.read_text(encoding="utf-8")
        out, n = OVERLAY.subn(lambda m: overlay_token(float(m.group(1))), s)
        path.write_text(out, encoding="utf-8")
        print(f"{rel}: {n} white overlays -> theme overlays")


if __name__ == "__main__":
    main()
