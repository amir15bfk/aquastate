"""Error/empty-state checks (blocked APIs) + tablet-width screenshots."""
import pathlib, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
ok = 0; n = 0
def check(name, cond, detail=""):
    global ok, n
    n += 1; ok += bool(cond)
    print("PASS" if cond else "FAIL", name, detail, flush=True)

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.route("**/api/regions/DZ/", lambda r: r.abort())
    pg.goto(BASE + "/map/?c=DZ", wait_until="load"); pg.wait_for_timeout(3000)
    check("map viewer: error state when the region API fails", pg.locator("#mv-error").is_visible(), pg.inner_text("#mv-error")[:80].replace("\n", " "))
    pg.screenshot(path=str(out / "map_error.png"))
    pg.unroute("**/api/regions/DZ/")
    pg.click("#mv-retry"); pg.wait_for_timeout(3500)
    check("map viewer: retry recovers", not pg.locator("#mv-error").is_visible() and pg.inner_text("#mv-title") == "Algeria")
    pg.route("**/api/regions/DZ/", lambda r: r.fulfill(status=202, content_type="application/json", body='{"status": "building", "iso2": "DZ", "units": 48, "job": {"state": "running", "stage": "climate", "done": 20, "total": 48, "label": "Fetching NASA POWER climate records"}}'))
    pg.goto(BASE + "/map/?c=DZ", wait_until="load"); pg.wait_for_timeout(3000)
    check("map viewer: first-visit build shows progress", pg.locator("#mv-progress").is_visible() and "20/48" in pg.inner_text("#mv-loading"), pg.inner_text("#mv-loading")[:90].replace("\n", " "))
    pg.screenshot(path=str(out / "map_building.png"))
    pg.unroute("**/api/regions/DZ/")
    pg.route("**/api/algeria/wilayas/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"wilayas": [], "message": "No wilaya snapshot yet."}'))
    pg.goto(BASE + "/", wait_until="load"); pg.wait_for_timeout(2000)
    check("overview: wilaya empty state", "No wilaya snapshot" in pg.inner_text("#dz-top"))
    pg.unroute("**/api/algeria/wilayas/**")
    pg.route("**/api/events/**", lambda r: r.abort())
    pg.goto(BASE + "/", wait_until="load"); pg.wait_for_timeout(2000)
    check("overview: events error state", "could not load" in pg.inner_text("#alert-list").lower())
    pg.unroute("**/api/events/**")
    pg.route("**/countries-world.geojson", lambda r: r.abort())
    pg.goto(BASE + "/", wait_until="load"); pg.wait_for_timeout(2000)
    check("overview: map fallback state", pg.locator("#map-fallback").is_visible())
    ctx.close()

    ctx = b.new_context(viewport={"width": 768, "height": 1024}, is_mobile=True, has_touch=True)
    for route, name in (("/", "home"), ("/map/?c=DZ&w=DZ-16", "map"), ("/map/", "map_world"), ("/no-page/", "404")):
        pg = ctx.new_page(); pg.goto(BASE + route, wait_until="load"); pg.wait_for_timeout(2200)
        check(f"tablet {route}: no overflow", pg.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0)
        pg.screenshot(path=str(out / f"tablet_{name}.png")); pg.close()
    b.close()
print(f"{ok}/{n} passed")
