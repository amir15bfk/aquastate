# AquaState — Index Mathematics

**Versions:** WCRI-2.0 (country), WRI-2.0 (water system), DRI-2.0 (dam deep index).
**Status:** implemented, deterministic, no AI in the index path.

Units: precipitation/ET `mm`, PET `mm/day`, storage `Mm³` in the country layer and `m³` in the dam layer, time `days`.

---

## 1. WCRI-2.0 — country index

0–100, higher is better. Six pillars:

| Pillar | Weight | Meaning |
|---|---:|---|
| Water availability | 0.22 | renewable freshwater per person + rainfall vs evaporative demand |
| Drought & soil | 0.20 | SPI-3, SPI-12, soil percentile, dry spell |
| Groundwater | 0.14 | root-zone percentile + trend; labelled proxy |
| Flood resilience | 0.14 | forecast discharge vs 60-day baseline + active events |
| Wildfire resilience | 0.14 | fire weather + drought coupling + active fires |
| Desertification resilience | 0.16 | aridity + rainfall/soil trends + forest change |

```
base = 0.22·W + 0.20·D + 0.14·G + 0.14·F + 0.14·R + 0.16·L

penalty = 0.12·max(0, 30 − min(pillars))
        + 0.05·max(0, 45 − D)·max(0, 45 − R)/45
        + 0.05·max(0, 45 − D)·max(0, 45 − L)/45

WCRI = clamp(base − penalty, 0, 100)
```

The first term is the bottleneck guard (max 3.6 points); the other two are the explicit drought–fire and drought–desertification cascade terms (max 2.25 each).

**Bands:** Resilient ≥70 · Stable 55–70 · Watch 40–55 · Stressed 25–40 · Critical <25.
**Coverage:** `Σ weight of pillars with confidence > 0.15`. Below 0.40 → `NO_DATA`.
**Confidence:** `Σ effective weight × pillar confidence`. Confidence never changes the score.
**Contribution:** `(weight / coverage) × (pillar − 50)`. Penalties are applied after the sum.

### Water availability

Per-capita score is log-scaled between the Falkenmark anchors:

```
per_capita = 100 × clamp((log10(max(1, pc)) − log10(500)) / (log10(10000) − log10(500)), 0, 1)
aridity    = annual_P / annual_PET
W          = 0.55 × per_capita + 0.45 × 100 × clamp(aridity / 0.65, 0, 1)
```

PET uses Hargreaves from NASA monthly Tmax/Tmin/Tmean with FAO-56 extraterrestrial radiation. If per-capita is missing, aridity alone; if both are missing, the pillar is unavailable.

### Drought & soil

```
D = 0.40 × SPI3 + 0.25 × SPI12 + 0.20 × soil percentile + 0.15 × dry-spell score
```

SPI is an **empirical mid-rank percentile** of the raw accumulation against the same calendar month in the prior baseline years. The current year is never in its own baseline. The dry-spell score is `100 × (1 − min(dry_days, 180)/120)` and is neutral 50 when the 92-day window is missing. `dry_days` counts days since rain > 2 mm.

### Groundwater (proxy)

```
G = 0.60 × soil percentile + 0.40 × trend score
```

The trend score uses Sen's slope and the Mann–Kendall p-value from the existing water-app statistics. This is a labelled proxy; GRACE is not ingested in the MVP.

### Flood

```
peak      = max(forecast river discharge, days 1–16)
q50, q95  = empirical quantiles of the prior 60 days
risk      = 100 × clamp((peak − q50) / max(0.01, q95 − q50), 0, 1)
FL        = 100 − [0.75 × risk + 0.25 × min(100, active_floods × 25)]
```

If the flood API is unavailable but events exist, event-only with low confidence. If neither, the pillar is unavailable.

### Wildfire

```
fire_weather = 0.35 × VPD percentile
             + 0.25 × dry-spell risk
             + 0.20 × (100 − soil percentile)
             + 0.20 × wind percentile
coupling     = 100 × clamp((50 − D)/50, 0, 1)
R            = 100 − [0.65 × fire_weather + 0.20 × coupling + 0.15 × min(100, active_fires × 25)]
```

VPD is computed from Tmax and RHmin (`es − ea`). This is fire weather, not an ignition forecast.

### Desertification

