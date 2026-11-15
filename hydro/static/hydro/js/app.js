/* global window, document, fetch */
(function () {
  "use strict";

  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.content : "";

  function escapeHTML(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  let toastTimer = null;
  function toast(message, kind) {
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    node.dataset.kind = kind || "info";
    window.clearTimeout(toastTimer);
    requestAnimationFrame(() => node.classList.add("is-visible"));
    toastTimer = window.setTimeout(() => {
      node.classList.remove("is-visible");
      window.setTimeout(() => {
        node.hidden = true;
      }, 220);
    }, 4200);
  }

  async function fetchJSON(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    opts.headers = Object.assign(
      {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken,
      },
      opts.headers || {}
    );
    const response = await fetch(url, opts);
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch (error) {
      payload = { detail: text };
    }
    if (!response.ok) {
      const message =
        (payload && (payload.message || payload.detail || payload.error)) ||
        `Request failed (${response.status})`;
      throw new Error(message);
    }
    return payload;
  }

  function fmt(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    });
  }

  // Country switch: native form, auto-submit once JS is available.
  const countryForm = document.querySelector(".country-form");
  const countrySelect = document.getElementById("country-select");
  if (countryForm && countrySelect) {
    countrySelect.addEventListener("change", () => countryForm.submit());
  }

  // Refresh: POST, then reload. The server persists a snapshot and returns the new state.
  const refreshButton = document.getElementById("refresh-data");
  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      const url = refreshButton.dataset.url;
      if (!url) return;
      refreshButton.setAttribute("aria-busy", "true");
      refreshButton.disabled = true;
      const original = refreshButton.textContent;
      refreshButton.textContent = "Refreshing…";
      try {
        await fetchJSON(url, { method: "POST" });
        toast("Live sources refreshed. Reloading the index…");
        window.setTimeout(() => window.location.reload(), 450);
      } catch (error) {
        toast(`Refresh failed: ${error.message}`, "error");
        refreshButton.disabled = false;
        refreshButton.removeAttribute("aria-busy");
        refreshButton.textContent = original;
      }
    });
  }

  // Optional OSM import for countries that only have a reference pool.
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("#import-osm");
    if (!button) return;
    const url = button.dataset.url;
    if (!url) return;
    button.disabled = true;
    button.textContent = "Importing…";
    try {
      const payload = await fetchJSON(url, { method: "POST" });
      toast(payload.message || "Reservoir inventory imported.");
      window.setTimeout(() => window.location.reload(), 500);
    } catch (error) {
      toast(`Import failed: ${error.message}`, "error");
      button.disabled = false;
      button.textContent = "Import OSM reservoirs";
    }
  });

  window.Aqua = { escapeHTML, fetchJSON, fmt, toast, csrfToken };
})();
