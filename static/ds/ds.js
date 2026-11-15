/* AquaState design-system behaviour: nav menu, mobile drawer, search palette,
   tooltips and toasts. No dependencies; every page loads it. */
(function () {
  "use strict";

  const DS = (window.DS = window.DS || {});
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  DS.esc = function (value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  };
  DS.fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  /* ---------------- theme (light / dark) ---------------- */
  const html = document.documentElement;
  const THEME_KEY = "aquastate.theme";
  DS.theme = () => (html.dataset.theme === "light" ? "light" : "dark");
  // Resolved value of a theme token, e.g. DS.cssVar("--t-map-bg") — maps and charts read colours this way.
  DS.cssVar = (name) => getComputedStyle(html).getPropertyValue(name).trim();
  function savedTheme() {
    try { const t = localStorage.getItem(THEME_KEY); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; }
  }
  function syncThemeUi() {
    const next = DS.theme() === "dark" ? "light" : "dark";
    $$("[data-theme-toggle]").forEach((b) => {
      b.setAttribute("aria-label", `Switch to ${next} theme`);
      if (b.classList.contains("drawer-theme")) b.textContent = `Switch to ${next} theme`;
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", DS.theme() === "dark" ? "#081012" : "#f2f5f2");
  }
  DS.setTheme = function (theme, persist) {
    if (theme !== "light" && theme !== "dark") return;
    html.classList.add("theme-switching");
    html.dataset.theme = theme;
    html.style.colorScheme = theme;
    if (persist) { try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode */ } }
    syncThemeUi();
    window.dispatchEvent(new CustomEvent("ds:theme", { detail: { theme } }));
    setTimeout(() => html.classList.remove("theme-switching"), 400);
  };
  $$("[data-theme-toggle]").forEach((b) => b.addEventListener("click", () => DS.setTheme(DS.theme() === "dark" ? "light" : "dark", true)));
  // Follow the system setting until the user picks a theme explicitly.
  const mq = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)");
  if (mq && mq.addEventListener) mq.addEventListener("change", (e) => { if (!savedTheme()) DS.setTheme(e.matches ? "light" : "dark", false); });
  syncThemeUi();

  /* ---------------- toast ---------------- */
  let toastTimer = null;
  DS.toast = function (message, ms = 3200) {
    const el = $("#ds-toast");
    if (!el) return;
    el.textContent = message;
    el.dataset.show = "true";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.dataset.show = "false"), ms);
  };

  /* ---------------- tooltip: [data-tip] or [data-tip-title] ---------------- */
  const tip = $("#ds-tip");
  let tipFor = null;
  function placeTip(target) {
    const r = target.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = r.left + r.width / 2 - tw / 2;
    let y = r.top - th - 10;
    if (y < 8) y = r.bottom + 10;
    x = Math.max(8, Math.min(window.innerWidth - tw - 8, x));
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function showTip(target) {
    if (!tip) return;
    const title = target.dataset.tipTitle;
    const body = target.dataset.tip || "";
    tip.innerHTML = (title ? `<strong>${DS.esc(title)}</strong>` : "") + `<span>${DS.esc(body)}</span>`;
    tip.dataset.show = "true";
    tipFor = target;
    placeTip(target);
  }
  function hideTip() {
    if (!tip) return;
    tip.dataset.show = "false";
    tipFor = null;
  }
  document.addEventListener("pointerover", (e) => {
    const t = e.target.closest("[data-tip],[data-tip-title]");
    if (t && t !== tipFor) showTip(t);
    else if (!t && tipFor) hideTip();
  });
  document.addEventListener("focusin", (e) => {
    const t = e.target.closest("[data-tip],[data-tip-title]");
    if (t) showTip(t);
  });
  document.addEventListener("focusout", hideTip);
  window.addEventListener("scroll", () => tipFor && hideTip(), { passive: true });

  /* ---------------- "More" menu ---------------- */
  $$("[data-menu]").forEach((menu) => {
    const button = $("button", menu);
    const close = () => { menu.dataset.open = "false"; button.setAttribute("aria-expanded", "false"); };
    const open = () => { menu.dataset.open = "true"; button.setAttribute("aria-expanded", "true"); };
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.dataset.open === "true" ? close() : open();
    });
    menu.addEventListener("keydown", (e) => {
      const items = $$("a", menu);
      const i = items.indexOf(document.activeElement);
      if (e.key === "Escape") { close(); button.focus(); }
      if (e.key === "ArrowDown") { e.preventDefault(); open(); (items[i + 1] || items[0]).focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); (items[i - 1] || items[items.length - 1]).focus(); }
    });
    document.addEventListener("click", (e) => { if (!menu.contains(e.target)) close(); });
  });

  /* ---------------- mobile drawer ---------------- */
  const drawer = $("[data-drawer]");
  const drawerBtn = $("[data-drawer-open]");
  function setDrawer(open) {
    if (!drawer) return;
    drawer.dataset.open = open ? "true" : "false";
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    if (drawerBtn) drawerBtn.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.style.overflow = open ? "hidden" : "";
    if (open) setTimeout(() => $("a", drawer)?.focus(), 30);
    else drawerBtn?.focus();
  }
  drawerBtn?.addEventListener("click", () => setDrawer(true));
  $$("[data-drawer-close]").forEach((el) => el.addEventListener("click", () => setDrawer(false)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer?.dataset.open === "true") setDrawer(false);
  });

  /* ---------------- search palette ---------------- */
  const dialog = $("#ds-search");
  const input = $("#ds-search-input");
  const list = $("#ds-search-results");
  const PAGES = [
    { label: "Overview", sub: "World water & climate picture", url: "/" , icon: "◎" },
    { label: "Map viewer", sub: "Every country, region by region", url: "/map/", icon: "▦" },
    { label: "Dam atlas", sub: "82k catalogued dams", url: "/dams/", icon: "≋" },
    { label: "Hazard board", sub: "Drought, flood, fire, desertification", url: "/hazards/", icon: "△" },
    { label: "Water runway", sub: "Stored water vs next rain (Algeria)", url: "/water/DZ/", icon: "↗" },
    { label: "Dam simulator", sub: "Pilot reservoirs", url: "/pilot/", icon: "◉" },
    { label: "Methodology", sub: "Formulas and weights", url: "/methodology/", icon: "ƒ" },
    { label: "Data sources", sub: "Live, cached, missing", url: "/sources/", icon: "⇣" },
  ];
  let countries = null, wilayas = null, damAbort = null, active = 0, current = [];

  function loadIndex() {
    const jobs = [];
    if (!countries) {
      jobs.push(fetch("/api/world/").then((r) => r.json()).then((p) => {
        countries = (p.countries || []).map((c) => ({ label: c.name, sub: c.status_label ? `Country · ${c.status_label}` : "Country", meta: c.score != null ? `${Number(c.score).toFixed(1)}` : "", url: `/country/${c.iso2}/`, icon: c.iso2, key: DS.fold(c.name + " " + c.iso2 + " " + (c.iso3 || "")) }));
      }).catch(() => { countries = []; }));
    }
    if (!wilayas) {
      jobs.push(fetch("/api/algeria/wilayas/").then((r) => r.json()).then((p) => {
        wilayas = (p.wilayas || []).map((w) => ({ label: w.name, sub: `Wilaya ${w.code.slice(3)} · Algeria`, meta: w.layers && w.layers.drought != null ? `drought ${Math.round(w.layers.drought)}` : "", url: `/map/?w=${w.code}`, icon: w.code.slice(3), key: DS.fold(w.name + " " + w.code) }));
      }).catch(() => { wilayas = []; }));
    }
    return Promise.all(jobs);
  }

  function rank(items, q, limit) {
    return items
      .map((it) => {
        const i = it.key.indexOf(q);
        return i < 0 ? null : { it, s: (i === 0 ? 0 : it.key.indexOf(" " + q) >= 0 ? 1 : 2) + it.label.length / 200 };
      })
      .filter(Boolean).sort((a, b) => a.s - b.s).slice(0, limit).map((x) => x.it);
  }

  function render(groups) {
    current = [];
    let html = "";
    groups.forEach(([name, items]) => {
      if (!items.length) return;
      html += `<div class="palette__group">${DS.esc(name)}</div>`;
      items.forEach((it) => {
        const idx = current.push(it) - 1;
        html += `<a class="palette__item" role="option" id="ds-opt-${idx}" href="${DS.esc(it.url)}" data-idx="${idx}" aria-selected="${idx === active}">
          <span class="palette__icon">${DS.esc(it.icon || "•")}</span>
          <span class="palette__text"><span>${DS.esc(it.label)}</span><small>${DS.esc(it.sub || "")}</small></span>
          ${it.meta ? `<span class="palette__meta">${DS.esc(it.meta)}</span>` : ""}
        </a>`;
      });
    });
    if (!current.length) {
      html = `<div class="ds-state"><strong>No matches</strong><span>Try a country, a wilaya (e.g. “Tlemcen”) or a dam name.</span></div>`;
    }
    list.innerHTML = html;
    input.setAttribute("aria-activedescendant", current.length ? `ds-opt-${active}` : "");
  }

  function search() {
    const q = DS.fold(input.value.trim());
    active = 0;
    if (!q) {
      render([["Jump to", PAGES], ["Popular", [
        { label: "Algeria", sub: "Country sheet", url: "/country/DZ/", icon: "DZ" },
        { label: "Algiers", sub: "Wilaya 16 · Map viewer", url: "/map/?w=DZ-16", icon: "16" },
        { label: "Beni Haroun", sub: "Pilot dam · Mila", url: "/dam/beni-haroun/", icon: "≋" },
      ]]]);
      return;
    }
    const pages = PAGES.filter((p) => DS.fold(p.label + " " + p.sub).includes(q));
    const cs = rank(countries || [], q, 5);
    const maps = cs.slice(0, 3).map((c) => ({ label: `${c.label} — regional map`, sub: "Regions coloured by drought, flood, fire…", url: `/map/?c=${c.icon}`, icon: "▦" }));
    const base = [["Pages", pages.slice(0, 3)], ["Wilayas", rank(wilayas || [], q, 5)], ["Countries", cs], ["Regional maps", maps]];
    render(base.concat([["Dams", []]]));
    if (q.length < 2) return;
    if (damAbort) damAbort.abort();
    damAbort = new AbortController();
    const asked = input.value;
    fetch(`/api/dams/?q=${encodeURIComponent(input.value.trim())}&page_size=6`, { signal: damAbort.signal })
      .then((r) => r.json())
      .then((p) => {
        if (asked !== input.value) return;
        const dams = (p.results || []).map((d) => ({
          label: d.name, sub: `${d.is_monitored ? "Monitored dam" : "Catalogued dam"} · ${d.country_name || d.country_iso2 || ""}`,
          meta: d.capacity_m3 ? `${(d.capacity_m3 / 1e6).toFixed(0)} Mm³` : "",
          url: `/dam/${encodeURIComponent(d.pilot_slug || d.wikidata_id)}/`, icon: "≋",
        }));
        render(base.concat([["Dams", dams]]));
      })
      .catch(() => {});
  }
  const debounced = (() => { let t; return () => { clearTimeout(t); t = setTimeout(search, 140); }; })();

  function openSearch() {
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    input.value = "";
    search();
    input.focus();
    loadIndex().then(() => { if (dialog.open) search(); });
  }
  DS.openSearch = openSearch;
  $$("[data-search-open]").forEach((b) => b.addEventListener("click", openSearch));
  $$("[data-search-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
  dialog?.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  input?.addEventListener("input", debounced);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!current.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + current.length) % current.length;
      $$(".palette__item", list).forEach((el) => el.setAttribute("aria-selected", String(Number(el.dataset.idx) === active)));
      $(`#ds-opt-${active}`)?.scrollIntoView({ block: "nearest" });
      input.setAttribute("aria-activedescendant", `ds-opt-${active}`);
    } else if (e.key === "Enter" && current[active]) {
      e.preventDefault();
      window.location.href = current[active].url;
    }
  });
  document.addEventListener("keydown", (e) => {
    const typing = /input|textarea|select/i.test(document.activeElement?.tagName || "") || document.activeElement?.isContentEditable;
    if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
      e.preventDefault();
      openSearch();
    }
  });
})();
