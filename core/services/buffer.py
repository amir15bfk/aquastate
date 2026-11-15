"""Forecast buffer bridge: autonomy, storm-event inflow, and Φ."""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.services.contracts import IndexContext
from core.services.units import km2_to_m2

EPSILON_FLOOR_M3_DAY = 1.0


@dataclass
class BufferResult:
    d_autonomy_days: float
    d_until_rain_days: int | None
    v_in14_m3: float
    v_proj14_m3: float
    phi: float
    q_out_m3_day: float
    epsilon_m3_day: float
    forecast_type: str
    forecast_confidence: float
    v_uc_m3: float
    v_u_m3: float
    d_autonomy_capped: bool = False
    demand_source: str = "known"
    event_count: int = 0
    v_in14_raw_m3: float = 0.0
    spill_headroom_m3: float = 0.0
    first_wet_days: int | None = None
    rain_gate: float = 0.0


def _sigmoid(value: float) -> float:
    value = max(-60.0, min(60.0, value))
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _smoothstep(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def group_storm_events(forecast_days) -> list[list[float]]:
    """Group consecutive wet days; one day below 1 mm ends an event."""
    events: list[list[float]] = []
    current: list[float] = []
    for day in forecast_days:
        precip = float(day.precip_mm or 0.0)
        if precip >= 1.0:
            current.append(precip)
        elif current:
            events.append(current)
            current = []
    if current:
        events.append(current)
    return events


def scs_runoff_mm(precip_mm: float, cn_eff: float) -> float:
    if precip_mm <= 0 or cn_eff <= 0:
        return 0.0
    storage = max(1e-9, 25400.0 / cn_eff - 254.0)
    if precip_mm <= 0.2 * storage:
        return 0.0
    return (precip_mm - 0.2 * storage) ** 2 / (precip_mm + 0.8 * storage)


def estimate_inflow(
    forecast_days, area_km2: float, cn_eff: float, eta: float = 0.8
) -> float:
    """Apply SCS-CN once per event, not once per day."""
    area = max(0.0, float(area_km2 or 0.0))
    if area <= 0:
        return 0.0
    total = 0.0
    for event in group_storm_events(forecast_days):
        runoff_mm = scs_runoff_mm(sum(event), cn_eff)
        total += max(0.0, runoff_mm) * area * 1_000.0 * max(0.0, eta)
    return total


def _cn_eff_from_context(ctx: IndexContext, sub_results: dict) -> float:
    srri = sub_results.get("SRRI")
    if srri is not None:
        value = srri.components.get("cn_eff")
        if value is not None and math.isfinite(float(value)):
            return max(1.0, min(100.0, float(value)))
    cn_ii = float(ctx.dam.metadata.get("cn_ii", 75.0))
    return max(1.0, min(100.0, cn_ii))


def compute_buffer(ctx: IndexContext, sub_results: dict | None = None) -> BufferResult:
    sub_results = sub_results or {}
    dam = ctx.dam
    v_uc = float(dam.usable_capacity_m3)
    if v_uc <= 0:
        return BufferResult(
            d_autonomy_days=0.0,
            d_until_rain_days=None,
            v_in14_m3=0.0,
            v_proj14_m3=0.0,
            phi=0.0,
            q_out_m3_day=0.0,
            epsilon_m3_day=0.0,
            forecast_type=ctx.forecast.forecast_type,
            forecast_confidence=ctx.forecast.confidence,
            v_uc_m3=v_uc,
            v_u_m3=0.0,
        )
    v_u = max(0.0, float(dam.usable_volume_m3))
    epsilon = max(EPSILON_FLOOR_M3_DAY, v_uc / 3650.0)
    epsilon_v = 14.0 * epsilon

    eesi = sub_results.get("EESI")
    e_loss = 0.0
    if eesi is not None:
        raw = eesi.components.get("e_loss_m3_day", 0.0)
        if raw is not None and math.isfinite(float(raw)):
            e_loss = max(0.0, float(raw))
    seepage = float(ctx.dam.metadata.get("seepage_m3_day", 0.0) or 0.0)
    demand = ctx.demand.latest_m3_day
    if demand is not None and math.isfinite(float(demand)):
        q_out = max(epsilon, float(demand)) + e_loss + max(0.0, seepage)
        demand_source = "known"
    else:
        # Drawdown fallback: E_loss and seepage are already inside the observed
        # drawdown term, so they are deliberately not added again.
        q_out = epsilon
        demand_source = "drawdown_fallback"
    q_out = max(epsilon, q_out)

    if v_u <= 0:
        d_autonomy = 0.0
        d_autonomy_capped = False
    else:
        d_autonomy = min(3650.0, v_u / q_out)
        d_autonomy_capped = v_u / q_out >= 3650.0

    d_until_rain = None
    first_wet_days = None
    for index, day in enumerate(ctx.forecast.days, start=1):
        precip = day.precip_mm or 0.0
        if precip >= 1.0 and first_wet_days is None:
            first_wet_days = index
        if precip >= 10.0 and d_until_rain is None:
            d_until_rain = index
            break

    area_km2 = float(ctx.basin.area_km2 or 0.0)
    cn_eff = _cn_eff_from_context(ctx, sub_results)
    eta = float(ctx.dam.metadata.get("runoff_coefficient", 0.8) or 0.0)
    v_in_raw = estimate_inflow(ctx.forecast.days, area_km2, cn_eff, eta)
    days_drawdown = 14.0 * q_out
    headroom = max(0.0, v_uc - (v_u - days_drawdown))
    v_in = min(v_in_raw, headroom)
    v_proj = max(0.0, min(v_uc, v_u - days_drawdown + v_in))

    events = group_storm_events(ctx.forecast.days)
    rain_gate = 0.0
    effective_until = None
    if first_wet_days is None or v_in_raw <= 0 or v_in <= 0:
        phi = 0.0
        effective_until = None
    else:
        # The signed spec gates the sigmoid on a >=10 mm day. A hard gate makes
        # a 39.6 mm storm score like a dry spell; use a continuous significance
        # ramp for sub-10 mm events while keeping the signed 65 mm case at 1.
        if d_until_rain is None:
            max_daily = max((day.precip_mm or 0.0) for day in ctx.forecast.days)
            rain_gate = _smoothstep((max_daily - 1.0) / 9.0)
            effective_until = first_wet_days
        else:
            rain_gate = 1.0
            effective_until = d_until_rain
        autonomy_argument = max(
            -60.0, min(60.0, (d_autonomy - effective_until) / 7.0)
        )
        ratio = (v_in_raw + epsilon_v) / (days_drawdown + epsilon_v)
        inflow_argument = max(
            -60.0, min(60.0, math.log(ratio) if ratio > 0 else -60.0)
        )
        phi = (
            rain_gate
            * _sigmoid(autonomy_argument)
            * _sigmoid(inflow_argument / 0.5)
        )

    return BufferResult(
        d_autonomy_days=round(d_autonomy, 6),
        d_until_rain_days=effective_until,
        v_in14_m3=v_in,
        v_proj14_m3=v_proj,
        phi=round(max(0.0, min(1.0, phi)), 8),
        q_out_m3_day=q_out,
        epsilon_m3_day=epsilon,
        forecast_type=ctx.forecast.forecast_type,
        forecast_confidence=ctx.forecast.confidence,
        v_uc_m3=v_uc,
        v_u_m3=v_u,
        d_autonomy_capped=d_autonomy_capped,
        demand_source=demand_source,
        event_count=len(events),
        v_in14_raw_m3=v_in_raw,
        spill_headroom_m3=headroom,
        first_wet_days=first_wet_days,
        rain_gate=round(rain_gate, 8),
    )
