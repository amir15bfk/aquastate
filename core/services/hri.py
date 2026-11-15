"""HRI — master Hydrological Resilience Index synthesizer."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass, field, replace

from core.services.buffer import BufferResult, compute_buffer
from core.services.contracts import (
    ClimateDay,
    ClimateWindow,
    ForecastWindow,
    IndexContext,
    IndexEvaluationResult,
    clamp,
)
from core.services.explain import build_explanation, build_proof_steps
from core.services.stats import week_bin

NOMINAL_WEIGHTS = {
    "SSI": 0.30,
    "CMI": 0.20,
    "SRRI": 0.15,
    "SAI": 0.20,
    "EESI": 0.15,
}
INDEX_ORDER = ("SSI", "CMI", "SRRI", "SAI", "EESI")

AUTONOMY_CAP_DAYS = 14.0
AUTONOMY_CAP_SCORE = 19.9
AUTONOMY_FULL_CAP_DAYS = 12.461538  # signed Case C3: 16.2 Mm³ / 1.30 Mm³/day
DRY_CAP_SCORE = 24.9
DRY_FULL_SSI = 5.357143  # signed Case A/B SSI
DRY_FULL_AUTONOMY = 27.0  # signed Case A/B autonomy


@dataclass
class HRISynthesisResult:
    hri: float
    status: str
    confidence: float
    phi: float
    sub_indices: dict
    contributions: dict
    components: dict
    explanation: str
    proof_steps: list[str]
    available: bool
    data_status: str
    hri_now: float = 0.0
    hri_proj: float = 0.0


def smoothstep(value: float) -> float:
    x = max(0.0, min(1.0, float(value)))
    return x * x * (3.0 - 2.0 * x)


def smooth_cap(hri: float, ssi: float, phi: float, d_autonomy: float) -> float:
    """Continuous low-storage guard.

    Full strength is reached at the signed Case A/B values (SSI 5.357,
    D_autonomy 27) and the signed Case C3 autonomy (12.46), so those fixtures
    land exactly on 24.9/19.9. Every gate releases smoothly to zero at its
    boundary; no strict comparison introduces a step.
    """
    dry_strength = (
        smoothstep((20.0 - ssi) / (20.0 - DRY_FULL_SSI))
        * smoothstep((0.3 - phi) / 0.3)
        * smoothstep((45.0 - d_autonomy) / (45.0 - DRY_FULL_AUTONOMY))
    )
    autonomy_strength = smoothstep(
        (AUTONOMY_CAP_DAYS - d_autonomy)
        / (AUTONOMY_CAP_DAYS - AUTONOMY_FULL_CAP_DAYS)
    )
    capped = hri - autonomy_strength * max(0.0, hri - AUTONOMY_CAP_SCORE)
    capped = capped - dry_strength * max(0.0, capped - DRY_CAP_SCORE)
    return capped


def cap_strengths(
    ssi: float, phi: float, d_autonomy: float
) -> tuple[float, float]:
    dry_strength = (
        smoothstep((20.0 - ssi) / (20.0 - DRY_FULL_SSI))
        * smoothstep((0.3 - phi) / 0.3)
        * smoothstep((45.0 - d_autonomy) / (45.0 - DRY_FULL_AUTONOMY))
    )
    autonomy_strength = smoothstep(
        (AUTONOMY_CAP_DAYS - d_autonomy)
        / (AUTONOMY_CAP_DAYS - AUTONOMY_FULL_CAP_DAYS)
    )
    return dry_strength, autonomy_strength


def classify_status(hri: float, phi: float, hri_now: float, hri_proj: float) -> str:
    if hri < 25.0:
        return "CRITICAL"
    if hri < 40.0:
        return "STRESSED"
    if hri < 55.0:
        return "WATCH"
    if hri >= 85.0:
        return "SURPLUS"
    if phi >= 0.5 and hri_proj > hri_now:
        return "RECHARGING"
    return "STABLE"


def build_projected_context(
    ctx: IndexContext, buffer: BufferResult
) -> IndexContext | None:
    if ctx.as_of is None or buffer.v_uc_m3 <= 0:
        return None
    projected_as_of = ctx.as_of + dt.timedelta(days=14)
    absolute_volume = ctx.dam.dead_storage_m3 + buffer.v_proj14_m3
    absolute_volume = max(
        ctx.dam.dead_storage_m3,
        min(float(ctx.dam.capacity_m3), absolute_volume),
    )
    fill_pct = clamp(
        100.0 * buffer.v_proj14_m3 / buffer.v_uc_m3, 0.0, 100.0
    )
    metadata = ctx.dam.metadata or {}
    latest = ctx.current_climate()
    projected_pet = float(
        metadata.get(
            "projected_pet_mm_day",
            latest.pet_mm if latest and latest.pet_mm is not None else 4.0,
        )
    )
    current_ratio = 0.0
    if latest and latest.pet_mm and latest.et_mm is not None and latest.pet_mm > 0:
        current_ratio = latest.et_mm / latest.pet_mm
    projected_ratio = float(metadata.get("projected_et_pet_ratio", current_ratio))
    lst_mean = metadata.get("lst_mean_k")
    projected_lst = None
    if lst_mean is not None:
        projected_lst = float(lst_mean) + float(
            metadata.get("projected_lst_anomaly_k", 0.0)
        )
    projected_soil = metadata.get("projected_soil_moisture")
    if projected_soil is None:
        projected_soil = latest.soil_moisture_m3m3 if latest else None

    climate_days = list(ctx.climate.days)
    for forecast_day in ctx.forecast.days:
        climate_days.append(
            ClimateDay(
                date=forecast_day.date,
                precip_mm=forecast_day.precip_mm,
                et_mm=projected_pet * projected_ratio,
                pet_mm=projected_pet,
                lst_k=projected_lst,
                soil_moisture_m3m3=projected_soil,
            )
        )
    projected_dam = replace(
        ctx.dam,
        current_volume_m3=absolute_volume,
        current_level_m=None,
        current_fill_pct=fill_pct,
        current_surface_area_km2=None,
        observation_date=projected_as_of,
        observation_quality="PROJECTED",
    )
    return replace(
        ctx,
        dam=projected_dam,
        climate=ClimateWindow(days=climate_days, source=ctx.climate.source),
        forecast=ForecastWindow(
            days=[], confidence=ctx.forecast.confidence,
            forecast_type=ctx.forecast.forecast_type, source=ctx.forecast.source,
        ),
        as_of=projected_as_of,
        week=week_bin(projected_as_of.timetuple().tm_yday),
        scenario_overrides={**ctx.scenario_overrides, "projected": True},
    )


def _no_data_result(
    data_status: str,
    reason: str,
    buffer: BufferResult | None,
    current: dict,
) -> HRISynthesisResult:
    components = {
        "hri_now": 0.0,
        "hri_proj": 0.0,
        "hri_before_cap": 0.0,
        "weights_effective": {},
        "buffer": asdict(buffer) if buffer else {},
        "cap_reason": reason,
        "agent_slot_status": "DETERMINISTIC_MVP",
        "sub_index_meta": {
            index: {
                "score": result.score,
                "available": result.available,
                "confidence": result.confidence,
                "data_status": result.data_status,
                "agent_slot_status": result.agent_slot_status,
            }
            for index, result in current.items()
        },
    }
    return HRISynthesisResult(
        hri=0.0,
        status="NO_DATA",
        confidence=0.0,
        phi=buffer.phi if buffer else 0.0,
        sub_indices={index: result.score for index, result in current.items()},
        contributions={"override": 0.0},
        components=components,
        explanation=build_explanation(
            "NO_DATA", 0.0, buffer.phi if buffer else 0.0, 0.0, 0.0,
            buffer or BufferResult(0, None, 0, 0, 0, 0, 0, "deterministic_single", 0, 0, 0),
            reason,
        ),
        proof_steps=["No participating index has a valid score → NO_DATA"],
        available=False,
        data_status=data_status,
    )


class HRISynthesizer:
    version = "1.0"
    master_agent_slot = None

    def compute(
        self,
        ctx: IndexContext,
        sub_results: dict[str, IndexEvaluationResult] | None = None,
        projected_results: dict[str, IndexEvaluationResult] | None = None,
    ) -> HRISynthesisResult:
        current = sub_results if sub_results is not None else self._compute_current(ctx)
        if ctx.dam.usable_capacity_m3 <= 0:
            return _no_data_result("INVALID", "invalid_storage", None, current)
        buffer = compute_buffer(ctx, current)

        projected = projected_results
        if projected is None:
            projected_ctx = build_projected_context(ctx, buffer)
            projected = self._compute_projected(ctx, projected_ctx, current)

        participating: list[str] = []
        weights_effective: dict[str, float] = {}
        raw_weights: dict[str, float] = {}
        scores_now: dict[str, float] = {}
        scores_proj: dict[str, float] = {}
        confidences: dict[str, float] = {}
        for index in INDEX_ORDER:
            now = current.get(index)
            if now is None or not now.available or now.confidence <= 0:
                continue
            if not math.isfinite(float(now.score)):
                continue
            proj = projected.get(index) if projected else None
            if proj is None or not proj.available or not math.isfinite(float(proj.score)):
                proj = now
            participating.append(index)
            raw_weights[index] = NOMINAL_WEIGHTS[index] * float(now.confidence)
            scores_now[index] = float(now.score)
            scores_proj[index] = float(proj.score)
            confidences[index] = float(now.confidence)

        raw_sum = sum(raw_weights.values())
        if not participating or raw_sum <= 0:
            return _no_data_result("NO_DATA", "no_data", buffer, current)
        weights_effective = {
            index: raw_weights[index] / raw_sum for index in participating
        }

        hri_now = sum(weights_effective[i] * scores_now[i] for i in participating)
        hri_proj = sum(weights_effective[i] * scores_proj[i] for i in participating)
        phi = buffer.phi
        hri_blend = (1.0 - phi) * hri_now + phi * hri_proj

        ssi_score = scores_now.get("SSI", 0.0)
        hri_smooth = smooth_cap(hri_blend, ssi_score, phi, buffer.d_autonomy_days)
        dry_strength, autonomy_strength = cap_strengths(
            ssi_score, phi, buffer.d_autonomy_days
        )
        hri_final = hri_smooth
        if autonomy_strength > 0.0:
            cap_reason = "autonomy_cap"
        elif dry_strength > 0.0:
            cap_reason = "dry_low_storage_cap"
        elif abs(hri_smooth - hri_blend) > 1e-12:
            cap_reason = "soft_override"
        else:
            cap_reason = None
        hri_final = clamp(hri_final, 0.0, 100.0)

        contributions: dict[str, float] = {}
        for index in participating:
            blended = (1.0 - phi) * scores_now[index] + phi * scores_proj[index]
            contributions[index] = weights_effective[index] * (blended - 50.0)
        contributions["override"] = hri_final - hri_blend

        status = classify_status(hri_final, phi, hri_now, hri_proj)
        confidence = sum(
            NOMINAL_WEIGHTS[index] * confidences[index] for index in participating
        ) / sum(NOMINAL_WEIGHTS[index] for index in participating)

        components = {
            "hri_now": hri_now,
            "hri_proj": hri_proj,
            "hri_before_cap": hri_blend,
            "hri_smooth": hri_smooth,
            "phi": phi,
            "weights_effective": weights_effective,
            "weights_nominal": {i: NOMINAL_WEIGHTS[i] for i in participating},
            "scores_now": scores_now,
            "scores_proj": scores_proj,
            "buffer": asdict(buffer),
            "cap_reason": cap_reason,
            "cap_delta": hri_final - hri_blend,
            "forecast_type": buffer.forecast_type,
            "forecast_confidence": buffer.forecast_confidence,
            "agent_slot_status": "DETERMINISTIC_MVP",
            "sub_index_meta": {
                index: {
                    "score": current[index].score,
                    "available": current[index].available,
                    "confidence": current[index].confidence,
                    "data_status": current[index].data_status,
                    "agent_slot_status": current[index].agent_slot_status,
                    "agent_id": current[index].agent_id,
                }
                for index in INDEX_ORDER
                if index in current
            },
            "waterfall": contributions,
        }
        explanation = build_explanation(
            status, hri_final, phi, hri_now, hri_proj, buffer, cap_reason
        )
        proof_steps = build_proof_steps(
            buffer, weights_effective, scores_now, scores_proj,
            hri_now, hri_proj, hri_final,
        )
        if cap_reason:
            proof_steps.append(
                f"Cap '{cap_reason}' applied: final HRI = {hri_final:.3f}"
            )
        return HRISynthesisResult(
            hri=float(hri_final),
            status=status,
            confidence=float(clamp(confidence, 0.0, 1.0)),
            phi=float(phi),
            sub_indices={i: float(scores_now[i]) for i in participating},
            contributions={k: float(v) for k, v in contributions.items()},
            components=components,
            explanation=explanation,
            proof_steps=proof_steps,
            available=True,
            data_status="OK",
            hri_now=float(hri_now),
            hri_proj=float(hri_proj),
        )

    @staticmethod
    def _compute_current(ctx: IndexContext) -> dict[str, IndexEvaluationResult]:
        from core.services.indices.registry import INDEX_REGISTRY

        results: dict[str, IndexEvaluationResult] = {}
        for index, provider in INDEX_REGISTRY.items():
            try:
                results[index] = provider.compute(ctx)
            except Exception:
                results[index] = IndexEvaluationResult(
                    index_id=index,
                    available=False,
                    status="NO_DATA",
                    data_status="NO_DATA",
                    confidence=0.0,
                )
        return results

    @staticmethod
    def _compute_projected(
        ctx: IndexContext,
        projected_ctx: IndexContext | None,
        current: dict[str, IndexEvaluationResult],
    ) -> dict[str, IndexEvaluationResult]:
        if projected_ctx is None:
            return dict(current)
        from core.services.indices.registry import INDEX_REGISTRY

        results: dict[str, IndexEvaluationResult] = {}
        for index, provider in INDEX_REGISTRY.items():
            if index == "SAI":
                results[index] = current.get(
                    index,
                    IndexEvaluationResult(
                        index_id=index, available=False, data_status="NO_DATA",
                        status="NO_DATA", confidence=0.0,
                    ),
                )
                continue
            try:
                results[index] = provider.compute(projected_ctx)
            except Exception:
                results[index] = current.get(
                    index,
                    IndexEvaluationResult(
                        index_id=index, available=False, data_status="NO_DATA",
                        status="NO_DATA", confidence=0.0,
                    ),
                )
        return results
