/* World choropleth + hazard layers. Leaflet is vendored; no tile server. */
(function () {
  "use strict";

  const el = document.getElementById("world-map");
  if (!el) return;
  const fallback = document.getElementById("map-fallback");
  if (!window.L) {
    if (fallback) fallback.hidden = false;
    return;
  }

  const geoUrl = el.dataset.geoUrl;
  const apiUrl = el.dataset.apiUrl;
  const metaUrl = el.dataset.metaUrl;
  const refreshUrl = el.dataset.refreshUrl;
  const eventsUrl = el.dataset.eventsUrl;
  const damsUrl = el.dataset.damsUrl;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const card = document.getElementById("country-card");
  const legend = document.getElementById("map-legend");
  const refreshBtn = document.getElementById("refresh-world");
  const refreshStatus = document.getElementById("refresh-status");

  const STATUS = {
    resilient: "#55c98a",
    stable: "#4aa3a2",
    watch: "#e5a23b",
    stressed: "#e07a3f",
    critical: "#ef6f72",
    no_data: "#35494c",
  };
  const STATUS_LABEL = {
    resilient: "Resilient",
    stable: "Stable",
    watch: "Watch",
    stressed: "Stressed",
    critical: "Critical",
    no_data: "No data",
  };
  const HAZARD_COLORS = ["#2b6f6a", "#8fae5a", "#e5a23b", "#e07a3f", "#ef6f72"];
  const CATEGORY_COLORS = {
    drought: "#e5a23b",
    floods: "#5ba7e8",
    wildfires: "#ef6f72",
    dustHaze: "#b18a5c",
    tempExtremes: "#c084fc",
  };

  let data = {};
  try {
    data = JSON.parse(document.getElementById("world-data")?.textContent || "{}");
  } catch (error) {
    data = {};
  }
  let currentVersion = data.version || null;
  let countryData = new Map((data.countries || []).map((row) => [row.iso2, row]));
  let currentLayer = el.dataset.layer || "index";
  let geoLayer = null;
  let damsLayer = null;
  let eventsLayer = null;
  let damsLoaded = false;
  let eventsLoaded = false;

  const map = L.map(el, {
    worldCopyJump: true,
    minZoom: 1,
    maxZoom: 7,
    zoomControl: true,
    attributionControl: true,
  }).setView([18, 12], 2);
  map.attributionControl.setPrefix("");

  function esc(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function hexToRgb(hex) {
    const value = hex.replace("#", "");
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16),
    ];
  }

  function pressureColor(pressure) {
    if (pressure === null || pressure === undefined || Number.isNaN(Number(pressure))) {
      return STATUS.no_data;
    }
    const value = Math.max(0, Math.min(100, Number(pressure))) / 100;
    const scaled = value * (HAZARD_COLORS.length - 1);
    const index = Math.min(HAZARD_COLORS.length - 2, Math.floor(scaled));
    const t = scaled - index;
    const a = hexToRgb(HAZARD_COLORS[index]);
    const b = hexToRgb(HAZARD_COLORS[index + 1]);
    const rgb = a.map((channel, i) => Math.round(channel + (b[i] - channel) * t));
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  }

  function featureColor(feature) {
    const row = countryData.get(feature.properties.iso2);
    if (!row) return STATUS.no_data;
    if (currentLayer === "index") return STATUS[row.status] || STATUS.no_data;
    const pressure = (row.hazards || {})[currentLayer];
    return pressureColor(pressure);
  }

  function styleFeature(feature) {
    return {
      fillColor: featureColor(feature),
      fillOpacity: 0.78,
      color: "#0b191c",
      weight: 0.6,
      opacity: 1,
    };
  }

  function scoreLine(row) {
    if (!row || row.score === null || row.score === undefined) return "No score";
    return `${Number(row.score).toFixed(1)} / 100 · ${STATUS_LABEL[row.status] || row.status}`;
  }

  function tooltip(row, name) {
    if (!row) return `<strong>${esc(name)}</strong><br>No data`;
    const hazards = row.hazards || {};
    const hazardBits = ["drought", "flood", "fire", "desertification"]
      .map((key) => {
        const value = hazards[key];
        return `<span style="color:#9bb0ae">${key}</span> ${value == null ? "—" : Math.round(value) + "%"}`;
      })
      .join(" · ");
    return `<strong>${esc(name)}</strong><br>${esc(scoreLine(row))}<br><span style="font-size:10px">${hazardBits}</span>`;
  }

  function showCard(iso2, name) {
    if (!card) return;
    const row = countryData.get(iso2);
    if (!row) {
      card.hidden = true;
      return;
    }
    const hazards = row.hazards || {};
    card.innerHTML = `
      <strong>${esc(name)}</strong>
      <div class="card-score" style="color:${STATUS[row.status] || STATUS.no_data}">${row.score == null ? "—" : Number(row.score).toFixed(1)}<span style="font-size:12px;color:#9bb0ae"> / 100</span></div>
      <p>${esc(STATUS_LABEL[row.status] || row.status)} · rank ${row.rank || "—"} · confidence ${Math.round((row.confidence || 0) * 100)}%</p>
      <p>Drought ${hazards.drought == null ? "—" : Math.round(hazards.drought)} · Flood ${hazards.flood == null ? "—" : Math.round(hazards.flood)} · Fire ${hazards.fire == null ? "—" : Math.round(hazards.fire)} · Desert ${hazards.desertification == null ? "—" : Math.round(hazards.desertification)}</p>
      <a href="/country/${esc(iso2)}/">Open the country sheet →</a>
    `;
    card.hidden = false;
  }

  function onEachFeature(feature, layer) {
    const props = feature.properties || {};
    const row = countryData.get(props.iso2);
    layer.bindTooltip(tooltip(row, props.name), { sticky: true, direction: "top" });
    layer.on({
      mouseover: () => layer.setStyle({ weight: 1.4, color: "#edf5f4", fillOpacity: 0.92 }),
      mouseout: () => geoLayer && geoLayer.resetStyle(layer),
      click: () => showCard(props.iso2, props.name),
    });
  }

  function markerForFeature(feature, latlng) {
    return L.circleMarker(latlng, {
      radius: 4,
      color: "#071113",
      weight: 1,
      fillColor: featureColor(feature),
      fillOpacity: 0.9,
    });
  }

  function updateLegend() {
    if (!legend) return;
    if (currentLayer === "index") {
      legend.innerHTML = Object.entries(STATUS_LABEL)
        .map(([key, label]) => `<span class="legend-item"><span class="legend-swatch" style="background:${STATUS[key]}"></span>${label}</span>`)
        .join("");
    } else if (currentLayer === "dams") {
      legend.innerHTML = '<span class="legend-item"><span class="legend-swatch" style="background:#34c9b8"></span>Monitored dam</span><span class="legend-item">Marker size/colour fixed · 38 monitored in the atlas</span>';
    } else if (currentLayer === "events") {
      legend.innerHTML = Object.entries(CATEGORY_COLORS)
        .map(([key, color]) => `<span class="legend-item"><span class="legend-swatch" style="background:${color}"></span>${key}</span>`)
        .join("");
    } else {
      legend.innerHTML = `<span class="legend-item">Low pressure</span><span class="legend-swatch" style="background:linear-gradient(90deg,${HAZARD_COLORS.join(",")});width:120px"></span><span class="legend-item">Extreme</span>`;
    }
  }

  function loadDams() {
    if (damsLoaded || !damsUrl) return Promise.resolve();
    damsLoaded = true;
    return fetch(damsUrl)
      .then((response) => response.json())
      .then((payload) => {
        const group = L.layerGroup();
        (payload.results || []).forEach((dam) => {
          if (dam.lat == null || dam.lon == null) return;
          const marker = L.circleMarker([dam.lat, dam.lon], {
            radius: dam.is_monitored ? 4.5 : 3,
            color: dam.is_monitored ? "#071113" : "#e5a23b",
            weight: 1,
            fillColor: dam.is_monitored ? "#34c9b8" : "#e5a23b",
            fillOpacity: dam.is_monitored ? 0.9 : 0.55,
          });
          const slug = dam.pilot_slug || dam.wikidata_id;
          marker.bindPopup(
            `<strong>${esc(dam.name)}</strong><br>${esc(dam.country_name || dam.country_iso2 || "")}<br>` +
              `<a href="/dam/${encodeURIComponent(slug)}/">Open dam sheet →</a>`
          );
          marker.addTo(group);
        });
        damsLayer = group;
        if (currentLayer === "dams") group.addTo(map);
      })
      .catch(() => {
        damsLoaded = false;
      });
  }

  function loadEvents() {
    if (eventsLoaded || !eventsUrl) return Promise.resolve();
    eventsLoaded = true;
    return fetch(eventsUrl)
      .then((response) => response.json())
      .then((payload) => {
        const group = L.layerGroup();
        const geo = L.geoJSON(payload, {
          pointToLayer: (feature, latlng) =>
            L.circleMarker(latlng, {
              radius: 5,
              color: "#071113",
              weight: 1,
              fillColor: CATEGORY_COLORS[feature.properties.category] || "#edf5f4",
              fillOpacity: 0.9,
            }),
          onEachFeature: (feature, layer) => {
            const props = feature.properties || {};
            layer.bindPopup(
              `<strong>${esc(props.title)}</strong><br>${esc(props.category)} · ${esc((props.date || "").slice(0, 10))}<br>` +
                (props.url ? `<a href="${esc(props.url)}" target="_blank" rel="noopener">NASA EONET source →</a>` : "")
            );
          },
        });
        geo.addTo(group);
        eventsLayer = group;
        if (currentLayer === "events") group.addTo(map);
      })
      .catch(() => {
        eventsLoaded = false;
      });
  }

  function setLayer(layer) {
    currentLayer = layer;
    document.querySelectorAll(".layer-btn").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.layer === layer);
    });
    if (damsLayer) map.removeLayer(damsLayer);
    if (eventsLayer) map.removeLayer(eventsLayer);
    if (layer === "dams") loadDams().then(() => damsLayer && damsLayer.addTo(map));
    if (layer === "events") loadEvents().then(() => eventsLayer && eventsLayer.addTo(map));
    if (geoLayer) geoLayer.setStyle(styleFeature);
    updateLegend();
    if (card) card.hidden = true;
  }

  document.querySelectorAll(".layer-btn").forEach((button) => {
    button.addEventListener("click", () => setLayer(button.dataset.layer));
  });

  document.querySelectorAll(".rail-switch button").forEach((button) => {
    button.addEventListener("click", () => {
      const top = button.dataset.rank === "top";
      document.querySelectorAll(".rail-switch button").forEach((item) => item.classList.toggle("is-active", item === button));
      document.getElementById("rank-top").hidden = !top;
      document.getElementById("rank-bottom").hidden = top;
    });
  });

  function refreshMapData() {
    return fetch(apiUrl, { headers: { Accept: "application/json" } })
      .then((response) => response.json())
      .then((payload) => {
        if (!payload || !payload.countries) return false;
        countryData = new Map(payload.countries.map((row) => [row.iso2, row]));
        currentVersion = payload.version;
        if (geoLayer) geoLayer.setStyle(styleFeature);
        return true;
      });
  }

  function pollMeta() {
    fetch(metaUrl, { headers: { Accept: "application/json" } })
      .then((response) => response.json())
      .then((payload) => {
        if (payload.version && currentVersion && payload.version !== currentVersion) {
          refreshMapData().then((updated) => {
            if (updated && refreshStatus) {
              refreshStatus.textContent = "A new world snapshot is available. Reload to update the ledger and source stamps.";
            }
          });
        }
        if (payload.refresh_running && refreshBtn) {
          refreshBtn.disabled = true;
          refreshBtn.textContent = "Refreshing…";
        } else if (refreshBtn) {
          refreshBtn.disabled = false;
          refreshBtn.textContent = "Refresh live data";
        }
      })
      .catch(() => {});
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing…";
      if (refreshStatus) refreshStatus.textContent = "Refresh started. The world snapshot will update when the sources finish.";
      fetch(refreshUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrf, Accept: "application/json" },
      })
        .then((response) => response.json())
        .then((payload) => {
          if (refreshStatus) refreshStatus.textContent = payload.message || "Refresh started.";
        })
        .catch(() => {
          if (refreshStatus) refreshStatus.textContent = "Refresh could not start. Run bootstrap_world from the terminal.";
          refreshBtn.disabled = false;
          refreshBtn.textContent = "Refresh live data";
        });
    });
  }

  fetch(geoUrl)
    .then((response) => {
      if (!response.ok) throw new Error("geometry fetch failed");
      return response.json();
    })
    .then((geo) => {
      geoLayer = L.geoJSON(geo, {
        style: styleFeature,
        onEachFeature,
        pointToLayer: markerForFeature,
      }).addTo(map);
      const bounds = geoLayer.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [8, 8] });
      updateLegend();
    })
    .catch(() => {
      if (fallback) fallback.hidden = false;
    });

  updateLegend();
  setInterval(pollMeta, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollMeta();
  });
})();
