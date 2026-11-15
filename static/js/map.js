/* AquaState map — MapLibre 6 ESM, local style, local SVG fallback. */
(function () {
  "use strict";
  // Basemap colours from the light/dark theme tokens (static/ds/themes.css).
  function pilotTheme() {
    const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    return { bg: css("--t-map-bg", "#090d10"), land: css("--t-map-land", "#0d171b"), edge: css("--t-map-edge", "#334750"), accent: css("--t-link", "#38d6c9") };
  }

  const STATUS_COLORS = {
    CRITICAL: "#ef6f82",
    STRESSED: "#d99a5b",
    WATCH: "#d9c05f",
    STABLE: "#6fc7d8",
    RECHARGING: "#4fd39b",
    SURPLUS: "#63d8e8",
    NO_DATA: "#7f929b",
  };

  const el = document.getElementById("map");
  if (!el) return;
  const fallback = document.getElementById("map-fallback");
  const mapUrl = el.dataset.mapUrl || `/api/pilot/dams/${focus}/map/`;
  const panelUrl = el.dataset.panelUrl || "/dashboard/partials/panel/";
  const focus = el.dataset.focus;
  let map = null;
  let markers = [];
  let selected = focus;

  function setActiveMarker(slug) {
    selected = slug;
    markers.forEach((entry) => {
      entry.element.classList.toggle("is-active", entry.slug === slug);
    });
    if (map) updateLabels();
  }

  function updateLabels() {
    if (!map) return;
    const mapRect = el.getBoundingClientRect();
    const placed = [];
    const ordered = markers.slice().sort((a, b) => {
      if (a.slug === selected) return -1;
      if (b.slug === selected) return 1;
      return 0;
    });
    ordered.forEach((entry) => {
      const label = entry.element.querySelector(".dam-marker__label");
      if (!label) return;
      label.style.visibility = "visible";
      const rect = label.getBoundingClientRect();
      const clipped =
        rect.left < mapRect.left + 6 ||
        rect.right > mapRect.right - 6 ||
        rect.top < mapRect.top + 6 ||
        rect.bottom > mapRect.bottom - 6;
      const overlaps = placed.some(
        (other) =>
          !(
            rect.right + 3 < other.left ||
            rect.left - 3 > other.right ||
            rect.bottom + 3 < other.top ||
            rect.top - 3 > other.bottom
          )
      );
      if (entry.slug !== selected && (clipped || overlaps)) {
        label.style.visibility = "hidden";
      } else {
        placed.push(rect);
      }
    });
  }

  function selectDam(slug, push) {
    if (!slug) return;
    setActiveMarker(slug);
    const country = el.dataset.country || "";
    if (push !== false) {
      const url = new URL(window.location.href);
      url.searchParams.set("dam", slug);
      if (country) url.searchParams.set("country", country);
      window.history.pushState({ dam: slug }, "", url);
    }
    const target = document.getElementById("panel-shell");
    if (!target) return;
    if (window.htmx) {
      window.htmx.ajax("GET", panelUrl + slug + "/", {
        target: "#panel-shell",
        swap: "innerHTML",
      });
    } else {
      fetch(panelUrl + slug + "/", { headers: { Accept: "text/html" } })
        .then((response) => response.text())
        .then((html) => { target.innerHTML = html; });
    }
  }

  function addSources(data) {
    map.addSource("countries", {
      type: "geojson",
      data: { type: "FeatureCollection", features: data.countries || [] },
    });
    map.addSource("basins", {
      type: "geojson",
      data: { type: "FeatureCollection", features: data.basins || [] },
    });

    map.addLayer({
      id: "countries-fill",
      type: "fill",
      source: "countries",
      paint: { "fill-color": pilotTheme().land, "fill-opacity": 0.96 },
    });
    map.addLayer({
      id: "countries-line",
      type: "line",
      source: "countries",
      paint: { "line-color": pilotTheme().edge, "line-width": 1.2 },
    });
    map.addLayer({
      id: "basins-fill",
      type: "fill",
      source: "basins",
      paint: { "fill-color": pilotTheme().accent, "fill-opacity": 0.10 },
    });
    map.addLayer({
      id: "basins-line",
      type: "line",
      source: "basins",
      paint: { "line-color": pilotTheme().accent, "line-opacity": 0.45, "line-width": 1 },
    });

    (data.features || []).forEach((feature, index) => {
      const [lon, lat] = feature.geometry.coordinates;
      const properties = feature.properties || {};
      const button = document.createElement("button");
      button.type = "button";
      button.className = `dam-marker status-${String(properties.status || "NO_DATA").toLowerCase()} dam-marker--${["above", "below", "left", "right"][index % 4]}`;
      button.setAttribute("aria-label", `${properties.name}, ${properties.status || "NO_DATA"}`);
      button.innerHTML =
        '<span class="dam-marker__ring"></span>' +
        `<span class="dam-marker__label">${properties.name}</span>`;
      button.addEventListener("click", () => selectDam(properties.slug));
      const marker = new window.maplibregl.Marker({ element: button, anchor: "center" })
        .setLngLat([lon, lat])
        .addTo(map);
      markers.push({ slug: properties.slug, element: button, marker });
      if (properties.slug === selected) button.classList.add("is-active");
    });

    map.on("moveend", updateLabels);
    map.on("zoomend", updateLabels);

    const coords = (data.features || [])
      .map((feature) => feature.geometry.coordinates)
      .filter((pair) => Array.isArray(pair));
    if (coords.length) {
      const lons = coords.map((pair) => pair[0]);
      const lats = coords.map((pair) => pair[1]);
      const center = [
        (Math.min(...lons) + Math.max(...lons)) / 2,
        (Math.min(...lats) + Math.max(...lats)) / 2,
      ];
      const span = Math.max(0.6, Math.max(...lons) - Math.min(...lons));
      const fit = () => {
        map.resize();
        const width = Math.max(240, el.clientWidth - 240);
        const zoom = Math.max(4.5, Math.min(6.4, Math.log2((width / span) * 360 / 256)));
        map.jumpTo({ center: center, zoom: zoom });
        setTimeout(updateLabels, 60);
      };
      requestAnimationFrame(() => requestAnimationFrame(fit));
      setTimeout(fit, 120);
    }
  }

  function bindLayerToggles() {
    const layerMap = {
      basins: ["basins-fill", "basins-line"],
      countries: ["countries-fill", "countries-line"],
    };
    document.querySelectorAll("[data-layer]").forEach((input) => {
      input.addEventListener("change", () => {
        const visible = input.checked ? "visible" : "none";
        (layerMap[input.dataset.layer] || []).forEach((layer) => {
          if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", visible);
        });
        if (input.dataset.layer === "dams") {
          markers.forEach((entry) => {
            entry.element.style.display = input.checked ? "" : "none";
          });
        }
        if (input.dataset.layer === "labels") {
          el.classList.toggle("labels-off", !input.checked);
        }
      });
    });
  }

  async function boot() {
    try {
      const module = await import("/static/vendor/maplibre-gl.js");
      const maplibregl = module.default || module;
      window.maplibregl = maplibregl;
      if (maplibregl.setWorkerUrl) {
        maplibregl.setWorkerUrl("/static/vendor/maplibre-gl-worker.mjs");
      }
      const response = await fetch(mapUrl, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`map endpoint ${response.status}`);
      const data = await response.json();

      map = new maplibregl.Map({
        container: "map",
        style: {
          version: 8,
          sources: {},
          layers: [{ id: "ground", type: "background", paint: { "background-color": pilotTheme().bg } }],
        },
        center: [9, 35],
        zoom: 3.2,
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("load", () => {
        addSources(data);
        bindLayerToggles();
        if (fallback) fallback.hidden = true;
      });
      window.addEventListener("resize", () => { if (map) map.resize(); });
      // Light/dark theme switch: recolour the basemap layers in place (static/ds/themes.css tokens).
      window.addEventListener("ds:theme", () => {
        if (!map || !map.isStyleLoaded()) return;
        const t = pilotTheme();
        [["ground", "background-color", t.bg], ["countries-fill", "fill-color", t.land], ["countries-line", "line-color", t.edge],
         ["basins-fill", "fill-color", t.accent], ["basins-line", "line-color", t.accent]].forEach(([id, prop, value]) => {
          if (map.getLayer(id)) map.setPaintProperty(id, prop, value);
        });
      });
      window.addEventListener("popstate", () => {
        const params = new URLSearchParams(window.location.search);
        if (params.get("dam")) selectDam(params.get("dam"), false);
      });
    } catch (error) {
      if (fallback) fallback.hidden = false;
      console.warn("AquaState map fallback:", error);
    }
  }

  boot();
  window.dashboardSelect = selectDam;
})();
