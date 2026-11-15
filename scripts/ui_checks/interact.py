"""Scripted interaction tests (desktop 1440x900 + mobile 390x844). Prints PASS/FAIL lines, saves screenshots.

python interact.py <out_dir> [suite ...]   suites: map overview search game pilot
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
suites = sys.argv[2:] or ["map", "overview", "search"]
results = []


def check(name, cond, detail=""):
    results.append(("PASS" if cond else "FAIL", name, detail))
    print(("PASS" if cond else "FAIL"), name, detail, flush=True)


def errors_of(page):
    errs = []
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append(f"pageerror {e}"))
    return errs


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)

    if "map" in suites:
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/map/?w=DZ-13&layer=water_stress", wait_until="networkidle")
        pg.wait_for_timeout(1800)
        pg.wait_for_function("document.querySelector('#mv-title') && document.querySelector('#mv-title').textContent === 'Algeria' && document.querySelectorAll('.mv-name').length === 1", timeout=60000)
        check("map: legacy ?w= link opens Algeria", pg.inner_text("#mv-title") == "Algeria")
        check("map: selected via URL", "Tlemcen" in pg.inner_text("#mv-detail"), pg.inner_text(".mv-name") if pg.locator(".mv-name").count() else "")
        check("map: layer from URL", pg.get_attribute('#mv-layers [data-layer="water_stress"]', "aria-checked") == "true")
        pg.screenshot(path=str(out / "map_selected_desk.png"))
        # switch layer by clicking an indicator in the detail panel
        pg.click('[data-layer-jump="fire"]'); pg.wait_for_timeout(500)
        check("map: indicator click switches layer", pg.get_attribute('#mv-layers [data-layer="fire"]', "aria-checked") == "true")
        check("map: legend updates", "Forest fire" in pg.inner_text("#mv-legend"), pg.inner_text("#mv-legend")[:60])
        # month selection on a latest-only layer -> auto switch to drought
        months = pg.eval_on_selector_all("#mv-month option", "els => els.map(e => e.value).filter(Boolean)")
        pg.select_option("#mv-month", months[3]); pg.wait_for_timeout(600)
        check("map: month on latest-only layer switches to drought", pg.get_attribute('#mv-layers [data-layer="drought"]', "aria-checked") == "true")
        check("map: URL keeps month", f"month={months[3]}" in pg.url, pg.url)
        # back to summary
        pg.click("[data-back]"); pg.wait_for_timeout(900)
        check("map: back shows national summary", "Algeria at a glance" in pg.inner_text("#mv-detail"))
        # level filter
        pg.click('#mv-levels [data-level="low"]'); pg.wait_for_timeout(300)
        check("map: level chip toggles", pg.get_attribute('#mv-levels [data-level="low"]', "aria-pressed") == "false")
        # hover tooltip
        box = pg.locator("#mv-map").bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55); pg.wait_for_timeout(500)
        check("map: hover tooltip", pg.locator(".leaflet-tooltip.ds-map-tip").count() > 0)
        # click a wilaya on the map
        pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55); pg.wait_for_timeout(1200)
        check("map: click selects a wilaya", pg.locator(".mv-name").count() == 1, pg.inner_text(".mv-name") if pg.locator(".mv-name").count() else "")
        pg.screenshot(path=str(out / "map_click_desk.png"))
        # search + reset
        pg.click("#mv-reset-all"); pg.wait_for_timeout(900)
        pg.fill("#mv-find", "Oran"); pg.wait_for_timeout(1200)
        check("map: exact search selects", "Oran" in (pg.inner_text(".mv-name") if pg.locator(".mv-name").count() else ""))
        before = pg.locator("#mv-map path.leaflet-interactive").count()
        pg.click("label:has(#mv-dams)"); pg.wait_for_timeout(400)
        check("map: dams overlay", pg.locator("#mv-map path.leaflet-interactive").count() > before)
        check("map: no console errors", not errs, "; ".join(errs[:3]))
        ctx.close()

        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/map/?c=DZ", wait_until="networkidle"); pg.wait_for_timeout(2500)
        pg.screenshot(path=str(out / "map_mob.png"), full_page=True)
        pg.click("#mv-open-controls"); pg.wait_for_timeout(400)
        check("map mobile: filters sheet opens", pg.locator(".mv-controls").is_visible())
        pg.screenshot(path=str(out / "map_mob_filters.png"))
        pg.click("#mv-open-controls"); pg.wait_for_timeout(300)
        pg.click('#mv-mobile-layers [data-layer="flood"]'); pg.wait_for_timeout(400)
        check("map mobile: layer chips work", pg.get_attribute('#mv-mobile-layers [data-layer="flood"]', "aria-pressed") == "true")
        check("map mobile: no overflow", pg.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0)
        check("map mobile: no console errors", not errs, "; ".join(errs[:3]))
        ctx.close()

    if "world" in suites:
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/map/", wait_until="networkidle"); pg.wait_for_timeout(1500)
        n_world = pg.locator("#mv-map path.leaflet-interactive").count()
        check("world: starts in world mode", pg.inner_text("#mv-title") == "Map viewer" and n_world > 200, str(n_world))
        check("world: world summary + legend counts countries", "country by country" in pg.inner_text("#mv-detail") and "countries" in pg.inner_text("#mv-legend"))
        pg.screenshot(path=str(out / "world_mode.png"))
        pg.click('#mv-layers [data-layer="vegetation"]'); pg.wait_for_timeout(400)
        check("world: vegetation explains it is per-region", "per region" in pg.inner_text("#mv-detail"))
        pg.click('#mv-layers [data-layer="drought"]'); pg.wait_for_timeout(300)
        pg.fill("#mv-country", "Morocco"); pg.dispatch_event("#mv-country", "change")
        pg.wait_for_function("document.querySelector('#mv-title').textContent === 'Morocco' && document.querySelector('#mv-loading').hidden", timeout=90000)
        check("world: country picker opens Morocco", "c=MA" in pg.url, pg.url)
        check("world: Morocco regions drawn", "regions of Morocco" in pg.inner_text("#mv-intro").lower() or "Regions" in pg.inner_text("#mv-intro"))
        pg.screenshot(path=str(out / "world_morocco.png"))
        pg.click("#mv-crumb-world"); pg.wait_for_timeout(900)
        check("world: breadcrumb returns to world", pg.inner_text("#mv-title") == "Map viewer" and "c=" not in pg.url)
        pg.go_back(); pg.wait_for_function("document.querySelector('#mv-title').textContent === 'Morocco'", timeout=60000)
        check("world: browser Back restores the country", "c=MA" in pg.url)
        pg.goto(BASE + "/map/?c=RU", wait_until="load")
        pg.wait_for_function("document.querySelector('#mv-title').textContent === 'Russia' && document.querySelector('#mv-loading').hidden", timeout=120000)
        pg.wait_for_timeout(1200)
        check("world: Russia (antimeridian) renders federal subjects", "federal subjects" in pg.inner_text("#mv-legend"), pg.inner_text("#mv-legend")[-60:])
        pg.screenshot(path=str(out / "world_russia.png"))
        box = pg.locator("#mv-map").bounding_box()
        pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55); pg.wait_for_timeout(1200)
        check("world: click selects a Russian region", pg.locator(".mv-name").count() == 1, pg.inner_text(".mv-name") if pg.locator(".mv-name").count() else "")
        pg.goto(BASE + "/map/?c=VA", wait_until="load"); pg.wait_for_timeout(2500)
        check("world: country without regions shows an honest message", pg.locator("#mv-error").is_visible() and "No regional map" in pg.inner_text("#mv-error"))
        pg.goto(BASE + "/country/FR/", wait_until="load")
        check("world: country sheet links its regional map", pg.locator('a[href="/map/?c=FR"]').count() == 1)
        check("world: no console errors", not [e for e in errs if "404" not in e], "; ".join(errs[:3]))
        ctx.close()

    if "theme" in suites:
        for scheme in ("dark", "light"):
            ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme=scheme)
            pg = ctx.new_page()
            pg.goto(BASE + "/country/DZ/", wait_until="load")
            check(f"theme: follows system preference ({scheme})", pg.evaluate("document.documentElement.dataset.theme") == scheme)
            ctx.close()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1500)
        bg0 = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        stroke0 = pg.evaluate("document.querySelector('#world-map path.leaflet-interactive').getAttribute('stroke')")
        pg.click(".site-tools [data-theme-toggle]"); pg.wait_for_timeout(600)
        check("theme: toggle switches to light", pg.evaluate("document.documentElement.dataset.theme") == "light")
        check("theme: page background changes", pg.evaluate("getComputedStyle(document.body).backgroundColor") != bg0, bg0)
        check("theme: dashboard map recolours in place", pg.evaluate("document.querySelector('#world-map path.leaflet-interactive').getAttribute('stroke')") != stroke0, stroke0)
        check("theme: choice saved", pg.evaluate("localStorage.getItem('aquastate.theme')") == "light")
        pg.reload(wait_until="load")
        check("theme: choice survives reload (overrides system dark)", pg.evaluate("document.documentElement.dataset.theme") == "light")
        pg.screenshot(path=str(out / "theme_overview_light.png"))
        pg.goto(BASE + "/map/?c=DZ", wait_until="load")
        pg.wait_for_function("document.querySelector('#mv-loading').hidden", timeout=60000); pg.wait_for_timeout(1200)
        land0 = pg.evaluate("[...document.querySelectorAll('#mv-map path')].map(p => p.getAttribute('fill')).find(f => f && f.startsWith('#'))")
        pg.click(".site-tools [data-theme-toggle]"); pg.wait_for_timeout(600)
        land1 = pg.evaluate("[...document.querySelectorAll('#mv-map path')].map(p => p.getAttribute('fill')).find(f => f && f.startsWith('#'))")
        check("theme: map viewer neighbours recolour", land0 != land1, f"{land0} -> {land1}")
        pg.goto(BASE + "/water/DZ/", wait_until="networkidle"); pg.wait_for_timeout(1200)
        rule0 = pg.evaluate("(document.querySelector('#runway-chart line, svg line') || {}).getAttribute && document.querySelector('svg line').getAttribute('stroke')")
        pg.click(".site-tools [data-theme-toggle]"); pg.wait_for_timeout(700)
        rule1 = pg.evaluate("document.querySelector('svg line') && document.querySelector('svg line').getAttribute('stroke')")
        check("theme: water runway chart redraws", rule0 != rule1, f"{rule0} -> {rule1}")
        pg.goto(BASE + "/pilot/", wait_until="load"); pg.wait_for_timeout(4000)
        pane0 = pg.evaluate("getComputedStyle(document.querySelector('.map-pane')).backgroundColor")
        pg.click(".site-tools [data-theme-toggle]"); pg.wait_for_timeout(700)
        check("theme: pilot follows the toggle", pg.evaluate("getComputedStyle(document.querySelector('.map-pane')).backgroundColor") != pane0)
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(300)
        before = pg.evaluate("document.documentElement.dataset.theme")
        pg.click("[data-drawer-open]"); pg.wait_for_timeout(300)
        pg.click(".site-drawer [data-theme-toggle]"); pg.wait_for_timeout(500)
        check("theme: mobile menu toggle works", pg.evaluate("document.documentElement.dataset.theme") != before)
        check("theme: no console errors", not errs, "; ".join(errs[:3]))
        ctx.close()

    if "overview" in suites:
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1500)
        check("overview: dz mini map drawn", pg.locator("#dz-mini path").count() >= 48 and "z" not in (pg.get_attribute("#dz-mini path", "d") or "z")[:8])
        pg.click('#layer-seg [data-layer="drought"]'); pg.wait_for_timeout(500)
        check("overview: layer switch retitles ranking", "drought" in pg.inner_text("#rank-title").lower(), pg.inner_text("#rank-title"))
        pg.click('#rank-list .ov-rank__row'); pg.wait_for_timeout(900)
        check("overview: ranking click opens detail", pg.locator("#country-detail").is_visible())
        pg.screenshot(path=str(out / "overview_detail.png"))
        pg.click("[data-close-detail]"); pg.wait_for_timeout(300)
        pg.click('.ov-histo__bar >> nth=5'); pg.wait_for_timeout(400)
        check("overview: histogram filter shows clear chip", pg.locator("#band-clear").is_visible())
        pg.click("#band-clear"); pg.wait_for_timeout(300)
        pg.click('.ov-kpi[data-filter-bands]'); pg.wait_for_timeout(700)
        check("overview: KPI filters bands", "Watch" in pg.inner_text("#band-clear"), pg.inner_text("#band-clear"))
        pg.click('[data-overlay="dams"]'); pg.wait_for_timeout(1200)
        check("overview: dams overlay toggles", pg.get_attribute('[data-overlay="dams"]', "aria-pressed") == "true")
        pg.select_option("#alert-period", "7"); pg.wait_for_timeout(300)
        c7 = pg.inner_text("#alert-count")
        pg.select_option("#alert-period", "all"); pg.wait_for_timeout(300)
        call = pg.inner_text("#alert-count")
        check("overview: alert period filter changes count", c7 != call, f"{c7} | {call}")
        pg.click('#alert-chips [data-cat="floods"]'); pg.wait_for_timeout(300)
        check("overview: alert category filter", "0 events" in pg.inner_text("#alert-count") or "Nothing" in pg.inner_text("#alert-list"))
        pg.click('#dz-seg [data-dz="water_stress"]'); pg.wait_for_timeout(300)
        check("overview: dz layer switch", "water stress" in pg.inner_text("#dz-caption").lower())
        check("overview: no console errors", not errs, "; ".join(errs[:3]))
        ctx.close()

    if "search" in suites:
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/hazards/", wait_until="networkidle")
        pg.keyboard.press("Control+k"); pg.wait_for_timeout(400)
        check("search: Ctrl+K opens palette", pg.locator("#ds-search[open]").count() == 1)
        pg.keyboard.type("tlem"); pg.wait_for_timeout(1500)
        txt = pg.inner_text("#ds-search-results")
        check("search: finds wilaya", "Tlemcen" in txt, txt[:120].replace("\n", " "))
        pg.fill("#ds-search-input", "beni har"); pg.wait_for_timeout(1500)
        check("search: finds dam", "Beni Haroun" in pg.inner_text("#ds-search-results"))
        pg.fill("#ds-search-input", "moroc"); pg.wait_for_timeout(800)
        check("search: finds country", "Morocco" in pg.inner_text("#ds-search-results"))
        pg.keyboard.press("Enter")
        try:
            pg.wait_for_url("**/country/MA/**", timeout=8000)
        except Exception:
            pass
        check("search: Enter navigates", "/country/MA/" in pg.url, pg.url)
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(300)
        pg.click("[data-drawer-open]"); pg.wait_for_timeout(400)
        check("nav: mobile drawer opens", pg.locator(".site-drawer[data-open=true]").count() == 1)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        check("nav: drawer closes on Esc", pg.locator(".site-drawer[data-open=true]").count() == 0)
        check("search/nav: no console errors", not errs, "; ".join(errs[:3]))
        ctx.close()

    if "pilot" in suites:
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page(); errs = errors_of(pg)
        pg.goto(BASE + "/pilot/", wait_until="load"); pg.wait_for_timeout(5000)
        check("pilot: maplibre canvas", pg.locator("canvas.maplibregl-canvas").count() == 1)
        pg.screenshot(path=str(out / "pilot_desk.png"))
        check("pilot: no console errors", not [e for e in errs if "favicon" not in e], "; ".join(errs[:3]))
        ctx.close()

    if "game" in suites:
        for vw, vh, mob in ((1440, 900, False), (390, 844, True)):
            ctx = b.new_context(viewport={"width": vw, "height": vh}, is_mobile=mob, has_touch=mob)
            pg = ctx.new_page(); errs = errors_of(pg)
            r = pg.goto(BASE + "/no-such-page/", wait_until="networkidle")
            check(f"404 {vw}: status 404", r.status == 404, str(r.status))
            check(f"404 {vw}: friendly copy", "dried up" in pg.inner_text("body"))
            pg.click("#rain-start"); pg.wait_for_timeout(300)
            check(f"404 {vw}: game running", pg.evaluate("window.__rain && window.__rain.state") == "playing")
            for _ in range(30):
                pg.keyboard.press("ArrowLeft" if _ % 2 else "ArrowRight"); pg.wait_for_timeout(120)
            if mob:
                cv = pg.locator("#rain-canvas").bounding_box()
                pg.touchscreen.tap(cv["x"] + 40, cv["y"] + cv["height"] - 30); pg.wait_for_timeout(300)
            st = pg.evaluate("({s: window.__rain.score, l: window.__rain.lives, st: window.__rain.state})")
            check(f"404 {vw}: score/lives tracked", isinstance(st["s"], (int, float)) and st["l"] <= 3, json.dumps(st))
            pg.screenshot(path=str(out / f"game_{vw}.png"))
            pg.evaluate("window.__rain.forceGameOver()"); pg.wait_for_timeout(500)
            check(f"404 {vw}: game over state", pg.evaluate("window.__rain.state") == "over" and pg.locator("#rain-restart").is_visible())
            pg.screenshot(path=str(out / f"game_over_{vw}.png"))
            pg.click("#rain-restart"); pg.wait_for_timeout(300)
            check(f"404 {vw}: restart", pg.evaluate("window.__rain.state") == "playing" and pg.evaluate("window.__rain.score") == 0)
            check(f"404 {vw}: no overflow", pg.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0)
            check(f"404 {vw}: no console errors", not [e for e in errs if "404" not in e], "; ".join(errs[:3]))
            ctx.close()
    b.close()

fails = [r for r in results if r[0] == "FAIL"]
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
