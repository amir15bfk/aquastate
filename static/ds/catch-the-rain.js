/* Catch the Rain — the 404 mini-game.
   Canvas, no dependencies. The player is a water droplet; rain falls from drifting clouds.
   Catch a drop: +1 (gold drop: +3) and the reservoir fills. Miss a drop: lose a life (3 lives).
   States: idle -> playing <-> paused -> over -> playing. Exposes window.__rain for tests. */
(function () {
  "use strict";
  const canvas = document.getElementById("rain-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const stage = document.getElementById("rain-stage");
  const $ = (id) => document.getElementById(id);
  const ui = {
    score: $("rain-score"), best: $("rain-best"), lives: $("rain-lives"), reservoir: $("rain-reservoir"),
    intro: $("rain-intro"), over: $("rain-over"), paused: $("rain-paused"),
    overTitle: $("rain-over-title"), overText: $("rain-over-text"),
  };
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const C = {
    skyTop: "#0b2a33", skyBottom: "#123b3f", cloud: "#dfeeed", cloudShade: "#b9d3d1",
    drop: "#5ba7e8", dropHi: "#cfe7fb", gold: "#e5a23b", player: "#34c9b8", playerInk: "#072e2a",
    dune1: "#2a3b33", dune2: "#1c2a26", river: "#2b6f6a", splash: "#9fd0f5",
  };

  let W = 0, H = 0, dpr = 1;
  const game = {
    state: "idle", score: 0, lives: 3, best: 0, caught: 0,
    player: { x: 0, w: 46, h: 56, vx: 0, target: null },
    drops: [], clouds: [], splashes: [], t: 0, spawnIn: 0, speed: 1,
  };
  try { game.best = Number(localStorage.getItem("aquastate.rain.best") || 0); } catch (e) { game.best = 0; }

  /* ---------------- sizing ---------------- */
  function resize() {
    const r = stage.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(280, Math.round(r.width));
    H = Math.round(W < 560 ? W * 1.15 : W * 0.56);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const s = Math.max(0.75, Math.min(1.2, W / 760));
    game.player.w = 46 * s; game.player.h = 56 * s;
    if (!game.player.x) game.player.x = W / 2;
    game.player.x = Math.max(game.player.w / 2, Math.min(W - game.player.w / 2, game.player.x));
    if (!game.clouds.length) seedClouds();
    if (game.state !== "playing") draw();
  }
  function seedClouds() {
    game.clouds = Array.from({ length: 4 }, (_, i) => ({ x: (i + 0.5) * (W / 4) + (Math.random() - 0.5) * 40, y: 30 + Math.random() * 30, s: 0.8 + Math.random() * 0.5, v: (Math.random() < 0.5 ? -1 : 1) * (8 + Math.random() * 10) }));
  }

  /* ---------------- HUD ---------------- */
  function hud() {
    ui.score.textContent = game.score;
    ui.best.textContent = game.best;
    ui.lives.innerHTML = [0, 1, 2].map((i) => `<i class="nf-life${i < game.lives ? "" : " is-lost"}"></i>`).join("");
    ui.lives.setAttribute("aria-label", `${game.lives} ${game.lives === 1 ? "life" : "lives"} left`);
    ui.reservoir.style.height = Math.min(100, (game.caught % 25) / 25 * 100) + "%";
  }

  /* ---------------- states ---------------- */
  function start() {
    Object.assign(game, { state: "playing", score: 0, lives: 3, caught: 0, drops: [], splashes: [], t: 0, spawnIn: 0.6, speed: 1 });
    game.player.x = W / 2; game.player.vx = 0; game.player.target = null;
    ui.intro.hidden = true; ui.over.hidden = true; ui.paused.hidden = true;
    hud();
    last = performance.now();
    canvas.focus({ preventScroll: true });
    requestAnimationFrame(loop);
  }
  function gameOver() {
    game.state = "over";
    const record = game.score > game.best;
    if (record) {
      game.best = game.score;
      try { localStorage.setItem("aquastate.rain.best", String(game.best)); } catch (e) { /* private mode */ }
    }
    ui.overTitle.textContent = record && game.score > 0 ? "New best — the reservoir thanks you" : "The ground dried out";
    ui.overText.textContent = `You caught ${game.caught} drop${game.caught === 1 ? "" : "s"} for ${game.score} point${game.score === 1 ? "" : "s"}.`;
    ui.over.hidden = false;
    hud();
    draw();
    document.getElementById("rain-restart").focus({ preventScroll: true });
  }
  function pause(on) {
    if (game.state === "playing" && on) { game.state = "paused"; ui.paused.hidden = false; }
    else if (game.state === "paused" && !on) { game.state = "playing"; ui.paused.hidden = true; last = performance.now(); requestAnimationFrame(loop); }
  }

  /* ---------------- input ---------------- */
  const keys = { left: false, right: false };
  window.addEventListener("keydown", (e) => {
    if (game.state === "idle" || game.state === "over") return;
    if (e.key === "ArrowLeft" || e.key === "a" || e.key === "A") { keys.left = true; e.preventDefault(); }
    if (e.key === "ArrowRight" || e.key === "d" || e.key === "D") { keys.right = true; e.preventDefault(); }
    if (e.key === "p" || e.key === "P") pause(game.state === "playing");
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === "ArrowLeft" || e.key === "a" || e.key === "A") keys.left = false;
    if (e.key === "ArrowRight" || e.key === "d" || e.key === "D") keys.right = false;
  });
  function pointerX(e) { const r = canvas.getBoundingClientRect(); return e.clientX - r.left; }
  canvas.addEventListener("pointermove", (e) => { if (game.state === "playing" && (e.pointerType === "mouse" || e.buttons)) game.player.target = pointerX(e); });
  canvas.addEventListener("pointerdown", (e) => { if (game.state === "playing") { game.player.target = pointerX(e); canvas.setPointerCapture(e.pointerId); } });
  canvas.addEventListener("pointerleave", () => { game.player.target = null; });
  canvas.style.touchAction = "none";
  document.querySelectorAll(".nf-pad__btn").forEach((b) => {
    const dir = Number(b.dataset.dir);
    const on = (e) => { e.preventDefault(); game.player.target = null; if (dir < 0) keys.left = true; else keys.right = true; };
    const off = () => { if (dir < 0) keys.left = false; else keys.right = false; };
    b.addEventListener("pointerdown", on);
    ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, off));
  });
  $("rain-start").addEventListener("click", start);
  $("rain-restart").addEventListener("click", start);
  $("rain-resume").addEventListener("click", () => pause(false));
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(true); });
  window.addEventListener("resize", resize);

  /* ---------------- simulation ---------------- */
  function spawn() {
    const cloud = game.clouds[Math.floor(Math.random() * game.clouds.length)];
    const gold = Math.random() < 0.08;
    game.drops.push({
      x: Math.max(14, Math.min(W - 14, cloud.x + (Math.random() - 0.5) * 70 * cloud.s)),
      y: cloud.y + 18, r: gold ? 8 : 6.5, gold,
      vy: (120 + Math.random() * 60) * game.speed * (H / 430),
    });
  }
  function update(dt) {
    game.t += dt;
    game.speed = 1 + Math.min(1.6, game.score / 40);
    game.clouds.forEach((c) => {
      c.x += c.v * dt * (reduceMotion ? 0.3 : 1);
      if (c.x < 40 || c.x > W - 40) c.v *= -1;
    });
    const p = game.player;
    const accel = 2600, maxV = 520 * Math.max(0.8, W / 760);
    if (p.target != null) {
      p.x += (p.target - p.x) * Math.min(1, dt * 14);
      p.vx = 0;
    } else {
      const dir = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);
      p.vx = dir ? Math.max(-maxV, Math.min(maxV, p.vx + dir * accel * dt)) : p.vx * Math.pow(0.0008, dt);
      p.x += p.vx * dt;
    }
    p.x = Math.max(p.w / 2, Math.min(W - p.w / 2, p.x));

    game.spawnIn -= dt;
    if (game.spawnIn <= 0) { spawn(); game.spawnIn = Math.max(0.32, 0.95 - game.score * 0.012) * (0.7 + Math.random() * 0.6); }

    const ground = H - 46;
    const top = ground - p.h;
    for (let i = game.drops.length - 1; i >= 0; i--) {
      const d = game.drops[i];
      d.y += d.vy * dt;
      if (d.y + d.r >= top + 8 && d.y - d.r <= ground && Math.abs(d.x - p.x) < p.w / 2 + d.r * 0.6) {
        game.drops.splice(i, 1);
        game.score += d.gold ? 3 : 1;
        game.caught += 1;
        splash(d.x, top + 6, d.gold ? C.gold : C.splash, 7);
        hud();
      } else if (d.y > ground) {
        game.drops.splice(i, 1);
        game.lives -= 1;
        splash(d.x, ground, "#b58a5c", 5);
        hud();
        if (game.lives <= 0) { gameOver(); return; }
      }
    }
    for (let i = game.splashes.length - 1; i >= 0; i--) {
      const s = game.splashes[i];
      s.life -= dt; s.x += s.vx * dt; s.y += s.vy * dt; s.vy += 600 * dt;
      if (s.life <= 0) game.splashes.splice(i, 1);
    }
  }
  function splash(x, y, color, n) {
    for (let k = 0; k < n; k++) game.splashes.push({ x, y, vx: (Math.random() - 0.5) * 180, vy: -80 - Math.random() * 140, life: 0.45, color });
  }

  /* ---------------- drawing ---------------- */
  function dropPath(x, y, r) {
    ctx.beginPath();
    ctx.moveTo(x, y - r * 1.8);
    ctx.bezierCurveTo(x + r * 0.9, y - r * 0.6, x + r, y + r * 0.2, x + r, y + r * 0.35);
    ctx.arc(x, y + r * 0.35, r, 0, Math.PI);
    ctx.bezierCurveTo(x - r, y + r * 0.2, x - r * 0.9, y - r * 0.6, x, y - r * 1.8);
    ctx.closePath();
  }
  function drawCloud(c) {
    const s = c.s;
    ctx.save();
    ctx.translate(c.x, c.y);
    ctx.fillStyle = C.cloudShade;
    ctx.beginPath(); ctx.ellipse(4, 10 * s, 52 * s, 13 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = C.cloud;
    [[-26, 4, 18], [-4, -6, 24], [22, 2, 19], [40, 8, 13], [-42, 9, 12]].forEach(([dx, dy, r]) => {
      ctx.beginPath(); ctx.arc(dx * s, dy * s, r * s, 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }
  function drawLandscape() {
    const g = H - 46;
    ctx.fillStyle = C.dune2;
    ctx.beginPath(); ctx.moveTo(0, g + 6);
    for (let x = 0; x <= W; x += 20) ctx.lineTo(x, g + 4 + Math.sin(x / 90) * 6);
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.fill();
    ctx.fillStyle = C.dune1;
    ctx.beginPath(); ctx.moveTo(0, g + 18);
    for (let x = 0; x <= W; x += 20) ctx.lineTo(x, g + 16 + Math.sin(x / 55 + 1) * 5);
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.fill();
    // a small river that widens as the reservoir fills
    const fill = Math.min(1, (game.caught % 25) / 25);
    ctx.strokeStyle = C.river; ctx.lineCap = "round"; ctx.lineWidth = 4 + fill * 6;
    ctx.beginPath(); ctx.moveTo(-10, H - 10);
    ctx.bezierCurveTo(W * 0.3, H - 30, W * 0.6, H - 4, W + 10, H - 22); ctx.stroke();
    // palms
    [[0.12, 1], [0.86, 0.85]].forEach(([fx, sc]) => {
      const x = W * fx, y = g + 14;
      ctx.strokeStyle = "#3b5446"; ctx.lineWidth = 3 * sc;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.quadraticCurveTo(x + 6 * sc, y - 22 * sc, x + 2 * sc, y - 40 * sc); ctx.stroke();
      ctx.fillStyle = "#4f7a5b";
      for (let k = 0; k < 5; k++) {
        const a = -Math.PI / 2 + (k - 2) * 0.55;
        ctx.beginPath(); ctx.ellipse(x + 2 * sc + Math.cos(a) * 12 * sc, y - 40 * sc + Math.sin(a) * 7 * sc, 13 * sc, 3.5 * sc, a, 0, Math.PI * 2); ctx.fill();
      }
    });
  }
  function drawPlayer() {
    const p = game.player;
    const g = H - 46;
    const r = p.w / 2.1;
    const cy = g - r * 0.4 - 4;
    const tilt = Math.max(-0.25, Math.min(0.25, p.vx / 2400));
    ctx.save();
    ctx.translate(p.x, cy); ctx.rotate(tilt);
    ctx.fillStyle = "rgba(0,0,0,.25)";
    ctx.beginPath(); ctx.ellipse(0, r * 1.38, r * 0.9, 4, 0, 0, Math.PI * 2); ctx.fill();
    const grad = ctx.createLinearGradient(0, -r * 1.8, 0, r * 1.4);
    grad.addColorStop(0, "#7fe3d6"); grad.addColorStop(1, C.player);
    ctx.fillStyle = grad;
    dropPath(0, 0, r); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.55)";
    ctx.beginPath(); ctx.ellipse(-r * 0.45, -r * 0.35, r * 0.16, r * 0.34, -0.4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = C.playerInk;
    ctx.beginPath(); ctx.arc(-r * 0.28, r * 0.25, r * 0.1, 0, Math.PI * 2); ctx.arc(r * 0.28, r * 0.25, r * 0.1, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = C.playerInk; ctx.lineWidth = 2; ctx.lineCap = "round";
    ctx.beginPath(); ctx.arc(0, r * 0.42, r * 0.22, 0.15 * Math.PI, 0.85 * Math.PI); ctx.stroke();
    ctx.restore();
  }
  function draw() {
    if (!W) return;
    const sky = ctx.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, C.skyTop); sky.addColorStop(1, C.skyBottom);
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(255,255,255,.05)";
    for (let i = 0; i < 18; i++) { const x = (i * 97 + game.t * 6) % W; ctx.fillRect(x, (i * 53) % (H * 0.5), 1.5, 1.5); }
    game.clouds.forEach(drawCloud);
    game.drops.forEach((d) => {
      ctx.fillStyle = d.gold ? C.gold : C.drop;
      dropPath(d.x, d.y, d.r); ctx.fill();
      ctx.fillStyle = d.gold ? "#fbe3b4" : C.dropHi;
      ctx.beginPath(); ctx.arc(d.x - d.r * 0.35, d.y - d.r * 0.1, d.r * 0.22, 0, Math.PI * 2); ctx.fill();
    });
    drawLandscape();
    game.splashes.forEach((s) => { ctx.globalAlpha = Math.max(0, s.life / 0.45); ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(s.x, s.y, 2.6, 0, Math.PI * 2); ctx.fill(); });
    ctx.globalAlpha = 1;
    drawPlayer();
  }

  let last = performance.now();
  function loop(now) {
    if (game.state !== "playing") return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    update(dt);
    draw();
    if (game.state === "playing") requestAnimationFrame(loop);
  }

  /* idle animation: clouds drift behind the start card, cheaply */
  function idle(now) {
    if (game.state !== "idle") return;
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    game.t += dt;
    game.clouds.forEach((c) => { c.x += c.v * dt * 0.5; if (c.x < 40 || c.x > W - 40) c.v *= -1; });
    draw();
    if (!reduceMotion) requestAnimationFrame(idle);
  }

  window.__rain = {
    get state() { return game.state; }, get score() { return game.score; }, get lives() { return game.lives; },
    forceGameOver() { if (game.state === "playing" || game.state === "paused") { game.lives = 0; gameOver(); } },
  };

  resize();
  hud();
  requestAnimationFrame(idle);
})();
