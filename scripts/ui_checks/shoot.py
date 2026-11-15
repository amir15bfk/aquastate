"""Full-page screenshots of every route at desktop + mobile, with console errors and overflow checks.

python shoot.py <out_dir> [route ...]
Set THEME=light or THEME=dark to seed the saved theme before every page load (default: system = light in headless).
"""
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
ROUTES = ["/", "/country/DZ/", "/water/DZ/", "/dams/", "/dam/beni-haroun/", "/hazards/",
          "/methodology/", "/sources/", "/pilot/", "/this-page-does-not-exist/"]
VIEWPORTS = {"desk": (1440, 900), "mob": (390, 844)}

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
routes = sys.argv[2:] or ROUTES
report = {}
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    for vname, (w, h) in VIEWPORTS.items():
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                  is_mobile=(vname == "mob"), has_touch=(vname == "mob"))
        if os.environ.get("THEME") in ("light", "dark"):
            ctx.add_init_script(f"try {{ localStorage.setItem('aquastate.theme', '{os.environ['THEME']}'); }} catch (e) {{}}")
        for route in routes:
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m, e=errors: e.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda exc, e=errors: e.append(f"pageerror: {exc}"))
            resp = page.goto(BASE + route, wait_until="load", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                errors.append("note: network never idle (polling)")
            page.wait_for_timeout(1200)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            name = ("".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in route.strip("/")) or "home") + f"_{vname}.png"
            page.screenshot(path=str(out / name), full_page=True)
            theme = page.evaluate("document.documentElement.dataset.theme")
            report[f"{vname} {route}"] = {"status": resp.status if resp else None, "theme": theme,
                                          "overflow_px": overflow, "errors": errors[:8]}
            page.close()
        ctx.close()
    browser.close()
print(json.dumps(report, indent=1))
