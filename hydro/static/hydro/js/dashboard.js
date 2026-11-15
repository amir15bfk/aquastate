/* global window, document, fetch, history, DOMParser, L */
(function () {
  "use strict";

  const STATUS_COLORS = {
    ok: "#1e7b4f",
    watch: "#8a5a0a",
    stressed: "#b54708",
    critical: "#c4242a",
  };
  const ACCENT = "#1b6c80";
  const CHART_2 = "#2f70bb";
  const INK = "#14201d";
  const MUTED = "#5b6763";
  const FAINT = "#6f7a76";
  const RULE = "#eef1ef";

  let navigating = false;

  function data() {
    const node = document.getElementById("dashboard-data");
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return null;
    }
  }

  function esc(value) {
    return window.Aqua ? window.Aqua.escapeHTML(value) : String(value == null ? "" : value);
  }

  function num(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    });
  }

  function attr(value) {
    return esc(value).replaceAll('"', "&quot;");
  }

  function svgEl(parts) {
    return `<svg viewBox="0 0 360 136" preserveAspectRatio="xMidYMid meet" role="img" aria-hidden="true">${parts}</svg>`;
  }

  /* -----------------------------------------------------------------------
     Runway chart: usable storage, threshold, rain bars, runoff day.
     ----------------------------------------------------------------------- */
  function renderRunway(payload) {
    const host = document.getElementById("runway-chart");
    if (!host) return;
    const runway = (payload.horizon && payload.horizon.runway) || [];
    if (!runway.length) {
      host.innerHTML = '<p class="empty-inline">No runway simulation available.</p>';
      return;
    }
    const W = 360;
    const H = 136;
    const ml = 30;
    const mr = 10;
    const mt = 24;
    const mb = 18;
    const plotW = W - ml - mr;
    const plotH = H - mt - mb;
    const values = runway.map((row) => Number(row.storage_pct) || 0);
    const threshold = Number(runway[0].threshold_pct) || 3;
    const rain = runway.map((row) => Number(row.rain_mm) || 0);
    const yMax = Math.max(10, Math.ceil((Math.max(...values, threshold * 2) * 1.18) / 5) * 5);
    const x = (index) => ml + (plotW * index) / Math.max(1, runway.length - 1);
    const y = (value) => mt + plotH - (Math.max(0, Math.min(yMax, value)) / yMax) * plotH;
    const rainMax = Math.max(1, ...rain);
    const parts = [];

    // Grid and y labels.
    [0, yMax / 2, yMax].forEach((tick) => {
      const yy = y(tick);
      parts.push(
        `<line x1="${ml}" y1="${yy}" x2="${W - mr}" y2="${yy}" stroke="${RULE}" stroke-width="1"/>`
      );
      parts.push(
        `<text x="${ml - 5}" y="${yy + 3.5}" text-anchor="end" font-size="12" fill="${FAINT}" font-family="IBM Plex Mono">${num(tick, 0)}</text>`
      );
    });

    // Rain bars above the plot.
    runway.forEach((row, index) => {
      const value = rain[index];
      if (value <= 0) return;
      const barH = Math.max(1.5, (value / rainMax) * 13);
      const barX = x(index) - 1.6;
      parts.push(
        `<rect x="${barX}" y="${mt - 17 - barH}" width="3.2" height="${barH}" rx="1" fill="${CHART_2}" opacity=".42"/>`
      );
    });

    // Emergency reserve.
    const yThreshold = y(threshold);
    parts.push(
      `<line x1="${ml}" y1="${yThreshold}" x2="${W - mr}" y2="${yThreshold}" stroke="#c4242a" stroke-width="1" stroke-dasharray="3 3" opacity=".7"/>`
    );
    parts.push(
      `<text x="${W - mr}" y="${yThreshold - 4}" text-anchor="end" font-size="12" fill="#831c1e" font-family="IBM Plex Sans">reserve ${num(threshold, 0)}%</text>`
    );

    // Area and line.
    const linePoints = runway.map((row, index) => `${x(index).toFixed(2)},${y(values[index]).toFixed(2)}`);
    const area = `M ${ml} ${mt + plotH} L ${linePoints.join(" L ")} L ${W - mr} ${mt + plotH} Z`;
    parts.push(`<path d="${area}" fill="${ACCENT}" opacity=".07"/>`);
    parts.push(
      `<path d="M ${linePoints.join(" L ")}" fill="none" stroke="${ACCENT}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>`
    );

    // Today.
    parts.push(
      `<circle cx="${x(0)}" cy="${y(values[0])}" r="3" fill="#ffffff" stroke="${ACCENT}" stroke-width="1.8"/>`
    );

    // Rain runoff arrival.
    if (payload.horizon && payload.horizon.days_to_rain) {
      const eventIndex = Math.min(payload.horizon.days_to_rain - 1, runway.length - 1);
      const eventX = x(eventIndex);
      parts.push(
        `<line x1="${eventX}" y1="${mt}" x2="${eventX}" y2="${mt + plotH}" stroke="${CHART_2}" stroke-width="1" stroke-dasharray="2 3" opacity=".8"/>`
      );
      const anchor = eventX > W - 72 ? "end" : "start";
      parts.push(
        `<text x="${eventX + (anchor === "end" ? -3 : 3)}" y="${mt - 16}" text-anchor="${anchor}" font-size="12" fill="${CHART_2}" font-family="IBM Plex Sans">runoff d${payload.horizon.days_to_rain}</text>`
      );
    }

    // X labels: first, middle, last.
    [0, Math.floor((runway.length - 1) / 2), runway.length - 1].forEach((index) => {
      const label = new Date(`${runway[index].date}T00:00:00`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
      parts.push(
        `<text x="${x(index)}" y="${H - 3}" text-anchor="${index === 0 ? "start" : index === runway.length - 1 ? "end" : "middle"}" font-size="12" fill="${FAINT}" font-family="IBM Plex Sans">${esc(label)}</text>`
      );
    });

    host.innerHTML = svgEl(parts.join(""));
    host.setAttribute(
      "aria-label",
      `Water runway: ${num(values[0], 1)} percent usable storage today, ${num(values[values.length - 1], 1)} percent in thirty days, emergency reserve ${num(threshold, 0)} percent${payload.horizon && payload.horizon.days_to_rain ? `, rain runoff in ${payload.horizon.days_to_rain} days` : ", no rain runoff in the forecast"}.`
    );
  }

  /* -----------------------------------------------------------------------
     Ten-year storage trend.
     ----------------------------------------------------------------------- */
  function renderTrend(payload) {
    const host = document.getElementById("trend-chart");
    if (!host) return;
    const history = (payload.series && payload.series.storage_history) || [];
    if (history.length < 2) {
      host.innerHTML = '<p class="empty-inline">Not enough annual history for a trend.</p>';
      return;
    }
    const W = 360;
    const H = 150;
    const ml = 28;
    const mr = 10;
    const mt = 12;
    const mb = 20;
    const plotW = W - ml - mr;
    const plotH = H - mt - mb;
    const x = (index) => ml + (plotW * index) / (history.length - 1);
    const y = (value) => mt + plotH - (Math.max(0, Math.min(100, value)) / 100) * plotH;
    const parts = [];
    [0, 50, 100].forEach((tick) => {
      const yy = y(tick);
      parts.push(
        `<line x1="${ml}" y1="${yy}" x2="${W - mr}" y2="${yy}" stroke="${RULE}" stroke-width="1"/>`
      );
      parts.push(
        `<text x="${ml - 5}" y="${yy + 3.5}" text-anchor="end" font-size="12" fill="${FAINT}" font-family="IBM Plex Mono">${tick}</text>`
      );
    });
    const points = history.map((row, index) => `${x(index).toFixed(2)},${y(Number(row.storage_pct)).toFixed(2)}`);
    const area = `M ${ml} ${mt + plotH} L ${points.join(" L ")} L ${W - mr} ${mt + plotH} Z`;
    parts.push(`<path d="${area}" fill="${ACCENT}" opacity=".06"/>`);
    parts.push(
      `<path d="M ${points.join(" L ")}" fill="none" stroke="${ACCENT}" stroke-width="1.8" stroke-linejoin="round"/>`
    );
    const last = history.length - 1;
    parts.push(
      `<circle cx="${x(last)}" cy="${y(Number(history[last].storage_pct))}" r="3" fill="${ACCENT}" stroke="#ffffff" stroke-width="1.5"/>`
    );
    const labels = [0, Math.floor(last / 2), last];
    labels.forEach((index) => {
      parts.push(
        `<text x="${x(index)}" y="${H - 3}" text-anchor="${index === 0 ? "start" : index === last ? "end" : "middle"}" font-size="12" fill="${FAINT}" font-family="IBM Plex Sans">${history[index].year}</text>`
      );
    });
    host.innerHTML = `<svg viewBox="0 0 360 150" preserveAspectRatio="xMidYMid meet" role="img" aria-hidden="true">${parts.join("")}</svg>`;
    host.setAttribute(
      "aria-label",
      `Storage trend from ${history[0].year} to ${history[history.length - 1].year}, ending at ${num(history[last].storage_pct, 0)} percent of capacity.`
    );
  }

  /* -----------------------------------------------------------------------
     Map
     ----------------------------------------------------------------------- */
  function initMap(payload) {
    const host = document.getElementById("map");
    if (!host) return;
    if (window.__aquaMap) {
      window.__aquaMap.remove();
      window.__aquaMap = null;
    }
    const fallback = document.getElementById("map-fallback");
    if (!window.L) {
      if (fallback) fallback.hidden = false;
      return;
    }
    if (fallback) fallback.hidden = true;

    const map = L.map(host, {
      zoomControl: true,
      attributionControl: false,
      scrollWheelZoom: false,
      preferCanvas: true,
    });
    window.__aquaMap = map;
    map.createPane("basemap").style.zIndex = 200;
    map.createPane("grid").style.zIndex = 210;
    map.createPane("labels").style.zIndex = 250;

    const bbox = payload.country && payload.country.bbox;
    if (bbox && bbox.length === 4) {
      map.fitBounds(
        [
          [bbox[1], bbox[0]],
          [bbox[3], bbox[2]],
        ],
        { padding: [22, 22], maxZoom: 6 }
      );
    } else {
      map.setView([payload.country.lat || 20, payload.country.lon || 0], 4);
    }

    // Vector basemap: Natural Earth countries, graticule and labels. No
    // external raster tiles, so the map works offline and never hits a tile
    // usage policy.
    const mapRef = map;

    function ringCenter(ring) {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      ring.forEach(([x, y]) => {
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      });
      return [(minY + maxY) / 2, (minX + maxX) / 2];
    }

    function largestPolygonCenter(feature) {
      const geometry = feature.geometry;
      if (!geometry) return null;
      if (geometry.type === "Polygon") {
        return ringCenter(geometry.coordinates[0]);
      }
      if (geometry.type === "MultiPolygon") {
        let best = null;
        let bestArea = -1;
        geometry.coordinates.forEach((polygon) => {
          const ring = polygon[0];
          const xs = ring.map((point) => point[0]);
          const ys = ring.map((point) => point[1]);
          const area =
            (Math.max(...xs) - Math.min(...xs)) *
            (Math.max(...ys) - Math.min(...ys));
          if (area > bestArea) {
            bestArea = area;
            best = ringCenter(ring);
          }
        });
        return best;
      }
      return null;
    }

    async function addBasemap() {
      try {
        if (!window.__worldGeo) {
          const response = await fetch("/static/hydro/geo/countries-110m.geojson");
          if (!response.ok) throw new Error("boundary file unavailable");
          window.__worldGeo = await response.json();
        }
        if (window.__aquaMap !== mapRef) return;

        const world = L.geoJSON(window.__worldGeo, {
          pane: "basemap",
          interactive: false,
          style: (feature) => {
            const selected =
              feature.properties && feature.properties.iso2 === payload.country.iso2;
            return {
              color: selected ? ACCENT : "#cfd8d2",
              weight: selected ? 1.6 : 0.6,
              opacity: selected ? 0.95 : 0.7,
              fillColor: selected ? "#e7f1f2" : "#f4f5ef",
              fillOpacity: selected ? 0.82 : 0.92,
            };
          },
        }).addTo(mapRef);

        const grid = L.layerGroup();
        for (let lat = -80; lat <= 80; lat += 5) {
          L.polyline(
            [
              [lat, -180],
              [lat, 180],
            ],
            { pane: "grid", color: "#c7d5d0", weight: 0.5, opacity: 0.45, interactive: false }
          ).addTo(grid);
        }
        for (let lon = -180; lon <= 180; lon += 5) {
          L.polyline(
            [
              [-85, lon],
              [85, lon],
            ],
            { pane: "grid", color: "#c7d5d0", weight: 0.5, opacity: 0.45, interactive: false }
          ).addTo(grid);
        }
        grid.addTo(mapRef);

        const viewport = mapRef.getBounds().pad(0.15);
        world.eachLayer((layer) => {
          const feature = layer.feature;
          if (!feature || !feature.properties || !feature.properties.name) return;
          const selected =
            feature.properties.iso2 === payload.country.iso2;
          const center = selected
            ? [payload.country.lat, payload.country.lon]
            : largestPolygonCenter(feature);
          if (!center || !viewport.contains(center)) return;
          L.marker(center, {
            pane: "labels",
            interactive: false,
            keyboard: false,
            icon: L.divIcon({
              className: `map-country-label${selected ? " is-selected" : ""}`,
              html: esc(feature.properties.name),
              iconSize: null,
              iconAnchor: [0, 0],
            }),
          }).addTo(mapRef);
        });
      } catch (error) {
        const bbox = payload.country && payload.country.bbox;
        if (bbox && bbox.length === 4) {
          L.rectangle(
            [
              [bbox[1], bbox[0]],
              [bbox[3], bbox[2]],
            ],
            {
              pane: "basemap",
              color: ACCENT,
              weight: 1.4,
              fillColor: "#e7f1f2",
              fillOpacity: 0.55,
            }
          ).addTo(mapRef);
        }
      }
    }
    addBasemap();

    const layers = {
      reservoirs: L.layerGroup(),
      aquifers: L.layerGroup(),
      soil: L.layerGroup(),
      rain: L.layerGroup(),
    };
    const markers = {};

    (payload.reservoirs || []).forEach((row) => {
      const radius = Math.max(5, Math.min(15, 4 + Math.sqrt(Number(row.capacity_mm3) || 0) / 2.4));
      const color = STATUS_COLORS[row.status] || MUTED;
      const marker = L.circleMarker([row.lat, row.lon], {
        radius,
        color: "#ffffff",
        weight: 1.5,
        fillColor: color,
        fillOpacity: 0.9,
      });
      marker.bindTooltip(
        `<strong>${esc(row.name)}</strong><br>${num(row.storage_pct, 1)}% storage · ${num(row.cover_days, 0)} d runway`,
        { direction: "top", sticky: true, opacity: 0.95 }
      );
      marker.on("click", () => {
        if (window.__aquaSelectReservoir) window.__aquaSelectReservoir(row.id, true);
      });
      marker.addTo(layers.reservoirs);
      markers[row.id] = { marker, row };
    });

    (payload.aquifers || []).forEach((row) => {
      if (!row.lat || !row.lon) return;
      const radius = Math.max(8, Math.min(18, 7 + Math.sqrt(Number(row.volume_km3) || 0) / 5.5));
      const marker = L.circleMarker([row.lat, row.lon], {
        radius,
        color: "#a86f0c",
        weight: 1.2,
        dashArray: "4 3",
        fillColor: "#a86f0c",
        fillOpacity: 0.12,
      });
      marker.bindTooltip(
        `<strong>${esc(row.name)}</strong><br>${num(row.volume_km3, 0)} km³ · ${num(row.stress_ratio, 1)}× extraction/recharge · ${num(row.trend_m_per_year, 2)} m/yr`,
        { direction: "top", sticky: true }
      );
      marker.addTo(layers.aquifers);
    });

    if (payload.soil && payload.soil.current !== null && payload.soil.current !== undefined) {
      const percentile = Number(payload.soil.percentile);
      const radius = Math.max(28, Math.min(70, 26 + (Number.isFinite(percentile) ? percentile : 50) / 2));
      const centroid = payload.hydrologic_centroid || payload.country;
      const marker = L.circleMarker([centroid.lat, centroid.lon], {
        radius,
        color: ACCENT,
        weight: 1,
        dashArray: "2 5",
        fillColor: ACCENT,
        fillOpacity: 0.06,
      });
      marker.bindTooltip(
        `<strong>Surface soil wetness</strong><br>${num(payload.soil.current, 3)} · ${num(payload.soil.percentile, 0)}th percentile`,
        { direction: "top", sticky: true }
      );
      marker.addTo(layers.soil);
    }

    (payload.reservoirs || []).forEach((row) => {
      if (!row.rain_3d_mm) return;
      const radius = Math.max(4, Math.min(13, 3 + Number(row.rain_3d_mm) * 0.6));
      const marker = L.circleMarker([row.lat, row.lon], {
        radius,
        color: CHART_2,
        weight: 1,
        fillColor: CHART_2,
        fillOpacity: 0.24,
      });
      marker.bindTooltip(`3-day rain at ${esc(row.name)}: ${num(row.rain_3d_mm, 1)} mm`, {
        direction: "top",
        sticky: true,
      });
      marker.addTo(layers.rain);
    });

    const defaults = { reservoirs: true, aquifers: true, soil: true, rain: false };
    Object.entries(defaults).forEach(([key, visible]) => {
      if (visible) layers[key].addTo(map);
    });

    window.__mapLayers = {
      toggle(key) {
        const layer = layers[key];
        if (!layer) return false;
        if (map.hasLayer(layer)) {
          map.removeLayer(layer);
          return false;
        }
        layer.addTo(map);
        return true;
      },
    };
    window.__aquaMarkerCount = Object.keys(markers).length;

    function selectReservoir(id, pan) {
      const entry = markers[id];
      const detail = document.getElementById("reservoir-detail");
      if (!entry || !detail) return;
      const row = entry.row;
      const horizon = ((payload.horizon && payload.horizon.reservoirs) || []).find(
        (item) => String(item.id) === String(id)
      );
      Object.values(markers).forEach((item) => {
        item.marker.setStyle({ color: "#ffffff", weight: 1.5 });
      });
      entry.marker.setStyle({ color: INK, weight: 3 });
      entry.marker.bringToFront();
      if (pan) map.panTo([row.lat, row.lon], { animate: true, duration: 0.25 });
      detail.hidden = false;
      detail.innerHTML = `
        <div class="reservoir-detail-head">
          <div>
            <h3>${esc(row.name)}</h3>
            <p>${esc(row.source_name || row.storage_source)}${row.is_reference_pool ? " · reference pool, not a physical dam" : ""}</p>
          </div>
          <button class="detail-close" type="button" aria-label="Close reservoir detail">×</button>
        </div>
        <div class="detail-grid">
          <div><span>Storage</span><strong>${num(row.storage_pct, 1)}%</strong></div>
          <div><span>Usable</span><strong>${num(row.usable_mm3, 0)} Mm³</strong></div>
          <div><span>Runway</span><strong>${num(row.cover_days, 0)} d</strong></div>
          <div><span>Demand</span><strong>${num(row.demand_mm3_day, 2)} Mm³/d</strong></div>
          <div><span>Rain 3d</span><strong>${num(row.rain_3d_mm, 1)} mm</strong></div>
          <div><span>Rain arrival</span><strong>${horizon && horizon.days_to_rain ? `${horizon.days_to_rain} d` : "–"}</strong></div>
        </div>
        <div class="detail-grid" style="grid-template-columns:1fr 1fr;margin-top:6px;padding-top:6px">
          <div><span>Capacity</span><strong>${num(row.capacity_mm3, 0)} Mm³</strong></div>
          <div><span>State</span><strong style="color:${STATUS_COLORS[row.status] || INK}">${esc(row.status_label)}</strong></div>
        </div>`;
      document.querySelectorAll("tr[data-reservoir-id]").forEach((tr) => {
        tr.classList.toggle("is-selected", String(tr.dataset.reservoirId) === String(id));
      });
    }

    window.__aquaSelectReservoir = selectReservoir;
    // Restore a selected marker after a partial swap.
    const selectedRow = document.querySelector("tr.is-selected");
    if (selectedRow) {
      // Selection is intentionally reset on scenario changes so verdict and map stay in sync.
      selectedRow.classList.remove("is-selected");
    }
  }

  /* -----------------------------------------------------------------------
     Scenario navigation and partial page swap
     ----------------------------------------------------------------------- */
  function formParams(form, rainOverride) {
    const formData = new FormData(form);
    const active = form.querySelector("[data-rain].is-active");
    const rain = rainOverride || formData.get("rain") || (active && active.dataset.rain) || "forecast";
    const demand = formData.get("demand") || "1.0";
    const horizon = formData.get("horizon") || "14";
    return new URLSearchParams({ rain: String(rain), demand: String(demand), horizon: String(horizon) });
  }

  function scenarioUrl(form, rainOverride) {
    const params = formParams(form, rainOverride);
    return `${form.action}?${params.toString()}`;
  }

  async function navigate(url, options) {
    const opts = options || {};
    if (navigating) return;
    const root = document.getElementById("dashboard-root");
    if (!root) return;
    navigating = true;
    root.setAttribute("aria-busy", "true");
    root.style.opacity = "0.62";
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/html" },
      });
      if (!response.ok) throw new Error(`Scenario request failed (${response.status})`);
      const html = await response.text();
      const parsed = new DOMParser().parseFromString(html, "text/html");
      const nextRoot = parsed.getElementById("dashboard-root");
      if (!nextRoot) throw new Error("The scenario response did not contain the dashboard.");
      root.innerHTML = nextRoot.innerHTML;
      document.title = parsed.title || document.title;
      if (opts.push !== false) {
        history.pushState({}, "", url);
      }
      initDashboard();
      const verdict = document.getElementById("verdict-label");
      if (verdict) {
        verdict.setAttribute("tabindex", "-1");
        verdict.focus({ preventScroll: true });
      }
    } catch (error) {
      if (window.Aqua) window.Aqua.toast(error.message, "error");
    } finally {
      navigating = false;
      root.removeAttribute("aria-busy");
      root.style.opacity = "";
    }
  }

  function wireScenarioControls() {
    document.addEventListener("submit", (event) => {
      const form = event.target.closest("#scenario-form");
      if (!form) return;
      event.preventDefault();
      const submitter = event.submitter;
      let rain = null;
      if (submitter && submitter.name === "rain") rain = submitter.value;
      navigate(scenarioUrl(form, rain));
    });

    document.addEventListener("input", (event) => {
      if (event.target.id !== "demand-stress") return;
      const output = document.getElementById("demand-output");
      if (output) output.textContent = `${Number(event.target.value).toFixed(1)}×`;
    });

    document.addEventListener("change", (event) => {
      const form = event.target.closest("#scenario-form");
      if (!form) return;
      if (event.target.id === "demand-stress" || event.target.id === "horizon-select") {
        navigate(scenarioUrl(form));
      }
    });

    window.addEventListener("popstate", () => {
      navigate(window.location.href, { push: false });
    });
  }

  function wireMapAndRows() {
    document.addEventListener("click", (event) => {
      const layerButton = event.target.closest(".layer-toggle");
      if (layerButton && window.__mapLayers) {
        const key = layerButton.dataset.layer;
        const visible = window.__mapLayers.toggle(key);
        layerButton.classList.toggle("is-active", visible);
        layerButton.setAttribute("aria-pressed", String(visible));
        return;
      }
      const close = event.target.closest(".detail-close");
      if (close) {
        const detail = document.getElementById("reservoir-detail");
        if (detail) detail.hidden = true;
        document.querySelectorAll("tr.is-selected").forEach((tr) => tr.classList.remove("is-selected"));
        return;
      }
      const row = event.target.closest("tr[data-reservoir-id]");
      if (row && window.__aquaSelectReservoir) {
        window.__aquaSelectReservoir(row.dataset.reservoirId, true);
      }
    });

    document.addEventListener("keydown", (event) => {
      const row = event.target.closest("tr[data-reservoir-id]");
      if (!row) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (window.__aquaSelectReservoir) window.__aquaSelectReservoir(row.dataset.reservoirId, true);
      }
    });
  }

  function initDashboard() {
    const payload = data();
    if (!payload) return;
    renderRunway(payload);
    renderTrend(payload);
    initMap(payload);
  }

  wireScenarioControls();
  wireMapAndRows();
  document.addEventListener("DOMContentLoaded", initDashboard);
  if (document.readyState !== "loading") {
    initDashboard();
  }
})();
