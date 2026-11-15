"""WCRI-2.0 — the country Water-Climate Resilience Index.

The score is deterministic. Every pillar carries its formula, inputs, source,
confidence and contribution. Missing data is neutral and low-confidence, never
a hidden zero; countries with less than 40% of the weight available are shown
as NO_DATA rather than given a false score.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean

from django.conf import settings

from hydro.services.statistics import clamp, normalise_weights
from world.services.statistics import (
    annual_means,
    annual_pet as annual_pet_series,
    annual_sums,
    hargreaves_pet_mm_day,
    mid_rank_percentile,
    rolling_sums,
    same_month_history,
    trend_score,
)

PILLAR_META = {
    "water": ("Water availability", "water", "Renewable freshwater per person and rainfall vs evaporative demand."),
    "drought": ("Drought & soil", "drought", "SPI-3, SPI-12, soil moisture and the current dry spell."),
    "groundwater": ("Groundwater", "groundwater", "Root-zone wetness and its trend; a labelled proxy when no aquifer inventory exists."),
    "flood": ("Flood resilience", "flood", "Forecast river discharge against its 60-day baseline, plus active flood events."),
    "fire": ("Wildfire resilience", "fire", "Fire weather (VPD, wind, dry spell, soil) coupled to drought and active fires."),
    "desertification": ("Desertification resilience", "desertification", "Aridity, rainfall trend, soil trend and forest-cover change."),
}

STATUS_BANDS = [
    ("resilient", 70.0, "Resilient"),
    ("stable", 55.0, "Stable"),
    ("watch", 40.0, "Watch"),
    ("stressed", 25.0, "Stressed"),
    ("critical", 0.0, "Critical"),
]


def status_for(score: float | None) -> tuple[str, str]:
    if score is None:
        return "no_data", "No data"
    for key, threshold, label in STATUS_BANDS:
        if score >= threshold:
            return key, label
    return "critical", "Critical"


def _band(score: float | None) -> dict:
    key, label = status_for(score)
    return {"key": key, "label": label}


def _safe_mean(values):
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return sum(values) / len(values) if values else None


def _clamp100(value: float | None) -> float | None:
    if value is None:
        return None
    return round(clamp(value, 0.0, 100.0), 2)


def _per_capita_score(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    # The Falkenmark scarcity anchors: 500 m³/person/year is absolute
    # scarcity (0), 10,000 is abundant (100), log-scaled between them.
    return _clamp100(
        (math.log10(max(1.0, value)) - math.log10(500.0))
        / (math.log10(10000.0) - math.log10(500.0))
        * 100.0
    )


def _annual_mean(points: list[tuple[int, float]]) -> float | None:
    return _safe_mean([value for _, value in points])


def _baseline(points: list[tuple[int, float]], current_year: int) -> list[tuple[int, float]]:
    return [(year, value) for year, value in points if year < current_year]


def _series_for_same_month(rolling: list[float | None], monthly: list[dict], month: int) -> list[float]:
    values = []
    for index, row in enumerate(monthly):
        if row["month"].month != month or index >= len(rolling):
            continue
        if rolling[index] is not None:
            values.append(float(rolling[index]))
    return values


def _fire_weather(rows: list[dict], today: date) -> dict:
    """A transparent fire-weather signal from the 92-day window + forecast."""
    past = [row for row in rows if row["date"] <= today]
    future = [row for row in rows if row["date"] > today]
    if len(past) < 14:
        return {"available": False, "pressure": 50.0, "confidence": 0.0, "inputs": {}}

    def vpd(row):
        t = row.get("tmax")
        rh = row.get("rh_min")
        if t is None or rh is None:
            return None
        es = 0.6108 * math.exp(17.27 * t / (t + 237.3))
        return max(0.0, es * (1.0 - rh / 100.0))

    past_vpd = [vpd(row) for row in past]
    current = next((row for row in reversed(future) if vpd(row) is not None), None)
    if current is None:
        current = next((row for row in reversed(past) if vpd(row) is not None), None)
    vpd_pct = mid_rank_percentile(past_vpd, vpd(current) if current else None)

    dry_days = 0
    for row in reversed(past):
        if (row.get("precip_mm") or 0.0) > 2.0:
            break
        dry_days += 1
    dry_days = min(180, dry_days)
    dry_risk = clamp(dry_days / 60.0 * 100.0, 0.0, 100.0)

    past_soil = [row.get("soil_surface") for row in past if row.get("soil_surface") is not None]
    current_soil = next((row.get("soil_surface") for row in reversed(future) if row.get("soil_surface") is not None), None)
    if current_soil is None:
        current_soil = next((row.get("soil_surface") for row in reversed(past) if row.get("soil_surface") is not None), None)
    soil_pct = mid_rank_percentile(past_soil, current_soil)

    past_wind = [row.get("wind_max") for row in past if row.get("wind_max") is not None]
    current_wind = next((row.get("wind_max") for row in reversed(future) if row.get("wind_max") is not None), None)
    wind_pct = mid_rank_percentile(past_wind, current_wind)

    risk = (
        0.35 * (vpd_pct["score"] if vpd_pct["available"] else 50.0)
        + 0.25 * dry_risk
        + 0.20 * (100.0 - (soil_pct["score"] if soil_pct["available"] else 50.0))
        + 0.20 * (wind_pct["score"] if wind_pct["available"] else 50.0)
    )
    return {
        "available": True,
        "pressure": _clamp100(risk),
        "confidence": 0.7,
        "inputs": {
            "vpd_percentile": vpd_pct["score"],
            "dry_days": dry_days,
            "soil_percentile": soil_pct["score"],
            "wind_percentile": wind_pct["score"],
        },
    }


def _flood_signal(rows: list[dict], today: date) -> dict:
    past = [row["discharge"] for row in rows if row["date"] <= today and row.get("discharge") is not None]
    future = [row["discharge"] for row in rows if row["date"] > today and row.get("discharge") is not None]
    if len(past) < 14 or not future:
        return {"available": False, "pressure": 50.0, "confidence": 0.0, "inputs": {}}
    peak = max(future)
    # Empirical quantiles of the 60-day baseline.
    ordered = sorted(past)
    q50 = ordered[len(ordered) // 2]
    q95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    if q95 <= q50:
        risk = 0.0 if peak <= q50 * 1.5 else 100.0
    else:
        risk = clamp((peak - q50) / (q95 - q50) * 100.0, 0.0, 100.0)
    return {
        "available": True,
        "pressure": _clamp100(risk),
        "confidence": 0.75,
        "inputs": {
            "peak_discharge": round(peak, 3),
            "baseline_p50": round(q50, 3),
            "baseline_p95": round(q95, 3),
            "forecast_peak_ratio": round(peak / q50, 2) if q50 else None,
        },
    }


def compute_country(
    *,
    iso2: str,
    iso3: str,
    country_name: str,
    lat: float,
    monthly: list[dict],
    forecast_rows: list[dict],
    flood_rows: list[dict],
    bank: dict,
    event_counts: dict[str, int] | None = None,
) -> dict:
    event_counts = event_counts or {}
    today = date.today()
    current_year = today.year
    weights = normalise_weights(settings.WCRI_WEIGHTS)

    # ------------------------------------------------------------------
    # Climate baseline
    # ------------------------------------------------------------------
    precip = [row.get("precip_mm") for row in monthly]
    soil = [row.get("soil_root") if row.get("soil_root") is not None else row.get("soil_top") for row in monthly]
    annual_p = annual_sums(monthly, "precip_mm")
    annual_pet_values = annual_pet_series(monthly, lat)
    # The current year is partial and is never part of its own baseline.
    annual_p_mean = _annual_mean(_baseline(annual_p, current_year))
    annual_pet_mean = _annual_mean(_baseline(annual_pet_values, current_year))
    aridity = (
        annual_p_mean / annual_pet_mean
        if annual_p_mean is not None and annual_pet_mean and annual_pet_mean > 0
        else None
    )
    soil_annual = annual_means(monthly, "soil_root")
    p_trend = trend_score(_baseline(annual_p, current_year), divisor=max(1.0, annual_p_mean or 1.0))
    soil_trend = trend_score(_baseline(soil_annual, current_year), divisor=1.0)
    latest_month = monthly[-1]["month"] if monthly else None
    current_month_no = latest_month.month if latest_month else today.month

    # SPI-3 / SPI-12 at the latest available month, against the same month in
    # the prior baseline years. The current year is never in its own baseline.
    rolling3 = rolling_sums(precip, 3)
    rolling12 = rolling_sums(precip, 12)
    current3 = next((v for v in reversed(rolling3) if v is not None), None)
    current12 = next((v for v in reversed(rolling12) if v is not None), None)
    hist3 = [v for i, v in enumerate(rolling3) if v is not None and monthly[i]["month"].month == current_month_no and monthly[i]["month"].year < current_year]
    hist12 = [v for i, v in enumerate(rolling12) if v is not None and monthly[i]["month"].month == current_month_no and monthly[i]["month"].year < current_year]
    spi3 = mid_rank_percentile(hist3, current3)
    spi12 = mid_rank_percentile(hist12, current12)

    current_soil = next((v for v in reversed(soil) if v is not None), None)
    soil_hist = same_month_history(monthly, current_month_no, "soil_root", before_year=current_year)
    if not soil_hist:
        soil_hist = same_month_history(monthly, current_month_no, "soil_top", before_year=current_year)
    soil_pct = mid_rank_percentile(soil_hist, current_soil)

    # Dry spell from the forecast's 92-day past window.
    past_days = [row for row in forecast_rows if row["date"] <= today]
    dry_days = 0
    for row in reversed(past_days):
        if (row.get("precip_mm") or 0.0) > 2.0:
            break
        dry_days += 1
    dry_days = min(180, dry_days)
    has_forecast_window = len(past_days) >= 14
    dry_score = clamp(100.0 * (1.0 - dry_days / 120.0), 0.0, 100.0) if has_forecast_window else 50.0

    if spi3["available"] or spi12["available"] or soil_pct["available"] or has_forecast_window:
        drought_value = (
            0.40 * (spi3["score"] if spi3["available"] else 50.0)
            + 0.25 * (spi12["score"] if spi12["available"] else 50.0)
            + 0.20 * (soil_pct["score"] if soil_pct["available"] else 50.0)
            + 0.15 * dry_score
        )
        drought_conf = 0.85 if spi3["available"] and spi12["available"] else (0.55 if spi3["available"] else 0.35)
    else:
        drought_value = None
        drought_conf = 0.0

    # ------------------------------------------------------------------
    # Water availability
    # ------------------------------------------------------------------
    bank_pop = (bank.get("population", {}).get(iso3) or {}).get("latest")
    bank_fw = (bank.get("freshwater_per_capita", {}).get(iso3) or {}).get("latest")
    withdrawal = (bank.get("freshwater_withdrawal_pct", {}).get(iso3) or {}).get("latest")
    per_capita_score = _per_capita_score(bank_fw)
    aridity_score = _clamp100((aridity or 0.0) / 0.65 * 100.0) if aridity is not None else None
    if per_capita_score is not None and aridity_score is not None:
        water_value = 0.55 * per_capita_score + 0.45 * aridity_score
        water_conf = 0.75
    elif aridity_score is not None:
        water_value = aridity_score
        water_conf = 0.55
    elif per_capita_score is not None:
        water_value = per_capita_score
        water_conf = 0.45
    else:
        water_value = None
        water_conf = 0.0
    if water_value is not None and withdrawal is not None and withdrawal > 100:
        water_value = max(0.0, water_value - 5.0)

    # ------------------------------------------------------------------
    # Groundwater proxy
    # ------------------------------------------------------------------
    if soil_pct["available"] or soil_trend.get("n", 0) >= 3:
        groundwater_value = 0.60 * (soil_pct["score"] if soil_pct["available"] else 50.0) + 0.40 * soil_trend["score"]
        groundwater_conf = 0.5 if soil_pct["available"] else 0.25
    else:
        groundwater_value = None
        groundwater_conf = 0.0

    # ------------------------------------------------------------------
    # Flood
    # ------------------------------------------------------------------
    flood_signal = _flood_signal(flood_rows, today)
    flood_events = event_counts.get(f"{iso2}:floods", 0)
    event_flood_pressure = min(100.0, flood_events * 25.0)
    if flood_signal["available"]:
        flood_pressure = 0.75 * flood_signal["pressure"] + 0.25 * event_flood_pressure
        flood_conf = 0.75
    elif flood_events:
        flood_pressure = event_flood_pressure
        flood_conf = 0.35
    else:
        flood_pressure = None
        flood_conf = 0.0
    flood_value = (100.0 - flood_pressure) if flood_pressure is not None else None

    # ------------------------------------------------------------------
    # Fire
    # ------------------------------------------------------------------
    fire_signal = _fire_weather(forecast_rows, today)
    fire_events = event_counts.get(f"{iso2}:wildfires", 0)
    drought_anchor = drought_value if drought_value is not None else 50.0
    drought_coupling = clamp((50.0 - drought_anchor) / 50.0, 0.0, 1.0) * 100.0
    active_fire_pressure = min(100.0, fire_events * 25.0)
    if fire_signal["available"]:
        fire_pressure = 0.65 * fire_signal["pressure"] + 0.20 * drought_coupling + 0.15 * active_fire_pressure
        fire_conf = 0.65
    elif fire_events:
        fire_pressure = 0.60 * 50.0 + 0.25 * drought_coupling + 0.15 * active_fire_pressure
        fire_conf = 0.25
    else:
        fire_pressure = None
        fire_conf = 0.0
    fire_value = (100.0 - fire_pressure) if fire_pressure is not None else None

    # ------------------------------------------------------------------
    # Desertification
    # ------------------------------------------------------------------
    aridity_pressure = _clamp100((0.50 - (aridity or 0.50)) / 0.50 * 100.0) if aridity is not None else None
    precip_pressure = _clamp100(-(p_trend.get("slope_pct_per_year") or 0.0) / 3.0 * 100.0)
    soil_pressure = _clamp100(-(soil_trend.get("slope_pct_per_year") or 0.0) / 1.0 * 100.0)
    forest = bank.get("forest_area_pct", {}).get(iso3) or {}
    forest_change = forest.get("change_pct")
    land_pressure = _clamp100(-(forest_change or 0.0) / 5.0 * 100.0) if forest_change is not None else 50.0
    if aridity_pressure is not None:
        desert_pressure = (
            0.40 * aridity_pressure
            + 0.30 * (precip_pressure or 50.0)
            + 0.20 * (soil_pressure or 50.0)
            + 0.10 * land_pressure
        )
        desert_conf = 0.75
    else:
        desert_pressure = None
        desert_conf = 0.0
    desert_value = (100.0 - desert_pressure) if desert_pressure is not None else None

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------
    values = {
        "water": water_value,
        "drought": drought_value,
        "groundwater": groundwater_value,
        "flood": flood_value,
        "fire": fire_value,
        "desertification": desert_value,
    }
    confidences = {
        "water": water_conf,
        "drought": drought_conf,
        "groundwater": groundwater_conf,
        "flood": flood_conf,
        "fire": fire_conf,
        "desertification": desert_conf,
    }
    available = {key: value for key, value in values.items() if value is not None and confidences[key] > 0.15}
    coverage = sum(weights[key] for key in available)
    if coverage < 0.40:
        score = None
        status_key, status_label = "no_data", "No data"
        confidence = 0.0
    else:
        # Renormalise over available pillars, then apply the two explicit
        # penalties. The score is never rewritten by a forecast.
        effective = {key: weights[key] / coverage for key in available}
        base = sum(effective[key] * available[key] for key in available)
        minimum = min(available.values())
        bottleneck = 0.12 * max(0.0, 30.0 - minimum)
        drought = values["drought"] if values["drought"] is not None else 50.0
        fire = values["fire"] if values["fire"] is not None else 50.0
        desert = values["desertification"] if values["desertification"] is not None else 50.0
        cascade = 0.05 * max(0.0, 45.0 - drought) * max(0.0, 45.0 - fire) / 45.0
        cascade += 0.05 * max(0.0, 45.0 - drought) * max(0.0, 45.0 - desert) / 45.0
        score = clamp(base - bottleneck - cascade, 0.0, 100.0)
        status_key, status_label = status_for(score)
        confidence = sum(effective[key] * confidences[key] for key in available)

    pillar_payload = {}
    for key, (label, hazard_key, interpretation) in PILLAR_META.items():
        value = values[key]
        pillar_payload[key] = {
            "key": key,
            "label": label,
            "value": round(value, 2) if value is not None else None,
            "weight": round(weights[key], 3),
            "contribution": round((weights[key] / coverage) * (value - 50.0), 2) if coverage and value is not None else 0.0,
            "confidence": round(confidences[key], 2),
            "source_kind": "live" if confidences[key] >= 0.7 else ("proxy" if key == "groundwater" else "modeled"),
            "formula": {
                "water": "W = 0.55 × freshwater-per-capita score + 0.45 × aridity score",
                "drought": "D = 0.40 × SPI-3 + 0.25 × SPI-12 + 0.20 × soil moisture + 0.15 × dry-spell score",
                "groundwater": "G = 0.60 × soil-moisture percentile + 0.40 × soil trend score",
                "flood": "FL = 100 − [0.75 × discharge pressure + 0.25 × event pressure]",
                "fire": "R = 100 − [0.65 × fire-weather pressure + 0.20 × drought coupling + 0.15 × active-fire pressure]",
                "desertification": "L = 100 − [0.40 × aridity + 0.30 × rainfall trend + 0.20 × soil trend + 0.10 × forest change]",
            }[key],
            "interpretation": interpretation,
            "inputs": {},
        }

    def pressure(value):
        return round(100.0 - value, 1) if value is not None else None

    hazard_payload = {
        "drought": {
            "pressure": pressure(drought_value),
            "value": round(drought_value, 1) if drought_value is not None else None,
            "unit": "resilience",
            "confidence": round(drought_conf, 2),
            "source": "NASA POWER monthly + Open-Meteo 92-day window",
            "inputs": {
                "spi3_percentile": spi3["score"],
                "spi12_percentile": spi12["score"],
                "soil_percentile": soil_pct["score"],
                "dry_days": dry_days,
            },
        },
        "flood": {
            "pressure": pressure(flood_value),
            "value": round(flood_value, 1) if flood_value is not None else None,
            "unit": "resilience",
            "confidence": round(flood_conf, 2),
            "source": "Open-Meteo GloFAS + NASA EONET",
            "inputs": flood_signal["inputs"] | {"active_events": flood_events},
        },
        "fire": {
            "pressure": pressure(fire_value),
            "value": round(fire_value, 1) if fire_value is not None else None,
            "unit": "resilience",
            "confidence": round(fire_conf, 2),
            "source": "Open-Meteo fire weather + NASA EONET",
            "inputs": fire_signal["inputs"] | {"drought_coupling": round(drought_coupling, 1), "active_events": fire_events},
        },
        "desertification": {
            "pressure": pressure(desert_value),
            "value": round(desert_value, 1) if desert_value is not None else None,
            "unit": "resilience",
            "confidence": round(desert_conf, 2),
            "source": "NASA POWER monthly + World Bank forest cover",
            "inputs": {
                "aridity_index": round(aridity, 3) if aridity is not None else None,
                "precip_trend_pct_per_year": p_trend.get("slope_pct_per_year"),
                "soil_trend_pct_per_year": soil_trend.get("slope_pct_per_year"),
                "forest_change_pct": forest_change,
            },
        },
    }

    climate_payload = {
        "annual_precip_mm": round(annual_p_mean, 1) if annual_p_mean is not None else None,
        "annual_pet_mm": round(annual_pet_mean, 1) if annual_pet_mean is not None else None,
        "aridity_index": round(aridity, 3) if aridity is not None else None,
        "precip_trend_pct_per_year": p_trend.get("slope_pct_per_year"),
        "precip_trend_p": p_trend.get("p"),
        "soil_trend_pct_per_year": soil_trend.get("slope_pct_per_year"),
        "soil_trend_p": soil_trend.get("p"),
        "latest_month": latest_month.isoformat() if latest_month else None,
        "annual_series": [
            {"year": year, "precip_mm": round(value, 1)}
            for year, value in annual_p
        ],
        "source": "NASA POWER / MERRA-2 monthly",
    }

    return {
        "iso2": iso2,
        "iso3": iso3,
        "name": country_name,
        "lat": lat,
        "score": round(score, 1) if score is not None else None,
        "status": status_key,
        "status_label": status_label,
        "confidence": round(confidence, 2),
        "coverage": round(coverage, 3),
        "pillars": pillar_payload,
        "hazards": hazard_payload,
        "climate": climate_payload,
        "bank": {
            "population": bank_pop,
            "freshwater_per_capita_m3": bank_fw,
            "freshwater_withdrawal_pct": withdrawal,
            "forest_area_pct": (forest or {}).get("latest"),
        },
        "aggregation": {
            "formula": "WCRI = Σ wᵢ·Sᵢ − 0.12·max(0, 30 − min(Sᵢ)) − drought/fire and drought/desertification cascade terms",
            "weights": weights,
            "coverage": round(coverage, 3),
        },
        "version": settings.WCRI_VERSION,
    }
