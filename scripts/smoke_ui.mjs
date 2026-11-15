import { Browser } from "file:///C:/Users/PC/.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8011";
const browser = await Browser.launch({ width: 1440, height: 900 });
const page = await browser.newPage({ width: 1440, height: 900 });
await page.send("Page.addScriptToEvaluateOnNewDocument", {
  source:
    "window.__errors=[];addEventListener('error',e=>window.__errors.push(e.message));addEventListener('unhandledrejection',e=>window.__errors.push(String(e.reason)));",
});

const wait = (ms) => page.eval(`new Promise(resolve => setTimeout(resolve, ${ms}))`);
const state = () =>
  page.eval(`({
    url: location.href,
    verdict: document.getElementById('verdict-label')?.textContent.trim(),
    score: document.querySelector('.index-stat .stat-value')?.textContent.trim(),
    county: document.querySelector('.country-select')?.value,
    map: Boolean(window.__aquaMap),
    markers: window.__aquaMarkerCount || 0,
    errors: window.__errors,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1
  })`);

await page.goto(`${BASE}/country/DZ/`);
console.log("initial", JSON.stringify(await state()));

await page.eval(`document.querySelector('[data-rain="dry"]').click()`);
await wait(2200);
console.log("dry", JSON.stringify(await state()));

await page.eval(`(() => { const input = document.querySelector('#demand-stress'); input.value = '1.5'; input.dispatchEvent(new Event('input', {bubbles:true})); input.dispatchEvent(new Event('change', {bubbles:true})); })()`);
await wait(2200);
console.log("dry_stress", JSON.stringify(await state()));

await page.eval(`document.querySelector('[data-rain="whatif"]').click()`);
await wait(2200);
console.log("whatif", JSON.stringify(await state()));

const mobile = await browser.newPage({ width: 390, height: 844, mobile: true });
await mobile.goto(`${BASE}/country/DZ/`);
const mobileState = await mobile.eval(`({
  width: window.innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  verdict: document.getElementById('verdict-label')?.textContent.trim(),
  map: Boolean(window.__aquaMap),
  markers: document.querySelectorAll('.leaflet-interactive').length,
  navItems: document.querySelectorAll('.nav-item').length,
  errors: window.__errors || []
})`);
console.log("mobile", JSON.stringify(mobileState));

await mobile.close();
await browser.close();
