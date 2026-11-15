from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8020"
OUT = Path(r"F:\amir\nasa space app\aquastate-world\docs\screenshots")
OUT.mkdir(parents=True, exist_ok=True)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

pages = [
    ("world-full.png", "/", False, 1440, 1000),
    ("world-mobile.png", "/", True, 390, 844),
    ("country-full.png", "/country/DZ/", False, 1440, 1000),
    ("country-mobile.png", "/country/DZ/", True, 390, 844),
    ("dam-full.png", "/dam/beni-haroun/", False, 1440, 1000),
    ("hazards-full.png", "/hazards/", False, 1440, 1000),
    ("dams-atlas.png", "/dams/", False, 1440, 1000),
    ("methodology.png", "/methodology/", False, 1440, 1000),
    ("sources.png", "/sources/", False, 1440, 1000),
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    for name, path, mobile, width, height in pages:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            is_mobile=mobile,
            has_touch=mobile,
        )
        page = context.new_page()
        page.goto(BASE + path, wait_until="load", timeout=60000)
        page.wait_for_timeout(3500)
        page.screenshot(path=str(OUT / name), full_page=True)
        # Report the actual layout width so overflow is visible in the log.
        metrics = page.evaluate(
            "() => ({inner: window.innerWidth, scroll: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight})"
        )
        print(name, metrics)
        context.close()
    browser.close()
