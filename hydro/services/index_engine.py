"""WRI-1.0: deterministic water-resilience index and Smart Horizon engine.

Every output carries its formula, substitution, inputs, source and confidence.
The AI layer is deliberately downstream of this module and cannot mutate the
core values.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone
from statistics import mean, median

from django.conf import settings
from django.utils import timezone

from hydro.models import ClimateDay, Country, ForecastDay, IndexSnapshot, Reservoir
from hydro.services import storage
from hydro.services.gazetteer import country_payload
from hydro.services.statistics import clamp, normalise_weights, percentile_rank, trend_summary

STATUS_BANDS = [
    ("ok", 60.0, "OK"),
    ("watch", 45.0, "Watch"),
    ("stressed", 30.0, "Stressed"),
    ("critical", 0.0, "Critical"),
]


@dataclass(frozen=True)
class Scenario:
    rain: str = "forecast"
    demand: float = 1.0
    horizon: int = 14

    @property
    def hypothetical(self) -> bool:
        return self.rain == "whatif"

    @property
    def label(self) -> str:
        return {
            "forecast": "Forecast",
            "dry": "Dry spell",
            "whatif": "Rain in 2 days (what-if)",
        }.get(self.rain, "Forecast")

    def as_dict(self) -> dict:
        return {
            "rain": self.rain,
            "demand_factor": round(self.demand, 2),
            "horizon_days": self.horizon,
            "hypothetical": self.hypothetical,
            "label": self.label,
        }


def make_scenario(rain: str = "forecast", demand: float | str = 1.0, horizon: int | str = 14) -> Scenario:
    rain = rain if rain in {"forecast", "dry", "whatif"} else "forecast"
    try:
        demand_float = float(demand)
    except (TypeError, ValueError):
        demand_float = 1.0
    demand_float = max(0.5, min(2.0, demand_float))
    try:
        horizon_int = int(horizon)
    except (TypeError, ValueError):
        horizon_int = 14
    horizon_int = max(7, min(30, horizon_int))
    return Scenario(rain=rain, demand=demand_float, horizon=horizon_int)


def status_for(score: float) -> tuple[str, str]:
    for key, threshold, label in STATUS_BANDS:
        if score >= threshold:
            return key, label
    return "critical", "Critical"


def confidence_label(value: float) -> str:
    if value >= 0.78:
        return "High"
    if value >= 0.58:
        return "Medium"
    return "Low"


def _r(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(value, digits)


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator is None or abs(denominator) < 1e-9:
        return default
    return numerator / denominator


def _mean(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    return mean(clean) if clean else None


def _window_mean(
    daily: dict[date, float],
    year: int,
    month: int,
    day: int,
    radius: int,
) -> float | None:
    anchor = date(year, month, min(day, 28))
    values = [daily.get(anchor + timedelta(days=offset)) for offset in range(-radius, radius + 1)]
    return _mean([v for v in values if v is not None])


def _climate_normal(
    climate: list[ClimateDay],
    field: str,
    today: date,
    radius: int = 14,
    years: int = 10,
) -> tuple[list[float], float | None]:
    daily = {
        row.date: getattr(row, field)
        for row in climate
        if getattr(row, field) is not None
    }
    history = []
    for year in range(today.year - years, today.year):
        value = _window_mean(daily, year, today.month, today.day, radius)
        if value is not None:
            history.append(value)
    current_window = [
        daily.get(today - timedelta(days=offset)) for offset in range(0, 7)
    ]
    current = _mean([v for v in current_window if v is not None])
    normal = median(history) if history else None
    return history, current if current is not None else normal


def _normal_14d(climate: list[ClimateDay], today: date) -> float:
    """Mean same-window 14-day rainfall total over the prior ten years."""
    daily = {row.date: row.precip_mm or 0.0 for row in climate}
    totals = []
    for year in range(today.year - 10, today.year):
        anchor = date(year, today.month, min(today.day, 28))
        total = sum(daily.get(anchor + timedelta(days=offset), 0.0) for offset in range(14))
        totals.append(total)
    if not totals:
        return 0.0
    return max(0.0, mean(totals))


def _forecast_rows(country: Country, reservoir: Reservoir, today: date) -> list[ForecastDay]:
    rows = list(
        ForecastDay.objects.filter(
            country=country, reservoir=reservoir, date__gte=today
        ).order_by("date")[:40]
    )
    if rows:
        return rows
    return list(
        ForecastDay.objects.filter(
            country=country, reservoir__isnull=True, date__gte=today
        ).order_by("date")[:40]
    )


def _rain_value(rows: list[ForecastDay], day: date, scenario: Scenario, day_index: int) -> float:
    base = 0.0
    for row in rows:
        if row.date == day:
            base = max(0.0, row.precip_mm or 0.0)
            break
    if scenario.rain == "dry":
        return 0.0
    if scenario.rain == "whatif":
        return base * 0.5 + (20.0 if day_index == 1 else 0.0)
    return base


def _et0_value(rows: list[ForecastDay], day: date, lat: float) -> float:
    for row in rows:
        if row.date == day and row.et0_mm is not None:
            return max(0.0, row.et0_mm)
    return storage._et0_estimate(day, lat)


def _demand_weights(reservoirs: list[Reservoir]) -> dict[int, float]:
    raw = {row.id: max(0.01, row.demand_mm3_day) for row in reservoirs}
    total = sum(raw.values())
    if total <= 0:
        return {row.id: 1.0 / len(reservoirs) for row in reservoirs} if reservoirs else {}
    return {key: value / total for key, value in raw.items()}


def _aggregate_history(country: Country) -> list[dict]:
    reservoirs = list(country.reservoirs.all())
    total_capacity = sum(max(0.0, row.capacity_mm3) for row in reservoirs)
    if total_capacity <= 0:
        return []
    by_year: dict[int, list[tuple[float, float]]] = {}
    for reservoir in reservoirs:
        for row in reservoir.storage_years.all():
            by_year.setdefault(row.year, []).append((row.end_storage_pct, reservoir.capacity_mm3))
    output = []
    for year in sorted(by_year):
        parts = by_year[year]
        capacity = sum(c for _, c in parts)
        if capacity <= 0:
            continue
        weighted = sum(pct * c for pct, c in parts) / capacity
        output.append({"year": year, "storage_pct": round(weighted, 2)})
    return output


def _build_pillar(
    *,
    key: str,
    label: str,
    value: float,
    weight: float,
    formula: str,
    substitution: str,
    inputs: list[dict],
    source: str,
    source_url: str,
    source_kind: str,
    confidence: float,
    interpretation: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "key": key,
        "label": label,
        "value": round(clamp(value), 2),
        "weight": round(weight, 4),
        "weight_pct": round(weight * 100, 1),
        "contribution": round(weight * clamp(value), 2),
        "formula": formula,
        "substitution": substitution,
        "inputs": inputs,
        "source": source,
        "source_url": source_url,
        "source_kind": source_kind,
        "confidence": round(clamp(confidence, 0.0, 1.0), 2),
        "interpretation": interpretation,
    }
    if extra:
        payload.update(extra)
    return payload


def horizon_simulation(
    country: Country,
    reservoirs: list[Reservoir],
    scenario: Scenario,
    today: date,
) -> dict:
    """Daily forward balance for 45 days; 16-day forecast, zero rain beyond it."""
    weights = _demand_weights(reservoirs)
    rows_by_res = {row.id: _forecast_rows(country, row, today) for row in reservoirs}
    et0_by_res = {
        row.id: [_et0_value(rows_by_res[row.id], today + timedelta(days=i), row.lat) for i in range(45)]
        for row in reservoirs
    }
    rain_by_res = {
        row.id: [_rain_value(rows_by_res[row.id], today + timedelta(days=i), scenario, i) for i in range(45)]
        for row in reservoirs
    }

    storage_state = {row.id: max(0.0, row.storage_mm3) for row in reservoirs}
    min_by_res = {row.id: 1.0 for row in reservoirs}
    min_by_res_horizon = {row.id: 1.0 for row in reservoirs}
    daily_res_ratios: dict[int, list[float]] = {row.id: [] for row in reservoirs}
    runway = []
    daily_ratios: list[float] = []
    weighted_rain: list[float] = []
    response_mm3_per_mm = sum((row.capacity_mm3 / 300.0) * 0.60 for row in reservoirs)
    daily_demand_total = sum(max(0.0, row.demand_mm3_day) * scenario.demand for row in reservoirs)
    # The relief event is scaled to the deficit: about five days of demand
    # delivered by the national rainfall-runoff response, bounded for sanity.
    relief_threshold_mm = clamp(
        5.0 * daily_demand_total / max(0.01, response_mm3_per_mm), 5.0, 25.0
    )

    # Runoff lags rainfall by two days: gain(t) uses rain(t-2).
    lag_days = 2
    for day_index in range(45):
        day = today + timedelta(days=day_index)
        day_rain = 0.0
        total_usable = 0.0
        total_live = 0.0
        for reservoir in reservoirs:
            capacity = max(0.001, reservoir.capacity_mm3)
            dead = max(0.0, reservoir.dead_storage_mm3)
            live_capacity = max(0.001, capacity - dead)
            rain_today = rain_by_res[reservoir.id][day_index]
            rain_to_runoff = rain_by_res[reservoir.id][max(0, day_index - lag_days)]
            et0 = et0_by_res[reservoir.id][day_index]
            # C/300 has units Mm3/mm (300 mm characteristic depth);
            # 0.60 is the screening runoff coefficient.
            gain = rain_to_runoff * (capacity / 300.0) * 0.60
            inflow = max(0.0, reservoir.inflow_mm3_day) + gain
            evaporation = et0 * max(0.0, reservoir.surface_area_km2) * 0.001 * 0.70
            demand = max(0.0, reservoir.demand_mm3_day) * scenario.demand
            current = storage_state[reservoir.id]
            current = max(0.0, min(capacity, current + inflow - demand - evaporation))
            storage_state[reservoir.id] = current
            usable = max(0.0, current - dead)
            ratio = usable / live_capacity
            min_by_res[reservoir.id] = min(min_by_res[reservoir.id], ratio)
            if day_index < scenario.horizon:
                min_by_res_horizon[reservoir.id] = min(min_by_res_horizon[reservoir.id], ratio)
            daily_res_ratios[reservoir.id].append(ratio)
            total_usable += usable
            total_live += live_capacity
            day_rain += rain_today * weights.get(reservoir.id, 0.0)
        aggregate = _safe_div(total_usable, total_live, 0.0)
        daily_ratios.append(aggregate)
        weighted_rain.append(day_rain)
        if day_index < 30:
            runway.append(
                {
                    "date": day.isoformat(),
                    "storage_pct": round(aggregate * 100, 2),
                    "rain_mm": round(day_rain, 2),
                    "threshold_pct": round(settings.HORIZON_EMERGENCY_RATIO * 100, 1),
                }
            )

    # National relief event: demand-weighted 3-day rain over the scaled
    # threshold, only inside the 16-day forecast window.
    relief_event_index = None
    for index in range(0, 14):
        three_day = sum(weighted_rain[index : index + 3])
        if three_day >= relief_threshold_mm:
            relief_event_index = index
            break
    relief_day = relief_event_index + 1 + lag_days if relief_event_index is not None else None
    rain_amount = (
        sum(weighted_rain[relief_event_index : relief_event_index + 3])
        if relief_event_index is not None
        else 0.0
    )

    major = [row for row in reservoirs if weights.get(row.id, 0) >= 0.10]
    check_ids = [row.id for row in major] or [row.id for row in reservoirs]
    covered_to_relief = False
    if relief_day is not None:
        covered_to_relief = True
        for day_index in range(0, min(relief_day + 1, 45)):
            if daily_ratios[day_index] < settings.HORIZON_EMERGENCY_RATIO:
                covered_to_relief = False
                break
            for reservoir in reservoirs:
                if reservoir.id in check_ids:
                    if daily_res_ratios[reservoir.id][day_index] < settings.HORIZON_PER_RESERVOIR_MIN_RATIO:
                        covered_to_relief = False
                        break
            if not covered_to_relief:
                break

    post_relief_ok = False
    post_balance = 0.0
    post_ratio = None
    ratio_at_relief = None
    refill_gain = 0.0
    refill_needed = 0.0
    total_live_capacity = sum(max(0.0, row.capacity_mm3 - row.dead_storage_mm3) for row in reservoirs)
    if relief_day is not None and relief_day < 45:
        start = min(relief_day, 44)
        initial_ratio = daily_ratios[start]
        ratio_at_relief = initial_ratio
        balance = 0.0
        for day_index in range(start, min(start + 14, 45)):
            for reservoir in reservoirs:
                capacity = max(0.001, reservoir.capacity_mm3)
                rain_to_runoff = rain_by_res[reservoir.id][max(0, day_index - lag_days)]
                et0 = et0_by_res[reservoir.id][day_index]
                gain = rain_to_runoff * (capacity / 300.0) * 0.60
                evaporation = et0 * max(0.0, reservoir.surface_area_km2) * 0.001 * 0.70
                demand = max(0.0, reservoir.demand_mm3_day) * scenario.demand
                balance += gain - demand - evaporation
        post_balance = balance
        post_ratio = daily_ratios[min(start + 13, 44)]
        if relief_event_index is not None:
            for day_index in range(relief_event_index, min(relief_event_index + 7, 45)):
                for reservoir in reservoirs:
                    capacity = max(0.001, reservoir.capacity_mm3)
                    refill_gain += rain_by_res[reservoir.id][day_index] * (capacity / 300.0) * 0.60
        # "Enough refill" means the event extends the runway by at least two
        # days of national demand (and 2% of live capacity), while the reserve
        # at the refill is above the emergency threshold. The verdict is
        # "OK until rain", not a promise of long-term sustainability.
        refill_needed = max(
            2.0 * max(0.05, daily_demand_total),
            0.02 * max(0.001, total_live_capacity),
        )
        post_relief_ok = (
            ratio_at_relief >= settings.HORIZON_EMERGENCY_RATIO
            and refill_gain >= refill_needed
        )

    aggregate_cover_days = _aggregate_cover_days(reservoirs, scenario)
    min_projected_ratio = min(daily_ratios[:30]) if daily_ratios else 0.0
    final_ratio = daily_ratios[min(scenario.horizon - 1, len(daily_ratios) - 1)] if daily_ratios else 0.0

    # Exhaustive, ordered classification. The verdict is separate from the
    # current-state score; a secured horizon does not rewrite the arithmetic.
    if relief_day is not None and relief_day <= scenario.horizon and covered_to_relief and post_relief_ok:
        state = "secured"
        verdict = "OK until rain"
    elif relief_day is None:
        if aggregate_cover_days >= scenario.horizon * 2 and min_projected_ratio >= settings.HORIZON_EMERGENCY_RATIO:
            state = "buffered"
            verdict = "OK, buffered"
        else:
            state = "exposed"
            verdict = "Exposed, no rain in forecast"
    elif relief_day <= scenario.horizon:
        state = "tight"
        verdict = "Tight before rain"
    elif aggregate_cover_days >= scenario.horizon and min_projected_ratio >= settings.HORIZON_EMERGENCY_RATIO:
        state = "buffered"
        verdict = "OK to horizon, rain later"
    else:
        state = "exposed"
        verdict = "Exposed before rain"

    reservoir_horizons = []
    for reservoir in reservoirs:
        rain_series = rain_by_res[reservoir.id]
        local_response = (max(0.001, reservoir.capacity_mm3) / 300.0) * 0.60
        local_demand = max(0.0, reservoir.demand_mm3_day) * scenario.demand
        local_threshold = clamp(5.0 * local_demand / max(0.01, local_response), 5.0, 30.0)
        local_relief = None
        for index in range(0, 14):
            if sum(rain_series[index : index + 3]) >= local_threshold:
                local_relief = index + 1 + lag_days
                break
        local_ratio = max(0.0, reservoir.storage_mm3 - reservoir.dead_storage_mm3) / max(
            0.001, reservoir.capacity_mm3
        )
        local_cover = _cover_days(reservoir, scenario)
        reservoir_horizons.append(
            {
                "id": reservoir.id,
                "name": reservoir.name,
                "cover_days": round(local_cover, 1),
                "days_to_rain": local_relief,
                "usable_ratio": round(local_ratio, 3),
                "min_projected_ratio": round(min_by_res_horizon[reservoir.id], 3),
                "major": reservoir.id in check_ids,
                "local_relief_threshold_mm": round(local_threshold, 1),
                "status": (
                    "covered"
                    if local_relief is not None and local_relief <= scenario.horizon
                    else "buffered"
                    if local_cover >= scenario.horizon * 2
                    else "exposed"
                ),
            }
        )
    alerts = [
        {
            "level": "warning",
            "message": f"{row['name']} is below the local emergency reserve before the national rain event.",
        }
        for row in reservoir_horizons
        if row["major"] and row["min_projected_ratio"] < settings.HORIZON_PER_RESERVOIR_MIN_RATIO
    ]

    return {
        "state": state,
        "verdict": verdict,
        "headline": verdict,
        "days_to_rain": relief_day,
        "rain_amount_mm": round(rain_amount, 1),
        "relief_threshold_mm": round(relief_threshold_mm, 1),
        "rain_event_window": {
            "start": (today + timedelta(days=relief_event_index)).isoformat()
            if relief_event_index is not None
            else None,
            "lag_days": lag_days,
        },
        "cover_days": round(aggregate_cover_days, 1),
        "min_projected_ratio": round(min_projected_ratio * 100, 1),
        "projected_storage_pct": round(final_ratio * 100, 1),
        "emergency_ratio_pct": round(settings.HORIZON_EMERGENCY_RATIO * 100, 1),
        "post_relief_ok": post_relief_ok,
        "post_relief_ratio_pct": round(post_ratio * 100, 1) if post_ratio is not None else None,
        "ratio_at_relief_pct": round(ratio_at_relief * 100, 1) if ratio_at_relief is not None else None,
        "post_relief_net_balance_mm3": round(post_balance, 2),
        "refill_gain_mm3": round(refill_gain, 1),
        "refill_needed_mm3": round(refill_needed, 1),
        "reserve_days": round(
            settings.HORIZON_EMERGENCY_RATIO * total_live_capacity / max(0.05, daily_demand_total), 1
        ),
        "covered_to_relief": covered_to_relief,
        "runway": runway,
        "reservoirs": reservoir_horizons,
        "alerts": alerts,
        "simulation_note": (
            "45-day daily balance. Forecast rain is used for days 0-15; zero rain "
            "is assumed after day 16. The runoff lag is 2 days. Screening response = "
            "rain × (capacity/300) × 0.60, where capacity/300 is Mm³ per mm."
        ),
    }


def _cover_days(reservoir: Reservoir, scenario: Scenario) -> float:
    usable = max(0.0, reservoir.storage_mm3 - reservoir.dead_storage_mm3)
    evap = 0.0
    if reservoir.surface_area_km2:
        et0 = storage._et0_estimate(date.today(), reservoir.lat)
        evap = et0 * reservoir.surface_area_km2 * 0.001 * 0.70
    burn = max(0.05, reservoir.demand_mm3_day * scenario.demand + evap - reservoir.inflow_mm3_day)
    return usable / burn


def _aggregate_cover_days(reservoirs: list[Reservoir], scenario: Scenario) -> float:
    usable = sum(max(0.0, row.storage_mm3 - row.dead_storage_mm3) for row in reservoirs)
    burn = 0.0
    for row in reservoirs:
        et0 = storage._et0_estimate(date.today(), row.lat) if row.surface_area_km2 else 0.0
        evaporation = et0 * row.surface_area_km2 * 0.001 * 0.70
        burn += max(0.05, row.demand_mm3_day * scenario.demand + evaporation - row.inflow_mm3_day)
    return _safe_div(usable, max(0.05, burn), 0.0)


def compute_index(
    country: Country,
    scenario: Scenario | None = None,
    *,
    as_of: date | None = None,
    persist: bool = False,
) -> dict:
    scenario = scenario or Scenario()
    today = as_of or date.today()
    reservoirs = list(country.reservoirs.all())
    if not reservoirs:
        return empty_result(country, scenario, today)
    centroid = (country.profile or {}).get("hydrologic_centroid") or {
        "lat": country.lat,
        "lon": country.lon,
    }
    climate = list(
        country.climate_days.filter(date__lte=today).order_by("-date")[:3800]
    )
    climate.reverse()
    aquifers = list(country.aquifers.all())
    weights = normalise_weights(settings.INDEX_WEIGHTS)

    # ------------------------------------------------------------------
    # B — storage buffer
    # ------------------------------------------------------------------
    buffer_scores = []
    buffer_weights = []
    total_usable = 0.0
    total_burn = 0.0
    reservoir_payload = []
    for reservoir in reservoirs:
        cover = _cover_days(reservoir, scenario)
        score = 100.0 * min(1.0, max(0.0, cover) / 90.0) ** 0.85
        weight = max(0.01, reservoir.demand_mm3_day)
        buffer_scores.append(score)
        buffer_weights.append(weight)
        usable = max(0.0, reservoir.storage_mm3 - reservoir.dead_storage_mm3)
        et0 = storage._et0_estimate(today, reservoir.lat) if reservoir.surface_area_km2 else 0.0
        evaporation = et0 * reservoir.surface_area_km2 * 0.001 * 0.70
        net_burn = max(
            0.05,
            reservoir.demand_mm3_day * scenario.demand + evaporation - reservoir.inflow_mm3_day,
        )
        total_usable += usable
        total_burn += net_burn
        storage_pct = reservoir.storage_pct
        reservoir_payload.append(
            {
                "id": reservoir.id,
                "name": reservoir.name,
                "lat": reservoir.lat,
                "lon": reservoir.lon,
                "capacity_mm3": round(reservoir.capacity_mm3, 1),
                "storage_mm3": round(reservoir.storage_mm3, 1),
                "dead_storage_mm3": round(reservoir.dead_storage_mm3, 1),
                "storage_pct": round(storage_pct, 1),
                "usable_mm3": round(usable, 1),
                "cover_days": round(cover, 1),
                "demand_mm3_day": round(reservoir.demand_mm3_day, 3),
                "evaporation_mm3_day": round(evaporation, 3),
                "inflow_mm3_day": round(reservoir.inflow_mm3_day, 3),
                "net_burn_mm3_day": round(net_burn, 3),
                "buffer_score": round(score, 1),
                "status": status_for(score)[0],
                "status_label": status_for(score)[1],
                "is_reference_pool": reservoir.is_reference_pool,
                "storage_source": reservoir.storage_source,
                "source_name": reservoir.source_name,
                "source_url": reservoir.source_url,
            }
        )
    buffer_weight_total = sum(buffer_weights)
    buffer_value = (
        sum(score * weight for score, weight in zip(buffer_scores, buffer_weights)) / buffer_weight_total
        if buffer_weight_total
        else 0.0
    )
    cover_days = _safe_div(total_usable, max(0.05, total_burn), 0.0)
    buffer_pillar = _build_pillar(
        key="buffer",
        label="Storage buffer",
        value=buffer_value,
        weight=weights["buffer"],
        formula="B = 100 × [Σ dᵢ × min(1, cover_daysᵢ / 90)^0.85] / Σ dᵢ",
        substitution=(
            f"Σ dᵢ = {buffer_weight_total:.2f} Mm³/day; demand-weighted buffer = {buffer_value:.1f}; "
            f"aggregate runway = {cover_days:.1f} days"
        ),
        inputs=[
            {"label": "Usable stored water", "value": round(total_usable, 1), "unit": "Mm³"},
            {"label": "Aggregate net burn", "value": round(total_burn, 3), "unit": "Mm³/day"},
            {"label": "Aggregate runway", "value": round(cover_days, 1), "unit": "days"},
            {"label": "Target runway", "value": 90, "unit": "days"},
        ],
        source="Public dam inventory + mass-balance reconstruction",
        source_url="/sources/",
        source_kind="reference/modeled",
        confidence=0.72 if any(not row.is_reference_pool for row in reservoirs) else 0.45,
        interpretation=(
            "How long the usable stored water can serve the allocated demand at the current net burn. "
            "The score reaches 100 at a 90-day runway."
        ),
    )

    # ------------------------------------------------------------------
    # M — soil moisture
    # ------------------------------------------------------------------
    soil_history, soil_current = _climate_normal(climate, "soil_surface", today)
    if soil_current is None:
        soil_history, soil_current = _climate_normal(climate, "soil_root", today)
    if soil_current is None:
        soil_percentile = 50.0
        soil_normal = None
        soil_anomaly = 0.0
        soil_score = 50.0
        soil_conf = 0.3
        soil_kind = "unavailable"
    else:
        soil_percentile = percentile_rank(soil_history, soil_current) or 50.0
        soil_normal = median(soil_history) if soil_history else soil_current
        anomaly_denominator = max(0.05, 0.25 * (soil_normal or 0.05))
        soil_anomaly = (soil_current - (soil_normal or soil_current)) / anomaly_denominator
        anomaly_score = 50.0 + 50.0 * math.tanh(soil_anomaly)
        soil_score = clamp(0.7 * soil_percentile + 0.3 * anomaly_score, 0.0, 100.0)
        soil_conf = 0.9 if len(soil_history) >= 8 else 0.62
        soil_kind = "NASA POWER GWETTOP" if climate and climate[-1].source.startswith("NASA") else "fallback"
    soil_pillar = _build_pillar(
        key="soil",
        label="Soil moisture",
        value=soil_score,
        weight=weights["soil"],
        formula="M = 0.7 × percentile(GWETTOP) + 0.3 × [50 + 50 × tanh((current − normal)/max(0.05, 0.25 × normal))]",
        substitution=(
            f"current = {soil_current:.3f}; normal = {soil_normal:.3f}; "
            f"percentile = {soil_percentile:.0f}; anomaly = {soil_anomaly:+.2f}σ"
            if soil_current is not None and soil_normal is not None
            else "insufficient soil-moisture history"
        ),
        inputs=[
            {"label": "7-day surface wetness", "value": _r(soil_current, 3), "unit": "fraction"},
            {"label": "Same-window normal", "value": _r(soil_normal, 3), "unit": "fraction"},
            {"label": "Percentile rank", "value": round(soil_percentile), "unit": "%"},
            {"label": "Normalised anomaly", "value": _r(soil_anomaly, 2), "unit": "σ"},
        ],
        source="NASA POWER / MERRA-2 surface soil wetness (GWETTOP)",
        source_url="https://power.larc.nasa.gov/",
        source_kind=soil_kind,
        confidence=soil_conf,
        interpretation=(
            "Surface soil wetness compared with the same calendar window in the prior ten years. "
            "It is an antecedent-condition signal, not a reservoir level."
        ),
        extra={
            "history": [{"date": row.date.isoformat(), "value": _r(row.soil_surface, 3)} for row in climate[-120:] if row.soil_surface is not None],
            "percentile": round(soil_percentile, 1),
        },
    )

    # ------------------------------------------------------------------
    # G — groundwater
    # ------------------------------------------------------------------
    if aquifers:
        total_volume = sum(max(0.1, row.volume_km3) for row in aquifers)
        groundwater_score = 0.0
        aquifer_payload = []
        for aquifer in aquifers:
            if aquifer.recharge_mm3_day <= 0:
                ratio = 0.0 if aquifer.extraction_mm3_day <= 0 else 999.0
                abstraction = 50.0 if aquifer.extraction_mm3_day <= 0 else 0.0
            else:
                ratio = _safe_div(aquifer.extraction_mm3_day, aquifer.recharge_mm3_day, 999.0)
                abstraction = 100.0 * clamp((1.25 - ratio) / 0.75, 0.0, 1.0)
            trend_score = 100.0 * clamp(0.5 + aquifer.trend_m_per_year / 3.0, 0.0, 1.0)
            score = 0.55 * abstraction + 0.45 * trend_score
            volume_weight = max(0.1, aquifer.volume_km3) / total_volume
            groundwater_score += score * volume_weight
            aquifer_status, aquifer_status_label = status_for(score)
            aquifer_payload.append(
                {
                    "id": aquifer.id,
                    "name": aquifer.name,
                    "lat": aquifer.lat,
                    "lon": aquifer.lon,
                    "volume_km3": round(aquifer.volume_km3, 1),
                    "recharge_mm3_day": round(aquifer.recharge_mm3_day, 2),
                    "extraction_mm3_day": round(aquifer.extraction_mm3_day, 2),
                    "stress_ratio": _r(ratio, 2) if ratio < 100 else 99.0,
                    "abstraction_score": round(abstraction, 1),
                    "trend_m_per_year": round(aquifer.trend_m_per_year, 2),
                    "trend_score": round(trend_score, 1),
                    "score": round(score, 1),
                    "status": aquifer_status,
                    "status_label": aquifer_status_label,
                    "is_fossil": aquifer.is_fossil,
                    "shared_with": aquifer.shared_with,
                    "source_name": aquifer.source_name,
                    "source_url": aquifer.source_url,
                }
            )
        groundwater_kind = "reference"
        groundwater_conf = 0.68
        groundwater_source = "SASS / national aquifer reports (screening)"
        groundwater_formula = "G = Σ volume_share × [0.55 × clamp((1.25 − extraction/recharge)/0.75) + 0.45 × clamp(0.5 + trend/3)]"
        groundwater_sub = (
            f"{len(aquifers)} aquifer systems; fossil systems flagged; "
            f"volume-weighted score {groundwater_score:.1f}"
        )
    else:
        root_history, root_current = _climate_normal(climate, "soil_root", today)
        root_pct = percentile_rank(root_history, root_current) if root_current is not None else None
        annual = []
        daily_root = {row.date: row.soil_root for row in climate if row.soil_root is not None}
        for year in sorted({row.date.year for row in climate if row.soil_root is not None}):
            values = [value for day, value in daily_root.items() if day.year == year]
            if values:
                annual.append((year, mean(values)))
        root_trend = trend_summary(annual, divisor=1.0) if len(annual) >= 3 else None
        proxy_pct = root_pct if root_pct is not None else 50.0
        proxy_trend = root_trend["score"] if root_trend else 50.0
        groundwater_score = 0.6 * proxy_pct + 0.4 * proxy_trend
        groundwater_kind = "proxy"
        groundwater_conf = 0.42
        groundwater_source = "NASA POWER root-zone wetness proxy (no aquifer inventory)"
        groundwater_formula = "G = 0.6 × percentile(GWETROOT) + 0.4 × trend_score(Sen / Mann–Kendall)"
        groundwater_sub = (
            f"root-zone percentile {proxy_pct:.0f}; trend score {proxy_trend:.0f}; "
            "no measured aquifer record loaded"
        )
        aquifer_payload = []
    groundwater_pillar = _build_pillar(
        key="groundwater",
        label="Underground reserve",
        value=groundwater_score,
        weight=weights["groundwater"],
        formula=groundwater_formula,
        substitution=groundwater_sub,
        inputs=[
            {"label": "Aquifer systems", "value": len(aquifers) or "–", "unit": "count"},
            {"label": "Primary data", "value": "Aquifer report" if aquifers else "Root-zone proxy", "unit": ""},
        ],
        source=groundwater_source,
        source_url="/sources/",
        source_kind=groundwater_kind,
        confidence=groundwater_conf,
        interpretation=(
            "Abstraction pressure and water-table direction for mapped aquifers. "
            "Fossil systems are not renewable on management timescales."
        ),
        extra={"aquifers": aquifer_payload},
    )

    # ------------------------------------------------------------------
    # F — forecast opportunity
    # ------------------------------------------------------------------
    demand_weights = _demand_weights(reservoirs)
    forecast_rows_by_res = {row.id: _forecast_rows(country, row, today) for row in reservoirs}
    has_forecast = any(bool(rows) for rows in forecast_rows_by_res.values())
    weighted_14 = 0.0
    if has_forecast:
        for reservoir in reservoirs:
            rows = forecast_rows_by_res[reservoir.id]
            total = 0.0
            for index in range(14):
                day = today + timedelta(days=index)
                total += _rain_value(rows, day, scenario, index)
            weighted_14 += total * demand_weights.get(reservoir.id, 0.0)
    normal_14 = _normal_14d(climate, today)
    if has_forecast:
        forecast_ratio = _safe_div(weighted_14, max(1.0, normal_14), 0.0)
        forecast_score = 100.0 * min(1.0, forecast_ratio / 1.25)
        forecast_source = "Open-Meteo 16-day forecast + NASA POWER 10-year normal"
        forecast_substitution = (
            f"P14 = {weighted_14:.1f} mm; normal 14-day rain = {normal_14:.1f} mm; "
            f"ratio = {forecast_ratio:.2f}"
        )
        forecast_confidence = 0.9 if any(
            any(row.source.startswith("Open-Meteo") for row in rows)
            for rows in forecast_rows_by_res.values()
        ) else 0.35
        forecast_kind = "live forecast" if forecast_confidence >= 0.8 else "fallback"
    else:
        forecast_ratio = 0.0
        forecast_score = 50.0
        forecast_source = "No forecast rows available"
        forecast_substitution = "No forecast rows; neutral score with low confidence, not a dry forecast."
        forecast_confidence = 0.20
        forecast_kind = "unavailable"
    forecast_pillar = _build_pillar(
        key="forecast",
        label="Forecast opportunity",
        value=forecast_score,
        weight=weights["forecast"],
        formula="F = 100 × min(1, (P14 / max(1, Pnormal14)) / 1.25)",
        substitution=forecast_substitution,
        inputs=[
            {"label": "14-day forecast rain", "value": round(weighted_14, 1), "unit": "mm"},
            {"label": "10-year same-window normal", "value": round(normal_14, 1), "unit": "mm"},
            {"label": "Rain scenario", "value": scenario.label, "unit": ""},
        ],
        source=forecast_source,
        source_url="https://open-meteo.com/",
        source_kind=forecast_kind,
        confidence=forecast_confidence,
        interpretation=(
            "Near-term rainfall opportunity relative to the ten-year normal for the same fortnight. "
            "It is an opportunity signal, not a guarantee. Missing data is neutral, not dry."
        ),
    )

    for row in reservoir_payload:
        rows = forecast_rows_by_res.get(row["id"], [])
        row["rain_3d_mm"] = round(
            sum(_rain_value(rows, today + timedelta(days=index), scenario, index) for index in range(3)),
            1,
        )
        row["rain_16d_mm"] = round(
            sum(_rain_value(rows, today + timedelta(days=index), scenario, index) for index in range(16)),
            1,
        )

    # ------------------------------------------------------------------
    # T — trend resilience
    # ------------------------------------------------------------------
    history = _aggregate_history(country)
    points = [(row["year"], row["storage_pct"]) for row in history]
    if len(points) >= 8:
        trend = trend_summary(points, divisor=100.0)
    else:
        trend = {
            "slope_per_year": None,
            "slope_pct_per_year": None,
            "p": None,
            "significant": False,
            "score": 50.0,
            "confidence": 0.3,
            "n": len(points),
            "mk": {},
        }
    trend_pillar = _build_pillar(
        key="trend",
        label="Storage trend",
        value=trend["score"],
        weight=weights["trend"],
        formula="T = 50 + (100 × clamp(0.5 + β/4, 0, 1) − 50) × (1 − p)",
        substitution=(
            f"Sen β = {trend['slope_pct_per_year']:+.2f}% capacity/year; "
            f"Mann–Kendall p = {trend['p'] if trend['p'] is not None else '–'}; n = {trend['n']}"
        ),
        inputs=[
            {"label": "Sen slope", "value": _r(trend["slope_pct_per_year"], 2), "unit": "% cap/yr"},
            {"label": "Mann–Kendall p", "value": trend["p"], "unit": ""},
            {"label": "Annual observations", "value": trend["n"], "unit": "years"},
        ],
        source="Mass-balance storage history; Sen's slope + Mann–Kendall",
        source_url="/methodology/",
        source_kind="modeled",
        confidence=trend["confidence"],
        interpretation=(
            "The direction of the ten-year storage trajectory, shrunk toward neutral when the "
            "Mann–Kendall test is not significant. Positive slope means recovery."
        ),
        extra={
            "history": history,
            "slope": {
                "per_year": trend["slope_per_year"],
                "pct_per_year": trend["slope_pct_per_year"],
                "p_value": trend["p"],
                "significant": trend["significant"],
                "n": trend["n"],
            },
        },
    )

    pillars = [buffer_pillar, soil_pillar, groundwater_pillar, forecast_pillar, trend_pillar]
    weighted_sum = sum(row["weight"] * row["value"] for row in pillars)
    minimum = min(row["value"] for row in pillars)
    penalty = 0.15 * max(0.0, 35.0 - minimum)
    base_index = clamp(weighted_sum - penalty, 0.0, 100.0)
    horizon = horizon_simulation(country, reservoirs, scenario, today)

    status, status_label = status_for(base_index)
    # The score is the current-state score and is never rewritten by the
    # horizon gate. The verdict is a separate, explicitly forward-looking
    # output. This keeps the arithmetic monotone and auditable while letting
    # the product say "OK until rain" when coverage is secured.
    outlook_ok = horizon["state"] in {"secured", "buffered"}
    headline_status = "ok" if outlook_ok else status
    headline_label = horizon["verdict"]
    horizon_gate = {
        "applied": False,
        "score_unchanged": True,
        "secured": horizon["state"] == "secured",
        "base_index": round(base_index, 1),
        "headline_status": headline_status,
        "headline_label": headline_label,
        "provisional": scenario.hypothetical,
        "reason": (
            "A forecast-backed refill covers the remaining gap before the emergency reserve is reached; "
            "the score is reported at its current/scenario value and is not rewritten by the horizon gate."
            if horizon["state"] == "secured"
            else "The score is reported at its current/scenario value; the horizon verdict is reported separately."
        ),
    }

    confidence = sum(row["weight"] * row["confidence"] for row in pillars)
    confidence = clamp(confidence, 0.0, 1.0)
    data_quality = {
        "confidence": round(confidence, 2),
        "label": confidence_label(confidence),
        "mode": country.data_mode,
        "fallback": any(
            (row["source_kind"] or "") in {"fallback", "unavailable"} for row in pillars
        ),
        "proxy": any((row["source_kind"] or "") == "proxy" for row in pillars),
        "notes": [],
    }
    if scenario.hypothetical:
        data_quality["notes"].append("What-if rainfall is simulated, not a forecast.")
    if any(row.is_reference_pool for row in reservoirs):
        data_quality["notes"].append("Reservoir inventory is a national reference pool, not a dam list.")
    if any(row.storage_source in {"blended", "modeled"} for row in reservoirs):
        data_quality["notes"].append("Current reservoir storage is modeled/blended, not telemetry.")
    if data_quality["proxy"]:
        data_quality["notes"].append(
            "Groundwater uses a labelled root-zone proxy; no aquifer inventory is loaded for this country."
        )

    bottleneck = min(pillars, key=lambda row: row["value"])
    narrative = _narrative(country, scenario, horizon, status_label, base_index, headline_label, bottleneck)
    result = {
        "meta": {
            "product": "AquaState",
            "index": "Water Resilience Index",
            "version": settings.INDEX_VERSION,
            "generated_at": timezone.now().isoformat(),
            "as_of": today.isoformat(),
            "mode": "deterministic-mathematics",
            "ai_enabled": bool(settings.AI_AGENTS_ENABLED),
        },
        "country": country_payload(country),
        "hydrologic_centroid": centroid,
        "scenario": scenario.as_dict(),
        "index": {
            "value": round(base_index, 1),
            "base_value": round(base_index, 1),
            "status": status,
            "status_label": status_label,
            "headline_status": headline_status,
            "headline_label": headline_label,
            "band": _band_payload(base_index),
            "horizon_gate": horizon_gate,
            "confidence": round(confidence, 2),
            "confidence_label": confidence_label(confidence),
            "weights": {row["key"]: row["weight"] for row in pillars},
            "weighted_sum": round(weighted_sum, 2),
            "bottleneck_penalty": round(penalty, 2),
            "bottleneck": {
                "key": bottleneck["key"],
                "label": bottleneck["label"],
                "value": bottleneck["value"],
            },
            "aggregation_formula": "WRI = Σ wᵢ·Sᵢ − 0.15 × max(0, 35 − min(Sᵢ)). The score is the current-state score; the horizon verdict is reported separately and never rewrites it.",
            "bands": [{"key": key, "min": threshold, "label": label} for key, threshold, label in STATUS_BANDS],
        },
        "pillars": pillars,
        "horizon": horizon,
        "narrative": narrative,
        "reservoirs": reservoir_payload,
        "aquifers": aquifer_payload,
        "soil": {
            "current": _r(soil_current, 3),
            "normal": _r(soil_normal, 3),
            "percentile": round(soil_percentile, 1) if soil_percentile is not None else None,
            "date": today.isoformat(),
            "source": "NASA POWER / MERRA-2 GWETTOP" if soil_kind.startswith("NASA") else "Fallback soil estimate",
        },
        "series": {
            "storage_history": history,
            "soil_history": soil_pillar.get("history", []),
            "forecast": _forecast_series(forecast_rows_by_res, reservoirs, demand_weights, scenario, today),
            "runway": horizon["runway"],
        },
        "alerts": _alerts(country, reservoirs, horizon, data_quality),
        "data_quality": data_quality,
        "sources": [],
        "ai_trace": {
            "enabled": bool(settings.AI_AGENTS_ENABLED),
            "policy": {
                "allow_subindex_adjustment": bool(settings.AI_ALLOW_SUBINDEX_ADJUSTMENT),
                "max_adjustment": settings.AI_MAX_ADJUSTMENT,
                "core_formula_mutable": False,
            },
            "contributions": [],
            "slots": [],
        },
    }
    if persist:
        store_snapshot(country, result)
    return result


def _band_payload(score: float) -> dict:
    for key, threshold, label in STATUS_BANDS:
        if score >= threshold:
            return {"key": key, "label": label, "min": threshold}
    return {"key": "critical", "label": "Critical", "min": 0}


def _narrative(
    country: Country,
    scenario: Scenario,
    horizon: dict,
    status_label: str,
    base_index: float,
    headline_label: str,
    bottleneck: dict,
) -> dict:
    state = horizon["state"]
    rain_day = horizon["days_to_rain"]
    score_label = "scenario score" if scenario.hypothetical else "current-state score"
    rain_text = f"Rain runoff arrives in {rain_day} days" if rain_day else "No significant rain is forecast in the next 14 days"
    if state == "secured":
        summary = (
            f"Stored water covers {horizon['cover_days']:.0f} days of demand. {rain_text}, "
            f"bringing about {horizon['rain_amount_mm']:.0f} mm. The forward reserve stays above the emergency threshold, "
            f"so the horizon verdict is OK. The {score_label} is {base_index:.1f}/100."
        )
    elif state == "buffered":
        summary = (
            f"{rain_text}, but stored water covers {horizon['cover_days']:.0f} days, more than twice the planning horizon. "
            f"The system is buffered; the {score_label} is {base_index:.1f}/100."
        )
    elif state == "tight":
        summary = (
            f"{rain_text}, but the simulated reserve falls below the emergency threshold before the refill. "
            f"Stored water covers {horizon['cover_days']:.0f} days; the {score_label} is {base_index:.1f}/100."
        )
    else:
        summary = (
            f"{rain_text}, and stored water covers only {horizon['cover_days']:.0f} days. "
            f"The absence of a refill is the binding constraint; the {score_label} is {base_index:.1f}/100."
        )
    if scenario.hypothetical:
        summary += " This is a what-if scenario, not a live forecast."
    return {
        "headline": horizon["verdict"],
        "headline_label": headline_label,
        "summary": summary,
        "bottleneck": f"The weakest pillar is {bottleneck['label']} at {bottleneck['value']:.0f}/100.",
        "status": status_label,
        "condition": (
            "conditional on the forecast"
            if state == "secured"
            else "forward-looking"
            if state in {"buffered", "tight", "exposed"}
            else "current"
        ),
        "country": country.name,
    }


def _forecast_series(
    rows_by_res: dict[int, list[ForecastDay]],
    reservoirs: list[Reservoir],
    weights: dict[int, float],
    scenario: Scenario,
    today: date,
) -> list[dict]:
    series = []
    for index in range(16):
        day = today + timedelta(days=index)
        rain = 0.0
        for reservoir in reservoirs:
            rain += _rain_value(rows_by_res[reservoir.id], day, scenario, index) * weights.get(
                reservoir.id, 0.0
            )
        series.append({"date": day.isoformat(), "rain_mm": round(rain, 1)})
    return series


def _alerts(
    country: Country,
    reservoirs: list[Reservoir],
    horizon: dict,
    data_quality: dict,
) -> list[dict]:
    alerts = []
    for reservoir in reservoirs:
        if reservoir.storage_pct < 20:
            alerts.append(
                {
                    "level": "watch",
                    "title": f"{reservoir.name} storage is low",
                    "detail": f"{reservoir.storage_pct:.0f}% of capacity; {reservoir.storage_source} storage.",
                }
            )
    if data_quality.get("fallback"):
        alerts.append(
            {
                "level": "info",
                "title": "Fallback data in use",
                "detail": "One or more live sources could not be reached; confidence is reduced.",
            }
        )
    alerts.extend({"level": "warning", "title": "Local reserve alert", "detail": row["message"]} for row in horizon.get("alerts", []))
    return alerts[:8]


def empty_result(country: Country, scenario: Scenario, today: date) -> dict:
    return {
        "meta": {
            "product": "AquaState",
            "index": "Water Resilience Index",
            "version": settings.INDEX_VERSION,
            "generated_at": timezone.now().isoformat(),
            "as_of": today.isoformat(),
            "mode": "deterministic-mathematics",
            "ai_enabled": bool(settings.AI_AGENTS_ENABLED),
        },
        "country": country_payload(country),
        "hydrologic_centroid": {"lat": country.lat, "lon": country.lon},
        "scenario": scenario.as_dict(),
        "index": {
            "value": 0,
            "base_value": 0,
            "status": "critical",
            "status_label": "No data",
            "headline_status": "critical",
            "headline_label": "No data",
            "band": {"key": "critical", "label": "No data", "min": 0},
            "horizon_gate": {"applied": False, "score_unchanged": True, "secured": False, "base_index": 0, "reason": "No reservoirs loaded."},
            "confidence": 0,
            "confidence_label": "Low",
            "weights": settings.INDEX_WEIGHTS,
            "bottleneck_penalty": 0,
            "bottleneck": {"key": None, "label": "No data", "value": 0},
            "aggregation_formula": "No data.",
            "bands": [{"key": key, "min": threshold, "label": label} for key, threshold, label in STATUS_BANDS],
        },
        "pillars": [],
        "horizon": {
            "state": "unknown",
            "verdict": "No reservoir data",
            "headline": "No reservoir data",
            "days_to_rain": None,
            "rain_amount_mm": 0,
            "cover_days": 0,
            "runway": [],
            "reservoirs": [],
            "alerts": [],
        },
        "narrative": {
            "headline": "No reservoir data",
            "summary": "Add a reservoir inventory or load the national reference pool.",
            "bottleneck": "",
            "status": "No data",
            "condition": "unknown",
            "country": country.name,
        },
        "reservoirs": [],
        "aquifers": [],
        "soil": {"current": None, "normal": None, "percentile": None, "date": today.isoformat(), "source": "none"},
        "series": {"storage_history": [], "soil_history": [], "forecast": [], "runway": []},
        "alerts": [],
        "data_quality": {"confidence": 0, "label": "Low", "mode": country.data_mode, "fallback": True, "proxy": False, "notes": []},
        "sources": [],
        "ai_trace": {"enabled": False, "policy": {}, "contributions": [], "slots": []},
    }


def store_snapshot(country: Country, result: dict) -> IndexSnapshot:
    snapshot = IndexSnapshot.objects.create(
        country=country,
        scenario=result["scenario"],
        base_index=result["index"]["base_value"],
        final_index=result["index"]["value"],
        status=result["index"]["status"],
        verdict=result["horizon"]["verdict"],
        horizon_state=result["horizon"]["state"],
        pillars=result["pillars"],
        horizon=result["horizon"],
        narrative=result["narrative"]["summary"],
        confidence=result["index"]["confidence"],
        data_quality=result["data_quality"],
        formula_version=result["meta"]["version"],
        ai_trace=result.get("ai_trace", {}),
    )
    # Keep the demo database compact.
    old_ids = list(
        IndexSnapshot.objects.filter(country=country)
        .order_by("-created_at")
        .values_list("id", flat=True)[100:]
    )
    if old_ids:
        IndexSnapshot.objects.filter(id__in=old_ids).delete()
    return snapshot
