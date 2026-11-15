/* Overview dashboard: world explorer, ranking, distribution, Algeria preview, alerts.
   Every number comes from /api/world/, /api/algeria/wilayas/ or /api/events/. */
(function () {
  "use strict";
  const esc = (v) => (window.DS ? window.DS.esc(v) : String(v == null ? "" : v));
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const el = $("#world-map");
  if (!el) return;

  /* ---------------- constants ---------------- */
  const STATUS = { resilient: "#55c98a", stable: "#4aa3a2", watch: "#e5a23b", stressed: "#e07a3f", critical: "#ef6f72", no_data: "#2a3d40" };
  const STATUS_LABEL = { resilient: "Resilient", stable: "Stable", watch: "Watch", stressed: "Stressed", critical: "Critical", no_data: "No data" };
  const BANDS = ["resilient", "stable", "watch", "stressed", "critical"];
  const RAMP = ["#2b6f6a", "#8fae5a", "#e5a23b", "#e07a3f", "#ef6f72"];
  const CAT_COLORS = { drought: "#e5a23b", floods: "#5ba7e8", wildfires: "#ef6f72", dustHaze: "#b18a5c", tempExtremes: "#c084fc", severeStorms: "#8fb3ff" };
  const CAT_LABEL = { drought: "Drought", floods: "Flood", wildfires: "Wildfire", dustHaze: "Dust & haze", tempExtremes: "Temperature extreme" };
  const LAYER_INFO = {
    index: { label: "Resilience index", top: "Most resilient", bottom: "Least resilient", unit: "/100 index", higherBetter: true },
    drought: { label: "Drought pressure", top: "Highest drought pressure", bottom: "Lowest drought pressure", unit: "/100 pressure" },
    flood: { label: "Flood pressure", top: "Highest flood pressure", bottom: "Lowest flood pressure", unit: "/100 pressure" },
    fire: { label: "Wildfire pressure", top: "Highest wildfire pressure", bottom: "Lowest wildfire pressure", unit: "/100 pressure" },
    desertification: { label: "Desertification pressure", top: "Highest desertification pressure", bottom: "Lowest desertification pressure", unit: "/100 pressure" },
  };
  const RANK_EXCLUDE = new Set(["AQ", "BV", "HM", "SJ", "UM", "TF", "GS", "IO"]);

  /* ---------------- state ---------------- */
  let data = {};
  try { data = JSON.parse($("#world-data")?.textContent || "{}"); } catch (e) { data = {}; }
  let rows = new Map((data.countries || []).map((r) => [r.iso2, r]));
  let version = data.version || null;
  let layer = "index";
  let rankDir = "top";
  let bandFilter = null; // Set of bands
  let rangeFilter = null; // [lo, hi]
  let selected = null;
  let geo = null, damsLayer = null, eventsLayer = null;
  const pathByIso = new Map();

  /* ---------------- helpers ---------------- */
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  function ramp(p) {
    if (p == null || Number.isNaN(Number(p))) return T.nodata;
    const v = Math.max(0, Math.min(100, Number(p))) / 100 * (RAMP.length - 1);
    const i = Math.min(RAMP.length - 2, Math.floor(v));
    const a = hex(RAMP[i]), b = hex(RAMP[i + 1]), t = v - i;
    return `rgb(${a.map((c, k) => Math.round(c + (b[k] - c) * t)).join(",")})`;
  }
  const valueOf = (row, l = layer) => !row ? null : l === "index" ? row.score : (row.hazards || {})[l];
  const colorOf = (row) => !row ? T.nodata : layer === "index" ? (STATUS[row.status] || T.nodata) : ramp(valueOf(row));
  function passes(row) {
    if (!row) return !bandFilter && !rangeFilter;
    if (bandFilter && !bandFilter.has(row.status)) return false;
    if (rangeFilter) {
      const v = valueOf(row);
      if (v == null || v < rangeFilter[0] || v >= rangeFilter[1] + (rangeFilter[1] >= 100 ? 0.001 : 0)) return false;
    }
    return true;
  }
  /* ---------------- theme colours (read from the CSS theme tokens; refreshed on ds:theme) ---------------- */
  const T = {};
  function readTheme() {
    const c = (name, fallback) => (window.DS && window.DS.cssVar(name)) || fallback;
    T.nodata = c("--t-nodata", "#2a3d40"); T.line = c("--t-map-line", "#0a1416"); T.hover = c("--t-map-hover", "#edf5f4");
    T.select = c("--t-map-select", "#ffffff"); T.land = c("--t-map-land", "#0f1c1f"); T.edge = c("--t-map-edge", "#1f3337");
    T.pending = c("--t-raised-2", "#1d3236");
  }
  readTheme();
  const fmt = (v, d = 0) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));

  /* ---------------- map ---------------- */
  if (!window.L) { $("#map-fallback").hidden = false; $("#map-loading")?.remove(); return; }
  const map = L.map(el, { worldCopyJump: true, minZoom: 1, maxZoom: 7, zoomSnap: 0.25, attributionControl: false, scrollWheelZoom: false }).setView([20, 12], 1.75);
  el.addEventListener("click", () => map.scrollWheelZoom.enable(), { once: true });

  function style(feature) {
    const iso = feature.properties.iso2;
    const row = rows.get(iso);
    const on = passes(row);
    const isSel = iso === selected;
    return {
      fillColor: colorOf(row),
      fillOpacity: on ? (isSel ? 0.98 : 0.82) : 0.12,
      color: isSel ? T.select : T.line,
      weight: isSel ? 2.4 : 0.6,
      opacity: 1,
      className: isSel ? "ov-selected" : "",
    };
  }
  function tipHtml(iso, name) {
    const row = rows.get(iso);
    if (!row) return `<strong>${esc(name)}</strong><span class="tip-muted">No data</span>`;
    const v = valueOf(row);
    const main = layer === "index"
      ? `${fmt(row.score, 1)} / 100 · ${STATUS_LABEL[row.status] || ""}`
      : `${LAYER_INFO[layer].label}: ${fmt(v)} / 100`;
    return `<strong>${esc(name)}</strong>${esc(main)}<br><span class="tip-muted">Click for the full picture</span>`;
  }
  function restyleAll() { if (geo) geo.setStyle(style); }

  fetch(el.dataset.geoUrl)
    .then((r) => { if (!r.ok) throw new Error("geo"); return r.json(); })
    .then((g) => {
      geo = L.geoJSON(g, {
        style,
        pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4 }),
        onEachFeature: (f, lyr) => {
          const p = f.properties || {};
          pathByIso.set(p.iso2, lyr);
          lyr.bindTooltip(() => tipHtml(p.iso2, p.name), { sticky: true, direction: "top", className: "ds-map-tip", offset: [0, -8] });
          lyr.on({
            mouseover: () => { if (p.iso2 !== selected) lyr.setStyle({ weight: 1.6, color: T.hover }); },
            mouseout: () => geo && geo.resetStyle(lyr),
            click: () => select(p.iso2, p.name),
          });
        },
      }).addTo(map);
      $("#map-loading")?.remove();
      legend();
      const initial = new URLSearchParams(location.search).get("country");
      if (initial && rows.get(initial.toUpperCase())) select(initial.toUpperCase());
    })
    .catch(() => { $("#map-fallback").hidden = false; $("#map-loading")?.remove(); });

  /* ---------------- legend ---------------- */
  function legend() {
    const box = $("#map-legend");
    if (!box) return;
    if (layer === "index") {
      box.innerHTML = `<span class="ov-legend__title">Resilience index</span>` + BANDS.concat("no_data").map((b) =>
        `<span class="ov-legend__item"><i style="background:${STATUS[b]}"></i>${STATUS_LABEL[b]}</span>`).join("");
    } else {
      box.innerHTML = `<span class="ov-legend__title">${esc(LAYER_INFO[layer].label)}</span>
        <span class="ov-legend__item">Low</span><span class="ov-legend__ramp" style="background:linear-gradient(90deg,${RAMP.join(",")})"></span><span class="ov-legend__item">Extreme</span>
        <span class="ov-legend__item"><i style="background:${T.nodata}"></i>No signal</span>`;
    }
  }

  /* ---------------- histogram ---------------- */
  function histogram() {
    const box = $("#histo");
    if (!box) return;
    const list = [...rows.values()].filter((r) => !RANK_EXCLUDE.has(r.iso2));
    let bins;
    if (layer === "index") {
      bins = BANDS.map((b) => ({ key: b, label: STATUS_LABEL[b], color: STATUS[b], n: list.filter((r) => r.status === b).length, band: b }));
      $("#histo-min").textContent = "Resilient";
      $("#histo-max").textContent = "Critical";
    } else {
      bins = Array.from({ length: 10 }, (_, i) => ({ key: i, lo: i * 10, hi: i * 10 + 10, color: ramp(i * 10 + 5), n: 0 }));
      list.forEach((r) => { const v = valueOf(r); if (v != null) bins[Math.min(9, Math.floor(v / 10))].n += 1; });
      bins.forEach((b) => (b.label = `${b.lo}–${b.hi}`));
      $("#histo-min").textContent = "0 · low pressure";
      $("#histo-max").textContent = "100 · extreme";
    }
    const max = Math.max(1, ...bins.map((b) => b.n));
    box.innerHTML = bins.map((b) => {
      const activeBin = layer === "index" ? bandFilter && bandFilter.size === 1 && bandFilter.has(b.band) : rangeFilter && rangeFilter[0] === b.lo;
      return `<button type="button" class="ov-histo__bar${activeBin ? " is-active" : ""}" data-bin="${b.key}" aria-pressed="${!!activeBin}"
        data-tip-title="${esc(b.label)}" data-tip="${b.n} countries. Click to highlight them on the map.">
        <span class="ov-histo__n num">${b.n}</span>
        <span class="ov-histo__fill" style="height:${Math.max(4, (b.n / max) * 80)}%;background:${b.color}"></span></button>`;
    }).join("");
    $$(".ov-histo__bar", box).forEach((btn) => btn.addEventListener("click", () => {
      const key = btn.dataset.bin;
      if (layer === "index") {
        const already = bandFilter && bandFilter.size === 1 && bandFilter.has(key);
        setBands(already ? null : [key]);
      } else {
        const lo = Number(key) * 10;
        rangeFilter = rangeFilter && rangeFilter[0] === lo ? null : [lo, lo + 10];
        bandFilter = null;
        filtersChanged();
      }
    }));
  }

  /* ---------------- ranking ---------------- */
  function ranking() {
    const info = LAYER_INFO[layer];
    $("#rank-title").textContent = rankDir === "top" ? info.top : info.bottom;
    const q = window.DS ? window.DS.fold($("#rank-filter").value.trim()) : $("#rank-filter").value.trim().toLowerCase();
    let list = [...rows.values()].filter((r) => !RANK_EXCLUDE.has(r.iso2) && valueOf(r) != null);
    list.sort((a, b) => valueOf(b) - valueOf(a) || a.name.localeCompare(b.name));
    const ranked = list.map((r, i) => ({ r, n: i + 1 }));
    let shown = ranked;
    if (rankDir === "bottom") shown = [...ranked].reverse();
    shown = shown.filter(({ r }) => passes(r));
    if (q) shown = shown.filter(({ r }) => (window.DS ? window.DS.fold(r.name) : r.name.toLowerCase()).includes(q));
    shown = shown.slice(0, 12);
    const ol = $("#rank-list");
    if (!shown.length) { ol.innerHTML = `<li class="ds-state"><strong>No country matches</strong><span>Clear the filter or pick another layer.</span></li>`; return; }
    const max = 100;
    ol.innerHTML = shown.map(({ r, n }) => {
      const v = valueOf(r);
      return `<li><button type="button" class="ov-rank__row${r.iso2 === selected ? " is-selected" : ""}" data-iso="${esc(r.iso2)}">
        <span class="ov-rank__n num">${n}</span>
        <span class="ov-rank__name">${esc(r.name)}<small>${layer === "index" ? esc(STATUS_LABEL[r.status] || "") : "pressure"}</small></span>
        <span class="ov-rank__bar"><i style="width:${Math.max(2, (v / max) * 100)}%;background:${colorOf(r)}"></i></span>
        <span class="ov-rank__v num">${fmt(v, layer === "index" ? 1 : 0)}</span></button></li>`;
    }).join("");
    $$(".ov-rank__row", ol).forEach((b) => b.addEventListener("click", () => select(b.dataset.iso, null, true)));
  }
  $$("[data-rank]").forEach((b) => b.addEventListener("click", () => {
    rankDir = b.dataset.rank;
    $$("[data-rank]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    ranking();
  }));
  $("#rank-filter")?.addEventListener("input", ranking);

  /* ---------------- country detail ---------------- */
  function bar(label, v, color, tip) {
    return `<div class="ov-meter" data-tip="${esc(tip)}"><span>${esc(label)}</span><span class="ov-meter__track"><i style="width:${v == null ? 0 : Math.max(2, v)}%;background:${color}"></i></span><b class="num">${fmt(v)}</b></div>`;
  }
  function select(iso, name, fly) {
    const row = rows.get(iso);
    const prev = selected;
    selected = iso;
    if (prev && pathByIso.get(prev) && geo) geo.resetStyle(pathByIso.get(prev));
    const lyr = pathByIso.get(iso);
    if (lyr && geo) { geo.resetStyle(lyr); lyr.bringToFront && lyr.bringToFront(); }
    if (fly && lyr && lyr.getBounds) map.flyToBounds(lyr.getBounds(), { maxZoom: 4, duration: 0.8, padding: [30, 30] });
    const box = $("#country-detail");
    const n = row ? row.name : name || iso;
    if (!row) {
      box.innerHTML = `<div class="ov-detail__head"><h3>${esc(n)}</h3><button class="ds-btn ds-btn--quiet ds-btn--sm" data-close-detail>Back to ranking</button></div><div class="ds-state"><strong>No score for this territory</strong><span>Too little source coverage to compute an index.</span></div>`;
    } else {
      const h = row.hazards || {};
      const p = row.pillars || {};
      box.innerHTML = `
        <div class="ov-detail__head">
          <div><p class="ds-eyebrow" style="margin:0">${esc(row.iso2)} · rank ${row.rank || "—"} of ${rows.size}</p><h3>${esc(n)}</h3></div>
          <button class="ds-btn ds-btn--quiet ds-btn--sm" data-close-detail aria-label="Close detail and return to ranking">✕</button>
        </div>
        <div class="ov-detail__score">
          <strong class="num" style="color:${STATUS[row.status] || T.nodata}">${fmt(row.score, 1)}</strong><span>/100</span>
          <span class="ds-badge ds-badge--${esc(row.status)}"><i></i>${esc(STATUS_LABEL[row.status] || row.status)}</span>
        </div>
        <p class="ov-detail__conf">Confidence ${Math.round((row.confidence || 0) * 100)}% · ${Math.round((row.coverage || 0) * 100)}% of the index weight has data</p>
        <h4>Climate pressures</h4>
        ${bar("Drought", h.drought, ramp(h.drought), "Rain and soil deficit vs this country's own record")}
        ${bar("Flood", h.flood, ramp(h.flood), "Forecast river discharge vs its 60-day baseline")}
        ${bar("Wildfire", h.fire, ramp(h.fire), "Fire weather coupled to drought and active fires")}
        ${bar("Desertification", h.desertification, ramp(h.desertification), "Aridity, rainfall and soil trends, forest change")}
        <h4>What holds the index up</h4>
        <div class="ov-pillars">
          ${[["water", "Water"], ["groundwater", "Groundwater"], ["drought", "Drought"], ["flood", "Flood"], ["fire", "Fire"], ["desertification", "Land"]].map(([k, l]) =>
            `<span class="ov-pillar" data-tip="Pillar score ${fmt(p[k])}/100 — higher means more resilient"><b class="num">${fmt(p[k])}</b>${l}</span>`).join("")}
        </div>
        <div class="ov-detail__actions">
          <a class="ds-btn ds-btn--sm" href="/country/${esc(row.iso2)}/">Open country sheet</a>
          <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/water/${esc(row.iso2)}/">Water runway</a>
          <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/map/?c=${esc(row.iso2)}">Regional map</a>
        </div>`;
    }
    box.hidden = false;
    $("#rank-panel").hidden = true;
    $("[data-close-detail]", box)?.addEventListener("click", closeDetail);
    ranking();
  }
  function closeDetail() {
    const prev = selected;
    selected = null;
    if (prev && pathByIso.get(prev) && geo) geo.resetStyle(pathByIso.get(prev));
    $("#country-detail").hidden = true;
    $("#rank-panel").hidden = false;
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && selected && !document.querySelector("dialog[open]")) closeDetail(); });

  /* ---------------- filters ---------------- */
  function filtersChanged() {
    restyleAll();
    histogram();
    ranking();
    const clear = $("#band-clear");
    if (bandFilter || rangeFilter) {
      clear.hidden = false;
      $("#band-clear-label").textContent = bandFilter ? [...bandFilter].map((b) => STATUS_LABEL[b]).join(", ") : `${rangeFilter[0]}–${rangeFilter[1]} pressure`;
    } else clear.hidden = true;
    $$(".band-seg").forEach((b) => b.classList.toggle("is-dim", !!bandFilter && !bandFilter.has(b.dataset.band)));
  }
  function setBands(list) {
    rangeFilter = null;
    bandFilter = list ? new Set(list) : null;
    if (list && layer !== "index") setLayer("index", true);
    filtersChanged();
  }
  $("#band-clear")?.addEventListener("click", () => { bandFilter = null; rangeFilter = null; filtersChanged(); });
  $$(".band-seg").forEach((b) => b.addEventListener("click", () => {
    const one = bandFilter && bandFilter.size === 1 && bandFilter.has(b.dataset.band);
    setBands(one ? null : [b.dataset.band]);
    $("#explorer").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  $$("[data-filter-bands]").forEach((a) => a.addEventListener("click", () => setBands(a.dataset.filterBands.split(","))));

  /* ---------------- layers + overlays ---------------- */
  function setLayer(next, keepFilters) {
    layer = next;
    $$("#layer-seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.layer === next)));
    if (!keepFilters) { rangeFilter = null; if (next !== "index") bandFilter = null; }
    restyleAll(); legend(); histogram(); ranking();
    $("#histo-title").textContent = next === "index" ? "Countries per band" : `${LAYER_INFO[next].label} across countries`;
    if (selected) select(selected);
    const clear = $("#band-clear");
    if (!bandFilter && !rangeFilter) clear.hidden = true;
  }
  $$("#layer-seg button").forEach((b) => b.addEventListener("click", () => setLayer(b.dataset.layer)));

  function loadDams() {
    if (damsLayer) return Promise.resolve(damsLayer);
    return fetch(el.dataset.damsUrl).then((r) => r.json()).then((p) => {
      damsLayer = L.layerGroup((p.results || []).filter((d) => d.lat != null).map((d) =>
        L.circleMarker([d.lat, d.lon], { radius: 5, color: T.line, weight: 1.2, fillColor: "#34c9b8", fillOpacity: 0.95 })
          .bindPopup(`<strong>${esc(d.name)}</strong><br>${esc(d.country_name || d.country_iso2 || "")}${d.capacity_m3 ? ` · ${(d.capacity_m3 / 1e6).toFixed(0)} Mm³` : ""}<br><a href="/dam/${encodeURIComponent(d.pilot_slug || d.wikidata_id)}/">Open dam sheet →</a>`)));
      return damsLayer;
    });
  }
  let eventsCache = null;
  function loadEvents() {
    if (eventsCache) return Promise.resolve(eventsCache);
    return fetch(el.dataset.eventsUrl).then((r) => r.json()).then((p) => (eventsCache = p.features || []));
  }
  const eventMarkers = new Map();
  function eventsGroup() {
    if (eventsLayer) return Promise.resolve(eventsLayer);
    return loadEvents().then((features) => {
      eventsLayer = L.layerGroup(features.map((f) => {
        const [lon, lat] = f.geometry.coordinates;
        const pr = f.properties;
        const m = L.circleMarker([lat, lon], { radius: 5.5, color: T.line, weight: 1, fillColor: CAT_COLORS[pr.category] || "#edf5f4", fillOpacity: 0.95 })
          .bindPopup(`<strong>${esc(pr.title)}</strong><br>${esc(CAT_LABEL[pr.category] || pr.category)} · ${esc((pr.date || "").slice(0, 10))}${pr.url ? `<br><a href="${esc(pr.url)}" target="_blank" rel="noopener">NASA EONET source →</a>` : ""}`);
        eventMarkers.set(pr.id, m);
        return m;
      }));
      return eventsLayer;
    });
  }
  function toggleOverlay(name, on) {
    const btn = $(`[data-overlay="${name}"]`);
    const want = on == null ? btn.getAttribute("aria-pressed") !== "true" : on;
    btn.setAttribute("aria-pressed", String(want));
    const getter = name === "dams" ? loadDams : eventsGroup;
    return getter().then((g) => { want ? g.addTo(map) : map.removeLayer(g); return g; })
      .catch(() => { btn.setAttribute("aria-pressed", "false"); window.DS && DS.toast(`Could not load ${name}.`); });
  }
  $$("[data-overlay]").forEach((b) => b.addEventListener("click", () => toggleOverlay(b.dataset.overlay)));

  /* ---------------- snapshots ---------------- */
  function recomputeHero() {
    const list = [...rows.values()].filter((r) => r.score != null);
    const avg = list.reduce((s, r) => s + r.score, 0) / Math.max(1, list.length);
    $("#kpi-average").textContent = list.length ? avg.toFixed(1) : "—";
    $("#kpi-scored").textContent = list.length;
    const gauge = $(".ov-gauge__value");
    if (gauge) gauge.style.strokeDasharray = `${avg.toFixed(1)} 100`;
    const counts = Object.fromEntries(BANDS.map((b) => [b, list.filter((r) => r.status === b).length]));
    $$(".band-seg").forEach((b) => (b.style.flex = String(counts[b.dataset.band] || 0)));
  }
  function loadSnapshot(v) {
    const sel = $("#snapshot-select");
    sel.disabled = true;
    return fetch(`/api/world/?version=${encodeURIComponent(v)}`).then((r) => r.json()).then((p) => {
      rows = new Map((p.countries || []).map((r) => [r.iso2, r]));
      version = p.version;
      restyleAll(); histogram(); ranking(); recomputeHero();
      if (selected) select(selected);
      window.DS && DS.toast(`Showing the snapshot of ${sel.options[sel.selectedIndex].text}`);
    }).catch(() => window.DS && DS.toast("That snapshot could not be loaded.")).finally(() => (sel.disabled = false));
  }
  $("#snapshot-select")?.addEventListener("change", (e) => e.target.value && loadSnapshot(e.target.value));

  /* ---------------- refresh (unchanged behaviour) ---------------- */
  const refreshBtn = $("#refresh-world");
  const refreshStatus = $("#refresh-status");
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  function busy(on) {
    if (!refreshBtn) return;
    refreshBtn.disabled = on;
    refreshBtn.classList.toggle("is-busy", on);
    refreshBtn.lastChild.textContent = on ? " Refreshing…" : " Refresh live data";
  }
  refreshBtn?.addEventListener("click", () => {
    busy(true);
    refreshStatus.textContent = "Refresh started — the map updates by itself when the sources finish (a few minutes).";
    fetch(el.dataset.refreshUrl, { method: "POST", headers: { "X-CSRFToken": csrf, Accept: "application/json" } })
      .then((r) => r.json().then((p) => ({ ok: r.ok, p })))
      .then(({ ok, p }) => { refreshStatus.textContent = p.message || "Refresh started."; if (!ok) busy(false); })
      .catch(() => { refreshStatus.textContent = "The refresh could not start. Run `python manage.py refresh_world` in a terminal."; busy(false); });
  });
  function pollMeta() {
    fetch(el.dataset.metaUrl).then((r) => r.json()).then((p) => {
      if (p.version && version && p.version !== version) {
        refreshStatus.textContent = "A new world snapshot is ready.";
        window.DS && DS.toast("New data arrived — the map has been updated.");
        loadSnapshot(p.version);
      }
      busy(!!p.refresh_running);
    }).catch(() => {});
  }
  setInterval(pollMeta, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollMeta(); });

  /* ---------------- Algeria preview ---------------- */
  const dzBox = $("#dz-mini");
  let dzLayer = "drought", dzData = null, dzGeo = null, dzMap = null;
  const DZ_LABEL = { drought: "drought pressure", water_stress: "water stress", fire: "forest-fire pressure" };
  function dzRender() {
    if (!dzData) return;
    const by = new Map(dzData.wilayas.map((w) => [w.code, w]));
    if (dzGeo) dzGeo.setStyle((f) => ({ fillColor: ramp((by.get(f.properties.code) || {}).layers?.[dzLayer]), fillOpacity: 0.9, color: T.line, weight: 0.7 }));
    const top = dzData.wilayas.filter((w) => w.layers[dzLayer] != null).sort((a, b) => b.layers[dzLayer] - a.layers[dzLayer]).slice(0, 5);
    $("#dz-caption").textContent = `Highest ${DZ_LABEL[dzLayer]}`;
    $("#dz-top").innerHTML = top.map((w) => `<li><a href="/map/?w=${w.code}&layer=${dzLayer}"><span>${esc(w.name)}</span><span class="ov-bars__track"><i style="width:${w.layers[dzLayer]}%;background:${ramp(w.layers[dzLayer])}"></i></span><b class="num">${fmt(w.layers[dzLayer])}</b></a></li>`).join("");
    $("#dz-open").href = `/map/?layer=${dzLayer}`;
  }
  if (dzBox) {
    Promise.all([fetch("/static/data/dz-wilayas-lite.geojson").then((r) => r.json()), fetch("/api/algeria/wilayas/").then((r) => r.json())])
      .then(([g, p]) => {
        dzData = p;
        if (!p.wilayas || !p.wilayas.length) {
          $("#dz-top").innerHTML = `<li class="ds-state"><strong>No wilaya snapshot yet</strong><span>Run <code>python manage.py refresh_wilayas</code>.</span></li>`;
          return;
        }
        dzMap = L.map(dzBox, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false, zoomSnap: 0.1 });
        const by = new Map(p.wilayas.map((w) => [w.code, w]));
        dzGeo = L.geoJSON(g, {
          onEachFeature: (f, lyr) => {
            lyr.bindTooltip(() => { const w = by.get(f.properties.code); return `<strong>${esc(f.properties.name)}</strong>${esc(DZ_LABEL[dzLayer])}: ${fmt(w?.layers?.[dzLayer])} / 100<br><span class="tip-muted">Click to open in the map viewer</span>`; }, { sticky: true, className: "ds-map-tip", direction: "top" });
            lyr.on({ mouseover: () => lyr.setStyle({ weight: 1.8, color: T.select }), mouseout: () => dzGeo.resetStyle(lyr), click: () => (location.href = `/map/?w=${f.properties.code}&layer=${dzLayer}`) });
          },
        }).addTo(dzMap);
        dzMap.fitBounds(dzGeo.getBounds(), { padding: [6, 6] });
        dzRender();
        new ResizeObserver(() => { dzMap.invalidateSize(); dzMap.fitBounds(dzGeo.getBounds(), { padding: [6, 6] }); }).observe(dzBox);
      })
      .catch(() => { $("#dz-top").innerHTML = `<li class="ds-state ds-state--error"><strong>Wilaya data unavailable</strong><span>The map viewer explains what is missing.</span></li>`; });
    $$("#dz-seg button").forEach((b) => b.addEventListener("click", () => {
      dzLayer = b.dataset.dz;
      $$("#dz-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      dzRender();
    }));
  }

  /* ---------------- alerts ---------------- */
  let alertCat = "all";
  function relDate(iso) {
    if (!iso) return "date unknown";
    const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
    return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
  }
  function renderAlerts() {
    const period = $("#alert-period").value;
    const now = Date.now();
    const list = (eventsCache || [])
      .filter((f) => alertCat === "all" || f.properties.category === alertCat)
      .filter((f) => period === "all" || (f.properties.date && now - new Date(f.properties.date).getTime() <= Number(period) * 86400000))
      .sort((a, b) => String(b.properties.date).localeCompare(String(a.properties.date)));
    const ul = $("#alert-list");
    $("#alert-count").textContent = `${list.length} event${list.length === 1 ? "" : "s"} match · ${(eventsCache || []).length} open in total`;
    if (!list.length) {
      ul.innerHTML = `<li class="ds-state"><strong>Nothing in this window</strong><span>Widen the period or pick another event type.</span></li>`;
      return;
    }
    ul.innerHTML = list.slice(0, 8).map((f) => {
      const p = f.properties;
      return `<li><button type="button" class="ov-alert" data-event="${p.id}">
        <span class="ov-alert__dot" style="background:${CAT_COLORS[p.category] || "#edf5f4"}"></span>
        <span class="ov-alert__title">${esc(p.title)}<small>${esc(CAT_LABEL[p.category] || p.category)} · ${esc(relDate(p.date))}</small></span>
        <span class="ov-alert__meta">${esc(p.country || "—")}</span></button></li>`;
    }).join("");
    $$(".ov-alert", ul).forEach((b) => b.addEventListener("click", () => {
      const f = (eventsCache || []).find((x) => String(x.properties.id) === b.dataset.event);
      if (!f) return;
      toggleOverlay("events", true).then(() => {
        $("#explorer").scrollIntoView({ behavior: "smooth", block: "start" });
        const [lon, lat] = f.geometry.coordinates;
        map.flyTo([lat, lon], 5, { duration: 0.9 });
        setTimeout(() => eventMarkers.get(f.properties.id)?.openPopup(), 950);
      });
    }));
  }
  $$("#alert-chips .ds-chip").forEach((b) => b.addEventListener("click", () => {
    alertCat = b.dataset.cat;
    $$("#alert-chips .ds-chip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderAlerts();
  }));
  $("#alert-period")?.addEventListener("change", renderAlerts);
  loadEvents().then(renderAlerts).catch(() => {
    $("#alert-list").innerHTML = `<li class="ds-state ds-state--error"><strong>Events could not load</strong><span>NASA EONET data is cached by the world refresh.</span></li>`;
  });

  /* ---------------- first paint ---------------- */
  legend(); histogram(); ranking();
  /* ---------------- theme switch: recolour in place, keep selection and filters ---------------- */
  window.addEventListener("ds:theme", () => {
    readTheme();
    restyleAll(); legend(); histogram(); ranking();
    if (selected) select(selected);
    [damsLayer, eventsLayer].forEach((g) => g && g.eachLayer((m) => m.setStyle && m.setStyle({ color: T.line })));
    if (typeof dzRender === "function") dzRender();
  });
})();
