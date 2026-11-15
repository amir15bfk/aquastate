/* Small interaction layer: HTMX error honesty and scenario focus. */
(function () {
  "use strict";

  document.addEventListener("htmx:responseError", function (event) {
    const target = event.detail && event.detail.target;
    if (!target) return;
    const status = event.detail.xhr ? event.detail.xhr.status : "";
    target.innerHTML =
      `<p class="scenario-status" role="alert">The scenario request failed (${status}). Observed values were not changed.</p>`;
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    const hero = event.detail && event.detail.target
      ? event.detail.target.querySelector("#hero")
      : null;
    if (hero) hero.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      const panel = document.getElementById("panel");
      if (panel) panel.focus();
    }
  });
})();
