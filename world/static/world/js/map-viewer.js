/* Map Viewer — the world, then any country's first-level regions (geoBoundaries ADM1).
   World mode: countries coloured from the live world snapshot (/api/world/).
   Country mode: regions coloured from /api/regions/<ISO2>/ (computed on first visit, with progress). */
(function () {
  "use strict";
  const root = document.getElementById("mv");
  if (!root) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (v) => (window.DS ? window.DS.esc(v) : String(v == null ? "" : v));
  const fold = (s) => (window.DS ? window.DS.fold(s) : String(s || "").toLowerCase());
  const toast = (m) => window.DS && window.DS.toast(m);
  const fmt = (v, d = 0) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));
  /* ---------------- theme colours (read from the CSS theme tokens; refreshed on ds:theme) ---------------- */
  const T = {};
  function readTheme() {
    const c = (name, fallback) => (window.DS && window.DS.cssVar(name)) || fallback;
    T.nodata = c("--t-nodata", "#2a3d40"); T.line = c("--t-map-line", "#0a1416"); T.hover = c("--t-map-hover", "#edf5f4");
    T.select = c("--t-map-select", "#ffffff"); T.land = c("--t-map-land", "#0f1c1f"); T.edge = c("--t-map-edge", "#1f3337");
    T.pending = c("--t-raised-2", "#1d3236");
  }
  readTheme();
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  /* ---------------- scales ---------------- */
  const RAMP = ["#2b6f6a", "#8fae5a", "#e5a23b", "#e07a3f", "#ef6f72"];
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  function ramp(p) {
    if (p == null || Number.isNaN(Number(p))) return T.nodata;
    const v = clamp(Number(p), 0, 100) / 100 * (RAMP.length - 1);
    const i = Math.min(RAMP.length - 2, Math.floor(v));
    const a = hex(RAMP[i]), b = hex(RAMP[i + 1]), t = v - i;
    return `rgb(${a.map((c, k) => Math.round(c + (b[k] - c) * t)).join(",")})`;
  }
  const LEVELS = {
    pressure: [
      { key: "low", lo: 0, hi: 25, label: "Low" }, { key: "moderate", lo: 25, hi: 50, label: "Moderate" },
      { key: "high", lo: 50, hi: 75, label: "High" }, { key: "severe", lo: 75, hi: 101, label: "Severe" },
    ],
    health: [
      { key: "very_dry", lo: 0, hi: 25, label: "Very dry" }, { key: "dry", lo: 25, hi: 50, label: "Drier than usual" },
      { key: "normal", lo: 50, hi: 75, label: "Normal" }, { key: "moist", lo: 75, hi: 101, label: "Moister than usual" },
    ],
  };
  // Layer metadata for world mode (country mode receives the same text from the API).
  const BASE_LAYERS = {
    water_stress: { label: "Water stress", direction: "pressure", history: false, short: "Rain vs evaporative demand", source: "NASA POWER / MERRA-2 monthly",
      detail: "Climatic water stress: 100 − aridity score, where aridity = annual rain ÷ potential evapotranspiration. High means the climate demands far more water than it supplies." },
    drought: { label: "Drought", direction: "pressure", history: true, short: "Rain and soil deficit vs normal", source: "NASA POWER monthly + Open-Meteo 92-day window",
      detail: "Drought pressure from SPI-3, SPI-12, soil-moisture percentile and the current dry spell." },
    flood: { label: "Flood risk", direction: "pressure", history: false, short: "Forecast river discharge vs baseline", source: "Open-Meteo GloFAS + NASA EONET",
      detail: "Flood pressure from GloFAS forecast discharge against its 60-day baseline plus active EONET flood events." },
    fire: { label: "Forest fire risk", direction: "pressure", history: false, short: "Fire weather coupled to drought", source: "Open-Meteo fire weather + NASA EONET",
      detail: "Wildfire pressure from fire weather, drought coupling and active EONET wildfires. It is fire weather, not an ignition forecast." },
    vegetation: { label: "Vegetation moisture", direction: "health", history: true, short: "Proxy · root-zone soil wetness", source: "NASA POWER / MERRA-2 monthly (GWETROOT)",
      detail: "Proxy for vegetation health: root-zone soil wetness percentile against the same month of previous years. Computed per region only — open a country to see it." },
  };
  const ICON = { water_stress: "water", drought: "drought", flood: "flood", fire: "fire", vegetation: "veg" };

  /* ---------------- state ---------------- */
  const params = new URLSearchParams(location.search);
  const S = {
    mode: "world", country: null, payload: null, byCode: new Map(),
    worldRows: new Map(), catalog: new Map(), worldNames: new Map(),
    layer: params.get("layer") || root.dataset.initialLayer || "drought",
    month: params.get("month") || "",
    selected: null, levelsOn: null, query: "", loadToken: 0, poll: null,
  };
  let map, worldLayer, regionLayer, labelLayer, damLayer;
  const worldPath = new Map(), regionPath = new Map(), regionFeat = new Map();

  const layersMeta = () => (S.mode === "country" && S.payload ? S.payload.layers : BASE_LAYERS);
  const meta = (l = S.layer) => layersMeta()[l] || BASE_LAYERS[l];
  const dirOf = (l) => (meta(l) || {}).direction || "pressure";
  const levels = (l = S.layer) => LEVELS[dirOf(l) === "health" ? "health" : "pressure"];
  const colorFor = (v, l = S.layer) => (v == null ? T.nodata : dirOf(l) === "health" ? ramp(100 - v) : ramp(v));
  const levelOf = (v, l = S.layer) => (v == null ? null : levels(l).find((x) => v >= x.lo && v < x.hi) || null);
  const hasHistory = (l) => !!(meta(l) || {}).history;
  const term = () => (S.payload && S.payload.term) || "region";
  const termPlural = () => (S.payload && S.payload.term_plural) || "regions";
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  function countryValue(row, l = S.layer) {
    if (!row) return null;
    if (l === "water_stress") return row.aridity == null ? null : Math.round((100 - clamp(row.aridity / 0.65 * 100, 0, 100)) * 10) / 10;
    if (l === "vegetation") return null;
    return (row.hazards || {})[l] ?? null;
  }
  function regionValue(w, l = S.layer) {
    if (!w) return null;
    if (S.month && hasHistory(l)) {
      const h = (w.history || []).find((x) => x.month === S.month);
      return h ? h[l] : null;
    }
    return w.layers ? w.layers[l] : null;
  }
  const nameOf = (iso2) => S.worldNames.get(iso2) || (S.worldRows.get(iso2) || {}).name || iso2;
  function passes(value, name) {
    if (S.query && !fold(name).includes(S.query)) return false;
    if (S.levelsOn) { const lv = levelOf(value); if (!lv || !S.levelsOn.has(lv.key)) return false; }
    return true;
  }
  function monthLabel(m) {
    if (!m) return "latest";
    const [y, mo] = m.split("-").map(Number);
    return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  }
  function syncUrl(push) {
    const q = new URLSearchParams();
    if (S.country) q.set("c", S.country);
    q.set("layer", S.layer);
    if (S.month && S.mode === "country") q.set("month", S.month);
    if (S.selected && S.mode === "country") q.set("w", S.selected);
    const url = `/map/?${q.toString()}`;
    if (url === location.pathname + location.search) return;
    (push ? history.pushState : history.replaceState).call(history, { c: S.country }, "", url);
  }

  /* ---------------- map + world layer ---------------- */
  function initMap() {
    map = L.map("mv-map", { zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 1.5, maxZoom: 10, worldCopyJump: false, zoomControl: false, attributionControl: true });
    map.attributionControl.setPrefix("");
    L.control.zoom({ position: "topright" }).addTo(map);
    map.setView([20, 10], 2);
    map.on("zoomend moveend", updateLabels);
  }
  function worldStyle(f) {
    const iso = f.properties.iso2;
    const row = S.worldRows.get(iso);
    if (S.mode === "country") {
      const isCur = iso === S.country;
      return { fillColor: T.land, fillOpacity: isCur ? 0 : 1, color: T.edge, weight: 0.8, opacity: isCur ? 0 : 1 };
    }
    const v = countryValue(row);
    const on = passes(v, nameOf(iso));
    const has = S.catalog.has(iso);
    return { fillColor: colorFor(v), fillOpacity: on ? (has ? 0.85 : 0.45) : 0.1, color: T.line, weight: 0.6, opacity: 1 };
  }
  function worldTip(iso) {
    const row = S.worldRows.get(iso);
    const cat = S.catalog.get(iso);
    const name = nameOf(iso);
    if (S.mode === "country") {
      return `<strong>${esc(name)}</strong>${cat ? `<span class="tip-muted">Click to open its ${cat.units} ${esc(cat.term)}</span>` : `<span class="tip-muted">No regional boundaries published</span>`}`;
    }
    const v = countryValue(row);
    const lv = levelOf(v);
    return `<strong>${esc(name)}</strong>${esc(meta().label)}: <b>${fmt(v)}</b>${v != null ? " / 100" : ""}${lv ? ` · ${esc(lv.label)}` : ""}<br>
      <span class="tip-muted">${cat ? `Click to open its ${cat.units} ${esc(cat.term)}` : "No regional boundaries published"}${S.layer === "vegetation" ? " · vegetation is computed per region" : ""}</span>`;
  }
  function drawWorld(geo) {
    worldLayer = L.geoJSON(geo, {
      style: worldStyle,
      // A few micro-states are points in the world file: draw them as dots, not Leaflet's default pin image.
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4 }),
      onEachFeature: (f, lyr) => {
        const iso = f.properties.iso2;
        if (f.properties.name) S.worldNames.set(iso, f.properties.name);
        worldPath.set(iso, lyr);
        lyr.bindTooltip(() => worldTip(iso), { sticky: true, direction: "top", className: "ds-map-tip", offset: [0, -10] });
        lyr.on({
          mouseover: () => { if (iso !== S.country) lyr.setStyle({ weight: 1.6, color: T.hover }); },
          mouseout: () => worldLayer.resetStyle(lyr),
          click: () => {
            if (iso === S.country) return;
            if (S.catalog.has(iso)) openCountry(iso, true);
            else toast(`${nameOf(iso)}: no first-level regions are published, so there is nothing to map below the national level.`);
          },
        });
      },
    }).addTo(map);
  }
  function restyle() {
    if (worldLayer) worldLayer.setStyle(worldStyle);
    if (regionLayer) { regionLayer.setStyle(regionStyle); regionPath.get(S.selected)?.bringToFront(); }
  }

  /* ---------------- region layer ---------------- */
  function regionStyle(f) {
    const code = f.properties.code;
    const w = S.byCode.get(code);
    const v = regionValue(w);
    const on = passes(v, f.properties.name);
    const sel = code === S.selected;
    return { fillColor: S.payload ? colorFor(v) : T.pending, fillOpacity: on ? (sel ? 0.95 : 0.86) : 0.12, color: sel ? T.select : T.line, weight: sel ? 3 : 0.9, opacity: on || sel ? 1 : 0.5 };
  }
  function regionTip(code) {
    const f = regionFeat.get(code);
    const name = f ? f.properties.name : code;
    if (!S.payload) return `<strong>${esc(name)}</strong><span class="tip-muted">Computing live layers…</span>`;
    const v = regionValue(S.byCode.get(code));
    const lv = levelOf(v);
    return `<strong>${esc(name)}</strong>${esc(meta().label)}: <b>${fmt(v)}</b>${v != null ? " / 100" : ""}${lv ? ` · ${esc(lv.label)}` : ""}<br>
      <span class="tip-muted">${S.month && hasHistory(S.layer) ? monthLabel(S.month) : "Latest"} · click for details</span>`;
  }
  function clearRegions() {
    S.mainBounds = null;
    [regionLayer, labelLayer, damLayer].forEach((l) => l && map.removeLayer(l));
    regionLayer = labelLayer = damLayer = null;
    regionPath.clear(); regionFeat.clear();
  }
  function drawRegions(geo) {
    clearRegions();
    regionLayer = L.geoJSON(geo, {
      style: regionStyle,
      onEachFeature: (f, lyr) => {
        const code = f.properties.code;
        regionPath.set(code, lyr); regionFeat.set(code, f);
        lyr.bindTooltip(() => regionTip(code), { sticky: true, direction: "top", className: "ds-map-tip", offset: [0, -10] });
        lyr.on({
          mouseover: () => { if (code !== S.selected) { lyr.setStyle({ weight: 2, color: T.hover }); lyr.bringToFront(); regionPath.get(S.selected)?.bringToFront(); } },
          mouseout: () => regionLayer && regionLayer.resetStyle(lyr),
          click: () => S.payload && select(code, true),
        });
      },
    }).addTo(map);
    labelLayer = L.layerGroup(geo.features.map((f) => L.marker([f.properties.label_lat, f.properties.label_lon], {
      interactive: false, keyboard: false, bbox: f.properties.bbox, area: f.properties.area_km2, labelText: f.properties.name,
      icon: L.divIcon({ className: "mv-label", html: `<span>${esc(f.properties.name)}</span>`, iconSize: null }),
    })));
    updateLabels();
    S.mainBounds = mainBounds(geo.features);
    const box = map.getSize();
    map.flyToBounds(S.mainBounds || regionLayer.getBounds(), { padding: box.x > 700 ? [28, 28] : [12, 12], duration: 0.8 });
  }
  // Frame the main territory: regions whose bounding boxes touch form clusters (union-find); fit the
  // largest cluster when it holds most regions. Keeps e.g. the contiguous US in view instead of the whole
  // Pacific; Alaska, Hawaii or overseas departments stay one zoom-out away.
  function mainBounds(features) {
    const n = features.length;
    if (n < 4) return null;
    const bb = features.map((f) => f.properties.bbox);
    const parent = bb.map((_, i) => i);
    const find = (i) => (parent[i] === i ? i : (parent[i] = find(parent[i])));
    const tol = 0.6;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = bb[i], b = bb[j];
      if (a[0] - tol <= b[2] && b[0] - tol <= a[2] && a[1] - tol <= b[3] && b[1] - tol <= a[3]) parent[find(i)] = find(j);
    }
    const groups = new Map();
    bb.forEach((_, i) => { const r = find(i); groups.set(r, (groups.get(r) || []).concat(i)); });
    const biggest = [...groups.values()].sort((a, b) => b.length - a.length)[0];
    if (groups.size === 1 || biggest.length < n * 0.6) return null;
    const xs = biggest.flatMap((i) => [bb[i][0], bb[i][2]]), ys = biggest.flatMap((i) => [bb[i][1], bb[i][3]]);
    return L.latLngBounds([Math.min(...ys), Math.min(...xs)], [Math.max(...ys), Math.max(...xs)]);
  }
  function updateLabels() {
    if (!labelLayer || !map) return;
    const on = $("#mv-labels").checked;
    // Greedy collision avoidance: larger regions claim their label space first; a label that would
    // overlap one already placed waits for a closer zoom.
    const placed = [];
    const items = [];
    labelLayer.eachLayer((m) => items.push(m));
    items.sort((a, b) => (b.options.area || 0) - (a.options.area || 0));
    items.forEach((m) => {
      const b = m.options.bbox;
      let show = on;
      if (show && b) {
        const p1 = map.latLngToContainerPoint([b[1], b[0]]), p2 = map.latLngToContainerPoint([b[3], b[2]]);
        show = Math.abs(p2.x - p1.x) > 46 && Math.abs(p1.y - p2.y) > 18;
      }
      if (show) {
        const c = map.latLngToContainerPoint(m.getLatLng());
        const w = (m.options.labelText || "").length * 6.4 + 10, h = 17;
        const r = { x0: c.x - w / 2, x1: c.x + w / 2, y0: c.y - h / 2, y1: c.y + h / 2 };
        show = !placed.some((q) => r.x0 < q.x1 && r.x1 > q.x0 && r.y0 < q.y1 && r.y1 > q.y0);
        if (show) placed.push(r);
      }
      if (show && !map.hasLayer(m)) m.addTo(map);
      if (!show && map.hasLayer(m)) map.removeLayer(m);
    });
  }
  function toggleDams() {
    const on = $("#mv-dams").checked;
    if (damLayer) { map.removeLayer(damLayer); damLayer = null; }
    if (on && S.mode === "country" && S.payload) {
      const markers = [];
      S.payload.regions.forEach((w) => (w.dams || []).forEach((d) => {
        if (d.lat == null) return;
        const lon = regionFeat.get(w.code) && regionFeat.get(w.code).properties.label_lon > 180 && d.lon < 0 ? d.lon + 360 : d.lon;
        markers.push(L.circleMarker([d.lat, lon], { radius: d.monitored ? 6 : 4, color: T.line, weight: 1.2, fillColor: d.monitored ? "#34c9b8" : "#c9d1cb", fillOpacity: 0.95 })
          .bindPopup(`<strong>${esc(d.name)}</strong><br>${esc(w.name)} · ${d.capacity_mm3 ? `${d.capacity_mm3} Mm³` : "capacity n/a"}<br>${d.monitored ? "Monitored" : "Catalogued only"}<br><a href="${esc(d.url)}">Open dam sheet →</a>`));
      }));
      damLayer = L.layerGroup(markers).addTo(map);
    } else if (on && S.mode === "world") {
      toast("Open a country to see its dams.");
    }
    renderLegend();
  }

  /* ---------------- overlays ---------------- */
  function loading(on, text, sub) {
    $("#mv-loading").hidden = !on;
    if (text) $("#mv-loading-text").textContent = text;
    $("#mv-loading-sub").textContent = sub || "";
    if (!on) $("#mv-progress").hidden = true;
  }
  function progress(job, units) {
    const total = job && job.total ? job.total : units || 0;
    const done = job && job.stage === "climate" ? job.done : job && ["events", "dams", "compute", "saving", "done"].includes(job.stage) ? total : 0;
    $("#mv-progress").hidden = false;
    $("#mv-progress-bar").style.width = `${total ? Math.max(4, (done / total) * 100) : 6}%`;
    loading(true, `Computing ${nameOf(S.country)}'s ${units || ""} ${S.catalog.get(S.country)?.term || "regions"}…`,
      `${job ? job.label || job.stage : "Starting"}${job && job.stage === "climate" ? ` · ${job.done}/${job.total}` : ""} — first visit only, about ${Math.max(10, Math.round((units || 20) * 0.8))} s`);
  }
  function fail(title, text, canRetry = true) {
    loading(false);
    $("#mv-error").hidden = false;
    $("#mv-error-title").textContent = title;
    $("#mv-error-text").textContent = text;
    $("#mv-retry").hidden = !canRetry;
  }

  /* ---------------- legend / controls ---------------- */
  function currentValues() {
    if (S.mode === "country" && S.payload) return S.payload.regions.map((w) => regionValue(w));
    return [...S.worldRows.values()].map((r) => countryValue(r));
  }
  function renderLegend() {
    const m = meta();
    const vals = currentValues();
    const lv = levels();
    const counts = lv.map((x) => vals.filter((v) => v != null && v >= x.lo && v < x.hi).length);
    const nodata = vals.filter((v) => v == null).length;
    const unit = S.mode === "country" ? termPlural() : "countries";
    $("#mv-legend").innerHTML = `
      <div class="mv-legend__title"><b>${esc(m.label)}</b><span>${S.mode === "country" && S.month && hasHistory(S.layer) ? esc(monthLabel(S.month)) : "Latest"}${m.direction === "health" ? " · proxy" : ""}</span></div>
      <div class="mv-legend__ramp" style="background:linear-gradient(90deg,${(m.direction === "health" ? [...RAMP].reverse() : RAMP).join(",")})"></div>
      <div class="mv-legend__scale"><span>0</span><span>${m.direction === "health" ? "drier ← → moister" : "lower ← → higher pressure"}</span><span>100</span></div>
      <div class="mv-legend__levels">${lv.map((x, i) => `<span><i style="background:${colorFor((x.lo + Math.min(100, x.hi)) / 2)}"></i>${esc(x.label)} <b class="num">${counts[i]}</b></span>`).join("")}${nodata ? `<span><i style="background:${T.nodata}"></i>No value <b class="num">${nodata}</b></span>` : ""}</div>
      <div class="mv-legend__unit">Counts are ${esc(unit)}${S.mode === "world" ? " · faded = no regional map published" : ""}</div>
      ${$("#mv-dams").checked && S.mode === "country" ? `<div class="mv-legend__levels"><span><i class="round" style="background:#34c9b8"></i>Monitored dam</span><span><i class="round" style="background:#c9d1cb"></i>Catalogued dam</span></div>` : ""}`;
  }
  function renderLayerButtons() {
    $$("#mv-layers [data-layer]").forEach((b) => {
      const l = b.dataset.layer;
      b.setAttribute("aria-checked", String(l === S.layer));
      b.classList.toggle("is-latest-only", S.mode === "country" && !!S.month && !hasHistory(l));
      const m = meta(l);
      b.dataset.tipTitle = m.label + (m.history ? "" : " · latest only");
      b.dataset.tip = m.detail;
    });
    $$("#mv-mobile-layers [data-layer]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.layer === S.layer)));
    const m = meta();
    $("#mv-layer-note").innerHTML = `${m.direction === "health" ? `<span class="ds-badge ds-badge--demo"><i></i>Proxy</span> ` : ""}${esc(m.short || "")} · <span class="ds-muted">${esc(m.source || "")}</span>`;
  }
  function renderLevels() {
    const box = $("#mv-levels");
    box.innerHTML = levels().map((x) => `<button type="button" class="ds-chip" data-level="${x.key}" aria-pressed="${!S.levelsOn || S.levelsOn.has(x.key)}"><i style="background:${colorFor((x.lo + Math.min(100, x.hi)) / 2)}"></i>${esc(x.label)}</button>`).join("");
    $$("[data-level]", box).forEach((b) => b.addEventListener("click", () => {
      const all = levels().map((x) => x.key);
      const cur = S.levelsOn ? new Set(S.levelsOn) : new Set(all);
      cur.has(b.dataset.level) ? cur.delete(b.dataset.level) : cur.add(b.dataset.level);
      S.levelsOn = cur.size === all.length ? null : cur;
      if (S.levelsOn && S.levelsOn.size === 0) { S.levelsOn = null; toast("At least one level stays visible — showing all."); }
      renderLevels(); restyle(); renderDetail();
    }));
  }
  function renderChrome() {
    const inCountry = S.mode === "country";
    const name = inCountry ? (S.payload && S.payload.country_name) || nameOf(S.country) : "";
    $("#mv-crumb-world").classList.toggle("is-current", !inCountry);
    $("#mv-crumb-sep").hidden = !inCountry;
    $("#mv-crumb-country").hidden = !inCountry;
    $("#mv-crumb-country").textContent = name;
    $("#mv-title").textContent = inCountry ? name : "Map viewer";
    const cat = inCountry ? S.catalog.get(S.country) : null;
    $("#mv-intro").textContent = inCountry
      ? `${cap(cat ? cat.term : termPlural())} of ${name}, computed from live NASA and Open-Meteo signals. Hover to read, click to explore.`
      : `Every country, region by region. ${S.catalog.size} countries publish first-level regions — pick one on the map or search for it.`;
    $("#mv-show-legend").textContent = inCountry ? `Show ${cat ? cat.term : "regions"}` : "Show countries";
    $("#mv-find").placeholder = inCountry ? `Find a ${term()}…` : "Find a country…";
    $("#mv-find-list").innerHTML = inCountry && S.payload
      ? S.payload.regions.map((w) => `<option value="${esc(w.name)}">`).join("")
      : [...S.worldRows.values()].map((r) => `<option value="${esc(r.name)}">`).join("");
    const sel = $("#mv-month");
    sel.disabled = !inCountry || !S.payload;
    if (inCountry && S.payload) {
      sel.innerHTML = `<option value="">Latest (live)</option>` + [...(S.payload.months || [])].reverse().map((m) => `<option value="${m}">${esc(monthLabel(m))}</option>`).join("");
      sel.value = S.month;
    } else sel.innerHTML = `<option value="">Latest (live)</option>`;
    $("#mv-month-hint").textContent = inCountry
      ? "Drought and vegetation moisture can be replayed month by month. Flood, fire and water stress are latest-only."
      : "Open a country to replay drought and vegetation moisture month by month.";
    renderMeta();
  }
  function renderMeta() {
    const box = $("#mv-meta");
    if (S.mode === "world") {
      box.innerHTML = `<p>Countries are coloured from the live world snapshot (NASA POWER, Open-Meteo, GloFAS, NASA EONET). <a href="/methodology/">How it's computed</a></p>
        <p class="ds-muted">Regional boundaries: geoBoundaries (licences vary by country and are shown inside each country). Countries: Natural Earth.</p>`;
      map.attributionControl.removeAttribution(map._mvAttr || "");
      map._mvAttr = "Countries: Natural Earth · Regions: geoBoundaries";
      map.attributionControl.addAttribution(map._mvAttr);
      return;
    }
    const p = S.payload;
    if (!p) { box.innerHTML = ""; return; }
    const g = p.geometry || {};
    const created = p.created_at ? new Date(p.created_at) : null;
    box.innerHTML = `
      <p><span class="ds-badge ds-badge--live"><i></i>Live data</span> Computed ${created ? esc(created.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" })) + " UTC" : ""}${p.refreshing ? " · <b>updating in the background</b>" : ""}</p>
      <p>${p.coverage.regions} ${esc(termPlural())} · NASA POWER, Open-Meteo, GloFAS, NASA EONET. <a href="/methodology/">How it's computed</a></p>
      <p class="ds-muted">Boundaries: ${esc(g.source || "geoBoundaries")}, ${esc(g.license || "")}${g.boundary_year ? `, year ${esc(g.boundary_year)}` : ""}${g.generalised ? " · outlines lightly generalised for display" : ""}. Shown as published by the source; not an official or legal boundary and no position on territorial claims.</p>
      <button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" id="mv-reset-all">Reset filters &amp; view</button>`;
    $("#mv-reset-all").addEventListener("click", resetAll);
    map.attributionControl.removeAttribution(map._mvAttr || "");
    map._mvAttr = `Regions: ${g.source || "geoBoundaries"} (${g.license || "see source"}) · Countries: Natural Earth`;
    map.attributionControl.addAttribution(map._mvAttr);
  }

  /* ---------------- detail panel ---------------- */
  function spark(series, key, color, isHealth) {
    const pts = series.map((h, i) => ({ i, v: h[key], m: h.month })).filter((p) => p.v != null);
    if (pts.length < 2) return `<p class="ds-muted">Not enough monthly data.</p>`;
    const W = 300, H = 74, n = series.length - 1;
    const x = (i) => 6 + (i / n) * (W - 12), y = (v) => 6 + (1 - v / 100) * (H - 12);
    const line = pts.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
    const area = `${line} L${x(pts[pts.length - 1].i).toFixed(1)} ${H - 6} L${x(pts[0].i).toFixed(1)} ${H - 6} Z`;
    const mi = S.month ? series.findIndex((h) => h.month === S.month) : series.length - 1;
    const mk = series[mi];
    return `<svg class="mv-spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(key)} over the last ${series.length} months">
      <line x1="6" x2="${W - 6}" y1="${y(50)}" y2="${y(50)}" class="mv-spark__mid"/>
      <path d="${area}" fill="${color}" opacity=".14"/><path d="${line}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
      ${mk && mk[key] != null ? `<circle cx="${x(mi).toFixed(1)}" cy="${y(mk[key]).toFixed(1)}" r="4.5" fill="#fff" stroke="${color}" stroke-width="2"/>` : ""}
      ${pts.map((p) => `<circle cx="${x(p.i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="9" fill="transparent" data-month="${p.m}"><title>${monthLabel(p.m)}: ${fmt(p.v)}</title></circle>`).join("")}
    </svg><div class="mv-spark__axis"><span>${esc(monthLabel(series[0].month))}</span><span>${isHealth ? "50 = normal for the month" : "50 = neutral"}</span><span>${esc(monthLabel(series[series.length - 1].month))}</span></div>`;
  }
  function rankList(items, onClickAttr, unitLabel) {
    const m = meta();
    const sorted = items.sort((a, b) => (m.direction === "health" ? a.v - b.v : b.v - a.v)).slice(0, 12);
    if (!sorted.length) return `<li class="ds-state"><strong>Nothing matches</strong><span>Loosen the level filter or clear the search.</span></li>`;
    return sorted.map((x) => `<li><button type="button" ${onClickAttr}="${esc(x.key)}">
      <span class="mv-rank__code num">${esc(x.tag)}</span><span class="mv-rank__name">${esc(x.name)}</span>
      <span class="mv-rank__bar"><i style="width:${Math.max(2, x.v)}%;background:${colorFor(x.v)}"></i></span><b class="num">${fmt(x.v)}</b></button></li>`).join("");
  }
  function statsHtml(vals, unit) {
    const s = vals.filter((v) => v != null).sort((a, b) => a - b);
    const mean = s.reduce((a, v) => a + v, 0) / Math.max(1, s.length);
    const lv = levels();
    const counts = lv.map((x) => s.filter((v) => v >= x.lo && v < x.hi).length);
    return `<div class="mv-stats"><div><span>Average</span><b class="num">${fmt(s.length ? mean : null)}</b></div><div><span>Median</span><b class="num">${fmt(s.length ? s[Math.floor(s.length / 2)] : null)}</b></div><div><span>${esc(cap(unit))}</span><b class="num">${s.length}</b></div></div>
      <div class="mv-stack" role="group" aria-label="Per level — click to filter">${lv.map((x, i) => `<button type="button" style="flex:${counts[i] || 0.0001};background:${colorFor((x.lo + Math.min(100, x.hi)) / 2)}" data-only="${x.key}" data-tip-title="${esc(x.label)} · ${counts[i]}" data-tip="Click to show only these."></button>`).join("")}</div>`;
  }
  function worldSummaryHtml() {
    const m = meta();
    const items = [...S.worldRows.values()].map((r) => ({ key: r.iso2, tag: r.iso2, name: r.name, v: countryValue(r) }))
      .filter((x) => x.v != null && passes(x.v, x.name) && S.catalog.has(x.key));
    const ready = [...S.catalog.values()].filter((c) => c.ready).slice(0, 10);
    return `<p class="ds-eyebrow">The world, country by country</p><h2>${esc(m.label)}</h2>
      <p class="mv-detail__lede">${esc(m.detail)}</p>
      ${S.layer === "vegetation" ? `<p class="mv-note">Vegetation moisture exists only per region. Open a country to see it.</p>` : statsHtml(currentValues(), "countries")}
      <h3 class="mv-h3">${m.direction === "health" ? "Open a country" : "Highest pressure"} <span class="ds-muted">· click to open its regions</span></h3>
      <ol class="mv-rank">${S.layer === "vegetation" ? "" : rankList(items, "data-country", "countries")}</ol>
      ${ready.length ? `<h3 class="mv-h3">Already computed</h3><div class="mv-ready">${ready.map((c) => `<button type="button" class="ds-chip" data-country="${c.iso2}">${esc(nameOf(c.iso2))}</button>`).join("")}</div>` : ""}`;
  }
  function countrySummaryHtml() {
    const m = meta();
    const p = S.payload;
    const items = p.regions.map((w) => ({ key: w.code, tag: w.code.split("-").pop(), name: w.name, v: regionValue(w) })).filter((x) => x.v != null && passes(x.v, x.name));
    return `<p class="ds-eyebrow">${esc(p.country_name || nameOf(S.country))} at a glance</p><h2>${esc(m.label)}</h2>
      <p class="mv-detail__lede">${esc(m.detail)}</p>${statsHtml(currentValues(), termPlural())}
      <h3 class="mv-h3">${m.direction === "health" ? "Driest first" : "Highest first"} <span class="ds-muted">· ${S.month && hasHistory(S.layer) ? esc(monthLabel(S.month)) : "latest"}</span></h3>
      <ol class="mv-rank">${rankList(items, "data-select", termPlural())}</ol>
      <div class="mv-actions"><a class="ds-btn ds-btn--ghost ds-btn--sm" href="/country/${esc(S.country)}/">Country sheet</a><a class="ds-btn ds-btn--ghost ds-btn--sm" href="/water/${esc(S.country)}/">Water runway</a></div>`;
  }
  function regionHtml(w) {
    const m = meta();
    const v = regionValue(w);
    const lv = levelOf(v);
    const inp = w.inputs || {};
    const fl = inp.flood || {};
    const rows = Object.entries(S.payload.layers).map(([key, lm]) => {
      const latestOnly = S.month && !lm.history;
      const val = latestOnly ? w.layers[key] : regionValue(w, key);
      return `<button type="button" class="mv-ind${key === S.layer ? " is-active" : ""}" data-layer-jump="${key}" data-tip-title="${esc(lm.label)}" data-tip="${esc(lm.detail)}">
        <i class="mv-ico mv-ico--${ICON[key]}"></i><span class="mv-ind__name">${esc(lm.label)}${lm.direction === "health" ? ' <em class="mv-proxy">proxy</em>' : ""}<small>${latestOnly ? "latest only" : (levelOf(val, key) || {}).label || "no signal"}</small></span>
        <span class="mv-ind__bar"><i style="width:${val == null ? 0 : Math.max(2, val)}%;background:${colorFor(val, key)}"></i></span><b class="num">${fmt(val)}</b></button>`;
    }).join("");
    const dams = w.dams || [];
    const events = (S.payload.events || []).filter((e) => e.code === w.code);
    return `<div class="mv-detail__top"><button type="button" class="ds-btn ds-btn--quiet ds-btn--sm" data-back>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12 5 7 10l5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>All ${esc(termPlural())}</button>
        <span class="mv-code num">${esc(cap(term()))} ${esc(w.code.split("-").pop())}</span></div>
      <h2 class="mv-name">${esc(w.name)}</h2>
      <p class="ds-muted mv-sub">${w.area_km2 ? `${Number(w.area_km2).toLocaleString("en-GB")} km² · ` : ""}${esc(S.payload.country_name || "")} · sampled at ${fmt(w.lat, 2)}°, ${fmt(w.lon, 2)}°</p>
      <div class="mv-hero-val" style="--c:${colorFor(v)}"><div><span>${esc(m.label)} · ${S.month && hasHistory(S.layer) ? esc(monthLabel(S.month)) : "latest"}</span><strong class="num">${fmt(v)}</strong><small>/100</small></div>
        ${lv ? `<span class="mv-level" style="background:${colorFor(v)}">${esc(lv.label)}</span>` : `<span class="mv-level mv-level--none">No signal</span>`}</div>
      <h3 class="mv-h3">All indicators <span class="ds-muted">· click to map one</span></h3><div class="mv-inds">${rows}</div>
      <h3 class="mv-h3">Last 12 months</h3>
      <div class="mv-trends"><div><span class="mv-trend__label"><i style="background:#e5a23b"></i>Drought pressure</span>${spark(w.history || [], "drought", "#e5a23b", false)}</div>
        <div><span class="mv-trend__label"><i style="background:#55c98a"></i>Vegetation moisture (proxy)</span>${spark(w.history || [], "vegetation", "#55c98a", true)}</div></div>
      <details class="mv-inputs"><summary>Model inputs and sources</summary><dl>
        <div><dt>Aridity index (P / PET)</dt><dd class="num">${fmt(inp.aridity_index, 3)}</dd></div>
        <div><dt>Mean annual rain</dt><dd class="num">${fmt(inp.annual_precip_mm)} mm</dd></div>
        <div><dt>Potential evapotranspiration</dt><dd class="num">${fmt(inp.annual_pet_mm)} mm</dd></div>
        <div><dt>Rainfall trend</dt><dd class="num">${fmt(inp.precip_trend_pct_per_year, 1)} %/yr</dd></div>
        <div><dt>SPI-3 / SPI-12 percentile</dt><dd class="num">${fmt(inp.spi3_percentile)} / ${fmt(inp.spi12_percentile)}</dd></div>
        <div><dt>Root-zone soil percentile</dt><dd class="num">${fmt(inp.soil_percentile)}</dd></div>
        <div><dt>Days since &gt;2 mm rain</dt><dd class="num">${fmt(inp.dry_days)}</dd></div>
        <div><dt>Forecast discharge peak ÷ median</dt><dd class="num">${fmt(fl.forecast_peak_ratio, 2)}</dd></div>
        <div><dt>Latest NASA POWER month</dt><dd>${esc(monthLabel((inp.latest_month || "").slice(0, 7)))}</dd></div></dl>
        <p class="ds-muted">Sampled at one interior point. NASA POWER is a ~0.5° grid, so small neighbouring ${esc(termPlural())} can share a cell.</p></details>
      <h3 class="mv-h3">Largest dams here <span class="ds-muted">· ${w.dam_count ?? dams.length}</span></h3>
      ${dams.length ? `<ul class="mv-dams">${dams.slice(0, 6).map((d) => `<li><a href="${esc(d.url)}"><span>${esc(d.name)}</span><small>${d.monitored ? '<span class="ds-badge ds-badge--live"><i></i>monitored</span>' : "catalogued"}</small><b class="num">${d.capacity_mm3 ? `${d.capacity_mm3} Mm³` : ""}</b></a></li>`).join("")}</ul>` : `<p class="ds-muted">No catalogued dam from the atlas falls inside this ${esc(term())}.</p>`}
      ${events.length ? `<h3 class="mv-h3">Active events</h3><ul class="mv-dams">${events.map((e) => `<li><a href="${esc(e.url || "#")}" target="_blank" rel="noopener"><span>${esc(e.title)}</span><small>${esc(e.category)}</small></a></li>`).join("")}</ul>` : ""}
      <div class="mv-actions"><a class="ds-btn ds-btn--sm" href="/water/${esc(S.country)}/">${esc(S.payload.country_name || "")} water runway</a><a class="ds-btn ds-btn--ghost ds-btn--sm" href="/country/${esc(S.country)}/">Country sheet</a></div>`;
  }
  function renderDetail() {
    const box = $("#mv-detail-inner");
    if (S.mode === "world") box.innerHTML = worldSummaryHtml();
    else if (!S.payload) box.innerHTML = `<p class="ds-eyebrow">${esc(nameOf(S.country))}</p><h2>Preparing the regional map</h2><p class="mv-detail__lede">Boundaries appear first; colours follow as soon as the live layers are computed.</p><span class="ds-skeleton" style="height:240px"></span>`;
    else {
      const w = S.selected && S.byCode.get(S.selected);
      box.innerHTML = w ? regionHtml(w) : countrySummaryHtml();
    }
    box.classList.remove("ds-enter"); void box.offsetWidth; box.classList.add("ds-enter");
    $$("[data-select]", box).forEach((b) => b.addEventListener("click", () => select(b.dataset.select, true)));
    $$("[data-country]", box).forEach((b) => b.addEventListener("click", () => openCountry(b.dataset.country, true)));
    $$("[data-layer-jump]", box).forEach((b) => b.addEventListener("click", () => setLayer(b.dataset.layerJump)));
    $$("[data-only]", box).forEach((b) => b.addEventListener("click", () => { S.levelsOn = new Set([b.dataset.only]); renderLevels(); restyle(); renderDetail(); renderLegend(); }));
    $("[data-back]", box)?.addEventListener("click", () => { select(null); fitCountry(); });
    $$(".mv-spark circle[data-month]", box).forEach((c) => c.addEventListener("click", () => { $("#mv-month").value = c.dataset.month; setMonth(c.dataset.month); }));
  }

  /* ---------------- actions ---------------- */
  function setLayer(next) {
    if (!BASE_LAYERS[next]) return;
    if (S.mode === "country" && S.month && !hasHistory(next)) {
      S.month = ""; $("#mv-month").value = "";
      toast(`${meta(next).label} is only available for the latest period — switched to Latest.`);
    }
    if (dirOf(next) !== dirOf(S.layer)) S.levelsOn = null;
    S.layer = next;
    renderLayerButtons(); renderLevels(); restyle(); renderLegend(); renderDetail(); syncUrl();
  }
  function setMonth(m) {
    S.month = m;
    if (m && !hasHistory(S.layer)) { const prev = meta().label; S.layer = "drought"; toast(`${prev} has no monthly history — showing drought for ${monthLabel(m)}.`); }
    renderLayerButtons(); restyle(); renderLegend(); renderDetail(); syncUrl();
  }
  function select(code, fly, fromUser = true) {
    const prev = S.selected;
    S.selected = code && S.byCode.has(code) ? code : null;
    if (prev && regionPath.get(prev)) regionLayer.resetStyle(regionPath.get(prev));
    const lyr = S.selected && regionPath.get(S.selected);
    if (lyr) {
      regionLayer.resetStyle(lyr); lyr.bringToFront();
      const el = lyr.getElement && lyr.getElement();
      if (el) { el.classList.remove("mv-sel"); void el.getBoundingClientRect(); el.classList.add("mv-sel"); }
      if (fly) map.flyToBounds(lyr.getBounds(), { padding: [60, 60], maxZoom: 8, duration: 0.8 });
    }
    renderDetail(); syncUrl();
    if (S.selected && fromUser && window.innerWidth < 1100) $("#mv-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function fitCountry() {
    if (regionLayer) map.flyToBounds(S.mainBounds || regionLayer.getBounds(), { padding: [24, 24], duration: 0.7 });
    else if (S.mode === "world") map.flyTo([20, 10], 2, { duration: 0.7 });
  }
  function resetAll() {
    S.levelsOn = null; S.query = ""; S.month = ""; $("#mv-find").value = ""; $("#mv-month").value = "";
    if (S.mode === "country") select(null); renderLevels(); renderLayerButtons(); restyle(); renderLegend(); renderDetail(); fitCountry(); syncUrl();
  }

  function goWorld(push) {
    S.loadToken++;
    clearTimeout(S.poll);
    S.mode = "world"; S.country = null; S.payload = null; S.byCode = new Map(); S.selected = null; S.month = ""; S.query = "";
    $("#mv-find").value = ""; $("#mv-error").hidden = true; loading(false);
    clearRegions();
    if (S.layer === "vegetation") S.levelsOn = null;
    renderChrome(); renderLayerButtons(); renderLevels(); restyle(); renderLegend(); renderDetail();
    map.flyTo([20, 10], 2, { duration: 0.8 });
    syncUrl(push);
  }

  async function openCountry(iso2, push, preselect) {
    iso2 = (iso2 || "").toUpperCase();
    if (!S.catalog.has(iso2)) {
      if (push === false) {
        // Arrived by URL: say so clearly instead of silently staying on the world map.
        renderChrome(); renderLayerButtons(); renderLevels(); restyle(); renderLegend(); renderDetail();
        fail(`No regional map for ${nameOf(iso2)}`, "geoBoundaries publishes no first-level regions for this country, so there is nothing to map below the national level.", false);
      } else toast(`${nameOf(iso2)}: no first-level regions are published.`);
      return;
    }
    const token = ++S.loadToken;
    clearTimeout(S.poll);
    S.mode = "country"; S.country = iso2; S.payload = null; S.byCode = new Map(); S.selected = null; S.query = ""; S.levelsOn = null;
    if (push !== false) S.month = "";
    $("#mv-find").value = ""; $("#mv-error").hidden = true; $("#mv-country").value = "";
    root.dataset.controls = "closed";
    renderChrome(); renderLevels(); restyle(); renderDetail(); syncUrl(push);
    const cat = S.catalog.get(iso2);
    loading(true, `Loading ${nameOf(iso2)}'s ${cat.term}…`);
    try {
      const geoRes = await fetch(`/api/regions/${iso2}/geo/`);
      if (token !== S.loadToken) return;
      if (!geoRes.ok) {
        const e = await geoRes.json().catch(() => ({}));
        fail(`No regional map for ${nameOf(iso2)}`, e.message || "The boundary file could not be downloaded.", geoRes.status !== 404);
        return;
      }
      const geo = await geoRes.json();
      if (token !== S.loadToken) return;
      drawRegions(geo);
      await pollRegions(iso2, token, cat.units, preselect);
    } catch (err) {
      if (token === S.loadToken) fail("The regional map could not load", "Check the server is running, then retry.");
    }
  }

  async function pollRegions(iso2, token, units, preselect, retry) {
    const res = await fetch(`/api/regions/${iso2}/${retry ? "?retry=1" : ""}`);
    if (token !== S.loadToken) return;
    const data = await res.json().catch(() => ({}));
    if (res.status === 404) { fail(`No regional map for ${nameOf(iso2)}`, data.message || "No regions are published.", false); return; }
    if (data.status === "error") { fail(`Couldn't compute ${nameOf(iso2)}'s layers`, `${data.message || "A live source failed."} Retry in a moment.`); return; }
    if (data.status === "building") {
      progress(data.job, data.units || units);
      S.poll = setTimeout(() => pollRegions(iso2, token, units, preselect), 1500);
      return;
    }
    S.payload = data;
    S.byCode = new Map(data.regions.map((w) => [w.code, w]));
    const c = S.catalog.get(iso2); if (c) c.ready = true;
    if (S.month && !(data.months || []).includes(S.month)) S.month = "";
    loading(false);
    renderChrome(); renderLayerButtons(); renderLevels(); restyle(); renderLegend(); toggleDams();
    if (preselect && S.byCode.has(preselect)) select(preselect, true, false);
    else renderDetail();
    if (data.refreshing) toast(`Showing the stored map of ${data.country_name}; fresh values are being computed.`);
  }

  /* ---------------- wiring ---------------- */
  $$("#mv-layers [data-layer], #mv-mobile-layers [data-layer]").forEach((b) => b.addEventListener("click", () => setLayer(b.dataset.layer)));
  $("#mv-layers").addEventListener("keydown", (e) => {
    if (!["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft"].includes(e.key)) return;
    e.preventDefault();
    const btns = $$("#mv-layers [data-layer]");
    const i = btns.findIndex((b) => b.dataset.layer === S.layer);
    const next = btns[(i + (e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1) + btns.length) % btns.length];
    setLayer(next.dataset.layer); next.focus();
  });
  $("#mv-month").addEventListener("change", (e) => setMonth(e.target.value));
  $("#mv-find").addEventListener("input", (e) => {
    S.query = fold(e.target.value.trim());
    restyle(); renderDetail();
    if (S.mode === "country" && S.payload) {
      const exact = S.payload.regions.find((w) => fold(w.name) === S.query);
      if (exact) select(exact.code, true);
    } else if (S.mode === "world") {
      const exact = [...S.worldRows.values()].find((r) => fold(r.name) === S.query);
      if (exact && S.catalog.has(exact.iso2)) openCountry(exact.iso2, true);
    }
  });
  $("#mv-country").addEventListener("change", (e) => {
    const q = fold(e.target.value.trim());
    const hit = [...S.catalog.keys()].map((iso) => ({ iso, n: fold(nameOf(iso)) })).find((x) => x.n === q || x.iso.toLowerCase() === q)
      || [...S.catalog.keys()].map((iso) => ({ iso, n: fold(nameOf(iso)) })).find((x) => x.n.startsWith(q));
    if (hit) openCountry(hit.iso, true);
    else if (q) toast("No regional map for that country — try another name.");
  });
  $("#mv-crumb-world").addEventListener("click", () => S.mode === "country" && goWorld(true));
  $("#mv-error-world").addEventListener("click", () => goWorld(true));
  $("#mv-retry").addEventListener("click", () => {
    $("#mv-error").hidden = true;
    if (S.mode === "country" && S.country) {
      if (!regionLayer) openCountry(S.country, false);
      else { loading(true, "Retrying…"); pollRegions(S.country, S.loadToken, S.catalog.get(S.country)?.units, S.selected, true); }
    } else boot();
  });
  $("#mv-labels").addEventListener("change", updateLabels);
  $("#mv-dams").addEventListener("change", toggleDams);
  $("#mv-reset").addEventListener("click", fitCountry);
  $("#mv-open-controls").addEventListener("click", (e) => {
    const open = root.dataset.controls !== "open";
    root.dataset.controls = open ? "open" : "closed";
    e.currentTarget.setAttribute("aria-expanded", String(open));
    e.currentTarget.textContent = open ? "Close filters" : "Filters";
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || document.querySelector("dialog[open]")) return;
    if (S.selected) { select(null); fitCountry(); } else if (S.mode === "country") goWorld(true);
  });
  window.addEventListener("popstate", () => {
    const q = new URLSearchParams(location.search);
    const c = (q.get("c") || "").toUpperCase();
    S.layer = q.get("layer") || S.layer;
    S.month = q.get("month") || "";
    if (c && c !== S.country) openCountry(c, false, (q.get("w") || "").toUpperCase());
    else if (!c && S.mode === "country") goWorld(false);
  });

  /* ---------------- boot ---------------- */
  async function boot() {
    loading(true, "Loading the world map…");
    try {
      if (!window.L) throw new Error("Leaflet missing");
      if (!map) initMap();
      const [geo, world, cat] = await Promise.all([
        fetch(root.dataset.worldGeo).then((r) => { if (!r.ok) throw new Error("geo"); return r.json(); }),
        fetch(root.dataset.worldApi).then((r) => r.json()).catch(() => ({ countries: [] })),
        fetch(root.dataset.catalog).then((r) => r.json()),
      ]);
      S.worldRows = new Map((world.countries || []).map((r) => [r.iso2, r]));
      S.catalog = new Map((cat.countries || []).map((c) => [c.iso2, c]));
      if (!worldLayer) drawWorld(geo);
      $("#mv-country-list").innerHTML = [...S.catalog.keys()].map((iso) => nameOf(iso)).sort().map((n) => `<option value="${esc(n)}">`).join("");
      loading(false);
      new ResizeObserver(() => { map.invalidateSize(); updateLabels(); }).observe($("#mv-map"));
      const c = (root.dataset.initialCountry || "").toUpperCase();
      if (c) openCountry(c, false, (root.dataset.initialRegion || "").toUpperCase());
      else { renderChrome(); renderLayerButtons(); renderLevels(); restyle(); renderLegend(); renderDetail(); }
    } catch (err) {
      fail("The map could not load", "The world boundaries or the region catalogue did not answer. Check the server, then retry.");
    }
  }
  boot();
  /* ---------------- theme switch: recolour in place, keep country, selection and filters ---------------- */
  window.addEventListener("ds:theme", () => {
    readTheme();
    restyle(); renderLegend(); renderLevels(); renderDetail();
    if (damLayer) toggleDams();
  });
})();
