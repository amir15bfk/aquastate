/* Annual rainfall trajectory: a compact SVG, no chart library. */
(function () {
  "use strict";
  const host = document.getElementById("climate-chart");
  if (!host) return;
  let profile = null;
  try { profile = JSON.parse(document.getElementById("profile-data")?.textContent || "null"); } catch (e) { profile = null; }
  const series = (profile && profile.climate && profile.climate.annual_series) || [];
  if (!series.length) {
    host.innerHTML = '<p class="empty-light">No annual climate series cached.</p>';
    return;
  }
  const W = 720, H = 190, ml = 34, mr = 8, mt = 16, mb = 28;
  const plotW = W - ml - mr;
  const plotH = H - mt - mb;
  const values = series.map((row) => Number(row.precip_mm) || 0);
  const max = Math.max(1, ...values) * 1.12;
  const x = (i) => ml + (plotW * i) / Math.max(1, series.length - 1);
  const y = (v) => mt + plotH - (Math.max(0, v) / max) * plotH;
  const parts = [];
  [0, max / 2, max].forEach((tick) => {
    parts.push(`<line x1="${ml}" y1="${y(tick)}" x2="${W - mr}" y2="${y(tick)}" stroke="#eef1ef" stroke-width="1"/>`);
    parts.push(`<text x="${ml - 6}" y="${y(tick) + 3}" text-anchor="end" font-size="9" fill="#6f7a76" font-family="IBM Plex Mono">${Math.round(tick)}</text>`);
  });
  const barW = Math.max(4, plotW / series.length * 0.52);
  series.forEach((row, i) => {
    const value = Number(row.precip_mm) || 0;
    const height = mt + plotH - y(value);
    parts.push(`<rect x="${x(i) - barW / 2}" y="${y(value)}" width="${barW}" height="${height}" rx="2" fill="${i === series.length - 1 ? "#1b6c80" : "#9fc3c9"}"><title>${row.year}: ${Math.round(value)} mm</title></rect>`);
    if (i === 0 || i === series.length - 1 || i % 3 === 0) {
      parts.push(`<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="9" fill="#6f7a76" font-family="IBM Plex Mono">${row.year}</text>`);
    }
  });
  const line = series.map((row, i) => `${x(i)},${y(Number(row.precip_mm) || 0)}`).join(" ");
  parts.push(`<polyline points="${line}" fill="none" stroke="#0d4553" stroke-width="1" opacity=".55"/>`);
  const last = series[series.length - 1];
  parts.push(`<text x="${x(series.length - 1)}" y="${y(Number(last.precip_mm) || 0) - 7}" text-anchor="end" font-size="10" fill="#0d4553" font-family="IBM Plex Mono">${Math.round(Number(last.precip_mm) || 0)} mm</text>`);
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Annual rainfall from ${series[0].year} to ${last.year}">${parts.join("")}</svg>`;
})();
