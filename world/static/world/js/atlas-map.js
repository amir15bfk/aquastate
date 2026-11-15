/* Atlas map: viewport-loaded dam markers, no tile server. */
(function () {
  "use strict";
  // Theme colours come from the CSS tokens (static/ds/themes.css); maps restyle on "ds:theme".
  const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  const T = {};
  function readTheme() {
    T.link = css("--t-link", "#1b6c80"); T.line = css("--t-map-line", "#ffffff");
    T.land = css("--t-map-land", "#dbe5df"); T.edge = css("--t-map-edge", "#a9b8b2");
  }
  readTheme();
  const el = document.getElementById("atlas-map");
  if (!el) return;
  if (!window.L) {
    el.innerHTML = '<div class="empty-light">Map library unavailable. The table below is the full catalogue.</div>';
    return;
  }
  const apiUrl = el.dataset.apiUrl;
  const geoUrl = el.dataset.geoUrl;
  const countEl = document.getElementById("atlas-map-count");
  const map = L.map(el, { minZoom: 1, maxZoom: 8, worldCopyJump: true, attributionControl: false }).setView([18, 12], 2);
  const layer = L.layerGroup().addTo(map);
  let timer = null;

  function esc(value) {
    return String(value == null ? "" : value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  function load() {
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((n) => n.toFixed(4)).join(",");
    fetch(`${apiUrl}?bbox=${encodeURIComponent(bbox)}&page_size=500`)
      .then((response) => response.json())
      .then((payload) => {
        layer.clearLayers();
        (payload.results || []).forEach((dam) => {
          if (dam.lat == null || dam.lon == null) return;
          const monitored = !!dam.is_monitored;
          const marker = L.circleMarker([dam.lat, dam.lon], {
            radius: monitored ? 5 : 3,
            color: monitored ? T.line : "#8a5a0a",
            weight: 1,
            fillColor: monitored ? T.link : "#c98a2e",
            fillOpacity: monitored ? 0.92 : 0.5,
          });
          const slug = dam.pilot_slug || dam.wikidata_id;
          const capacity = dam.capacity_m3
            ? `${(Number(dam.capacity_m3) / 1e6).toFixed(1)} Mm³`
            : dam.installed_mw
              ? `${Number(dam.installed_mw).toFixed(0)} MW`
              : "capacity unknown";
          marker.bindPopup(
            `<strong>${esc(dam.name)}</strong><br>${esc(dam.country_name || dam.country_iso2 || "")}<br>` +
              `${esc(capacity)} · ${monitored ? "monitored" : "inventory only"}<br>` +
              `<a href="/dam/${encodeURIComponent(slug)}/">Open dam sheet →</a>`
          );
          marker.addTo(layer);
        });
        if (countEl) {
          countEl.textContent = `${payload.count.toLocaleString()} in view · showing ${(payload.results || []).length}`;
        }
      })
      .catch(() => {
        if (countEl) countEl.textContent = "Viewport load failed";
      });
  }

  let countries = null;
  window.addEventListener("ds:theme", () => { readTheme(); if (countries) countries.setStyle({ color: T.edge, fillColor: T.land }); load(); });
  fetch(geoUrl)
    .then((response) => response.json())
    .then((geo) => {
      countries = L.geoJSON(geo, {
        style: () => ({ color: T.edge, weight: 0.5, fillColor: T.land, fillOpacity: 0.85 }),
        pointToLayer: (f, latlng) => L.circleMarker(latlng, { radius: 2, color: T.edge, fillColor: T.land }),
      }).addTo(map);
      const bounds = countries.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [6, 6] });
      load();
    })
    .catch(() => load());

  map.on("moveend", () => {
    clearTimeout(timer);
    timer = setTimeout(load, 250);
  });
  window.addEventListener("resize", () => map.invalidateSize());
})();
