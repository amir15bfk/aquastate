/* Country map: the national outline, monitored dams and active events. */
(function () {
  "use strict";
  const el = document.getElementById("country-map");
  if (!el) return;
  if (!window.L) {
    el.innerHTML = '<div class="empty-light">Map library unavailable. Use the dam table below.</div>';
    return;
  }
  const iso2 = el.dataset.iso2;
  const geoUrl = el.dataset.geoUrl;
  let dams = [];
  let events = [];
  try { dams = JSON.parse(document.getElementById("country-dams")?.textContent || "[]"); } catch (e) { dams = []; }
  try { events = JSON.parse(document.getElementById("country-events")?.textContent || "[]"); } catch (e) { events = []; }

  // Theme colours come from the CSS tokens (static/ds/themes.css); maps restyle on "ds:theme".
  const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  const T = {};
  function readTheme() {
    T.link = css("--t-link", "#1b6c80"); T.line = css("--t-map-line", "#ffffff");
    T.land = css("--t-map-land", "#dbe5df"); T.edge = css("--t-map-edge", "#a9b8b2");
  }
  readTheme();
  const map = L.map(el, { zoomControl: true, attributionControl: false, minZoom: 2, maxZoom: 9 }).setView([20, 0], 2);
  const colors = {
    drought: "#e5a23b",
    floods: "#5ba7e8",
    wildfires: "#ef6f72",
    dustHaze: "#b18a5c",
    tempExtremes: "#c084fc",
  };

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  let outline = null;
  fetch(geoUrl)
    .then((response) => response.json())
    .then((geo) => {
      const feature = (geo.features || []).find((item) => item.properties?.iso2 === iso2);
      if (!feature) {
        map.setView([20, 0], 2);
        return;
      }
      outline = L.geoJSON(feature, {
        style: () => ({ color: T.link, weight: 1.5, fillColor: T.link, fillOpacity: 0.08 }),
        pointToLayer: (f, latlng) => L.circleMarker(latlng, { radius: 6, color: T.link, fillColor: T.link, fillOpacity: 0.2 }),
      }).addTo(map);
      const bounds = outline.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [22, 22], maxZoom: 6 });
    })
    .catch(() => {});

  const damLayer = L.layerGroup().addTo(map);
  dams.forEach((dam) => {
    if (dam.lat == null || dam.lon == null) return;
    const monitored = !!dam.is_monitored;
    const marker = L.circleMarker([dam.lat, dam.lon], {
      radius: monitored ? 5 : 3,
      color: monitored ? T.line : "#8a5a0a",
      weight: 1,
      fillColor: monitored ? T.link : "#c98a2e",
      fillOpacity: monitored ? 0.92 : 0.55,
    });
    const capacity = dam.capacity_m3
      ? `${Number(dam.capacity_m3 / 1_000_000).toFixed(1)} Mm³`
      : dam.installed_mw
        ? `${Number(dam.installed_mw).toFixed(0)} MW`
        : "capacity unknown";
    const slug = dam.pilot_slug || dam.wikidata_id;
    marker.bindPopup(
      `<strong>${esc(dam.name)}</strong><br>${esc(capacity)} · ${monitored ? "monitored" : "inventory only"}<br>` +
        `<a href="/dam/${encodeURIComponent(slug)}/">Open dam sheet →</a>`
    );
    marker.addTo(damLayer);
  });

  const eventLayer = L.layerGroup().addTo(map);
  events.forEach((event) => {
    if (event.lat == null || event.lon == null) return;
    L.circleMarker([event.lat, event.lon], {
      radius: 5,
      color: T.line,
      weight: 1,
      fillColor: colors[event.category] || "#c4242a",
      fillOpacity: 0.9,
    })
      .bindPopup(`<strong>${esc(event.title)}</strong><br>${esc(event.category)} · ${esc((event.date || "").slice(0, 10))}`)
      .addTo(eventLayer);
  });

  window.addEventListener("resize", () => map.invalidateSize());
  window.addEventListener("ds:theme", () => {
    readTheme();
    if (outline) outline.setStyle({ color: T.link, fillColor: T.link });
    damLayer.eachLayer((m) => m.setStyle(m.options.radius === 5 ? { color: T.line, fillColor: T.link } : {}));
    eventLayer.eachLayer((m) => m.setStyle({ color: T.line }));
  });
})();
