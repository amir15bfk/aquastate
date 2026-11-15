"""One-off design-system normaliser for the legacy stylesheets (kept for review / re-runs).

Rules, applied per declaration block:
  * font-size 7-10px  -> 12px ; 10.5-11.5px -> 13px   (minimum readable size; SVG text rules with
    `fill:` are skipped because they live inside a fixed viewBox)
  * text-transform: uppercase -> removed, and that block's letter-spacing -> normal
  * literal "IBM Plex Sans" font stacks -> var(--ds-font)

python scripts/ds_normalize_css.py          # rewrite in place and print a change count per file
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "world" / "static" / "world" / "css").glob("*.css")) + [
    ROOT / "hydro" / "static" / "hydro" / "css" / "app.css"
]
BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
SIZE = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)px")


def fix_block(selector: str, body: str, stats: dict) -> str:
    if "@font-face" in selector:
        return body
    svg_text = "fill:" in body
    if not svg_text:
        def bump(m):
            px = float(m.group(1))
            if px <= 10:
                stats["size"] += 1
                return "font-size: 12px"
            if px < 12:
                stats["size"] += 1
                return "font-size: 13px"
            return m.group(0)

        body = SIZE.sub(bump, body)
    if re.search(r"text-transform:\s*uppercase", body):
        stats["upper"] += 1
        body = re.sub(r"\s*text-transform:\s*uppercase;?", "", body)
        body = re.sub(r"letter-spacing:\s*[^;}]+", "letter-spacing: normal", body)
    if '"IBM Plex Sans"' in body:
        stats["font"] += 1
        body = re.sub(r'"IBM Plex Sans"(?:\s*,\s*[^;}]+)?', "var(--ds-font)", body)
    return body


def main():
    for path in FILES:
        css = path.read_text(encoding="utf-8")
        stats = {"size": 0, "upper": 0, "font": 0}
        out = BLOCK.sub(lambda m: m.group(1) + "{" + fix_block(m.group(1), m.group(2), stats) + "}", css)
        if out != css:
            path.write_text(out, encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {stats}")


if __name__ == "__main__":
    main()