```
aridity_pressure = 100 × clamp((0.50 − AI)/0.50, 0, 1)
precip_pressure  = 100 × clamp(−slope_pct_per_year / 3, 0, 1)
soil_pressure    = 100 × clamp(−soil_slope_pct_per_year / 1, 0, 1)
land_pressure    = 100 × clamp(−forest_change_pct / 5, 0, 1)   # neutral 50 if missing
L = 100 − [0.40 × aridity + 0.30 × precip + 0.20 × soil + 0.10 × land]
```

Aridity uses the baseline mean annual P/PET. Trends use Sen's slope with the current year excluded.

### Sampling

The climate point is the **capacity-weighted centroid of monitored dams** where a country has one (e.g. Algeria/Tunisia), otherwise the gazetteer centroid. A country centroid can sit in a desert while the water system is in a wetter upland. This is a screening limitation, not a full national grid.

---

## 2. WRI-2.0 — water system

The original five pillars are preserved: storage buffer 0.34, soil 0.18, groundwater 0.14, forecast 0.14, trend 0.20. The aggregation is:

```
WRI = Σ wᵢ·Sᵢ − 0.15·max(0, 35 − min(Sᵢ))
```

Upgrades: mid-rank percentiles, SPI-3/SPI-12, confidence-weighted effective weights, the Φ buffer bridge, a continuous low-storage guard, source-freshness confidence and coverage.

The **score never jumps**: the current-state score is reported unchanged; the Smart Horizon verdict is a separate forward-looking output. The Φ bridge and the Smart Horizon can both say “OK until rain” without rewriting the arithmetic.

---

## 3. DRI-2.0 — dam deep index

The space app's signed HRI-1.0 mathematics is ported unchanged:

- SSI surface storage, CMI catchment meteorology, SRRI soil/runoff readiness, SAI subsurface (NO_DATA for pilot basins), EESI evaporative/ecological stress.
- Nominal weights: SSI 0.30, CMI 0.20, SRRI 0.15, SAI 0.20, EESI 0.15.
- Pilot effective weights after SAI exclusion: `[0.375, 0.25, 0.1875, 0.1875]`.
- `Φ = rain_gate · σ((D_autonomy − D_until_rain)/7) · σ(ln((V_in14 + ε_V)/(14·Q_out + ε_V))/0.5)`.
- `HRI = (1−Φ)·HRI_now + Φ·HRI_proj`, then the continuous low-storage guard.
- Waterfall contributions sum to `HRI − 50`.
- The signed fixtures are regression tests:
  - Case A dry: **24.9 CRITICAL**.
  - Case B storm: `HRI_now=38.616`, `HRI_proj=83.293`, `Φ=0.94977`, **81.05 RECHARGING**.
  - Case C3 low autonomy: **19.9**.

The spillway pressure diagnostic (forecast inflow vs spill headroom) is display-only and never enters the score.

---

## 4. Statistics

- `mid_rank_percentile`: `P = 100·(b + t/2 + 1)/(N + 2)`, with `b = count(< current)`, `t = count(== current)`.
- Sen's slope: median of pairwise slopes.
- Mann–Kendall: two-sided normal approximation with tie correction; n < 8 returns neutral/low confidence.
- Hargreaves PET: `0.0023 × 0.408 × Ra × (Tmean + 17.8) × √(Tmax − Tmin)`.
- Weights are normalized; zero total returns zeros, never a divide-by-zero.

---

## 5. Edge cases

| Case | Behaviour |
|---|---|
| No monthly climate | Drought/groundwater/desertification unavailable; coverage falls |
| No forecast | Fire weather unavailable; no fake dry signal |
| No flood API | Event-only or unavailable, never a hidden zero |
| No aquifer inventory | Labelled root-zone proxy |
| Coverage < 40% | `NO_DATA`, grey map |
| Country centroid in desert | Monitored-dam centroid used where available |
| Polar territory | Excluded from the map framing; still has a country profile |
| All-equal percentile baseline | Mid-rank 50 with reduced confidence |
| Dam with no deep data | Inventory card; no invented score |

---

## 6. Reproduce

```powershell
python manage.py bootstrap_world          # WCRI + world snapshot
python manage.py seed_demo --country DZ --country TN --force
python manage.py compute_indices --all    # DRI snapshots
python -m pytest -q core/tests dashboard/tests
```
