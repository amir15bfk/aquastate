"""SRRI — Soil & Runoff Readiness Index (refill readiness, not flood risk)."""
from __future__ import annotations

import math

from core.services.contracts import IndexContext, IndexEvaluationResult, clamp
from core.services.indices.base import BaseIndexProvider
from core.services.stats import percentile_score


def cn_i_from_ii(cn_ii: float) -> float:
    return clamp(4.2 * cn_ii / (10.0 - 0.058 * cn_ii), 0.0, 100.0)


def cn_iii_from_ii(cn_ii: float) -> float:
    return clamp(23.0 * cn_ii / (10.0 + 0.13 * cn_ii), 0.0, 100.0)


def wet_day_p95(days) -> float | None:
    wet = sorted(
        float(day.precip_mm)
        for day in days
        if day.precip_mm is not None and float(day.precip_mm) > 1.0
    )
    if not wet:
        return None
    index = max(0, math.ceil(0.95 * len(wet)) - 1)
    return wet[index]


def display_c_runoff(c_ref: float) -> float:
    return clamp(0.05 + 0.80 * c_ref, 0.05, 0.85)


def c_ref_from_p_ref(p_ref_mm: float, cn_eff: float) -> tuple[float, float, float]:
    storage = max(1e-9, 25400.0 / cn_eff - 254.0)
    if p_ref_mm <= 0.2 * storage:
        return 0.0, 0.0, storage
    runoff = (p_ref_mm - 0.2 * storage) ** 2 / (p_ref_mm + 0.8 * storage)
    return runoff / p_ref_mm, runoff, storage


class SRRIProvider(BaseIndexProvider):
    index_id = "SRRI"
    version = "1.0"

    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        dam = ctx.dam
        metadata = dam.metadata or {}
        components = {"week": ctx.week}
        cn_ii = clamp(float(metadata.get("cn_ii", 75.0)), 1.0, 99.0)
        cn_i = cn_i_from_ii(cn_ii)
        cn_iii = cn_iii_from_ii(cn_ii)
        components.update({"cn_ii": cn_ii, "cn_i": cn_i, "cn_iii": cn_iii})

        latest = ctx.current_climate()
        soil = latest.soil_moisture_m3m3 if latest else None
        if soil is None:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                explanation="No current soil-moisture observation is available.",
                proof_steps=["θ missing → NO_DATA"],
            )

        theta_wp = float(metadata.get("theta_wp", 0.12))
        theta_fc = float(metadata.get("theta_fc", 0.32))
        if not (theta_fc > theta_wp > 0):
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="INVALID",
                confidence=0.0,
                components={**components, "theta_wp": theta_wp, "theta_fc": theta_fc},
                explanation="Soil bounds are invalid: require θ_fc > θ_wp > 0.",
                proof_steps=["θ_fc <= θ_wp or θ_wp <= 0 → INVALID"],
            )

        saturation = clamp((float(soil) - theta_wp) / (theta_fc - theta_wp), 0.0, 1.0)
        cn_eff = clamp(cn_i + saturation * (cn_iii - cn_i), 1.0, 100.0)

        design_storm = metadata.get("design_storm_mm")
        if design_storm is not None:
            p_ref = max(25.0, float(design_storm))
            p_ref_source = "design_storm"
        else:
            p95 = wet_day_p95(ctx.climate.days)
            p_ref = max(25.0, p95 or 0.0)
            p_ref_source = "wet_day_p95" if p95 is not None else "floor_25mm"

        c_ref, runoff, storage = c_ref_from_p_ref(p_ref, cn_eff)
        if p_ref <= 0.2 * storage:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="INVALID",
                confidence=0.0,
                components={
                    **components,
                    "p_ref_mm": p_ref,
                    "storage_mm": storage,
                    "c_ref": c_ref,
                    "p_ref_source": p_ref_source,
                },
                explanation="P_ref does not exceed 0.2·S(CN_I); the runoff ratio is undefined.",
                proof_steps=["P_ref <= 0.2·S(CN_I) → INVALID"],
            )

        baseline = ctx.climatology_values("srri_c_ref")
        percentile = percentile_score(baseline, c_ref)
        flood_penalty = clamp((c_ref - 0.7) / 0.3, 0.0, 1.0)
        score = clamp(percentile.score * (1.0 - 0.15 * flood_penalty))
        available = percentile.n > 0
        data_status = percentile.data_status if available else "NO_DATA"
        c_runoff = display_c_runoff(c_ref)
        components.update(
            {
                "saturation": saturation,
                "cn_eff": cn_eff,
                "p_ref_mm": p_ref,
                "p_ref_source": p_ref_source,
                "storage_mm": storage,
                "q_mm": runoff,
                "c_ref": c_ref,
                "c_runoff": c_runoff,
                "p_c_ref": percentile.score,
                "baseline_n": percentile.n,
                "flood_penalty": flood_penalty,
            }
        )
        return IndexEvaluationResult(
            index_id=self.index_id,
            score=round(score, 6),
            status="OK" if available else "NO_DATA",
            available=available,
            data_status=data_status,
            confidence=round(percentile.confidence, 6),
            components=components,
            explanation=(
                f"CN_eff={cn_eff:.2f}, S={storage:.2f} mm, P_ref={p_ref:.1f} mm, "
                f"raw C_ref={c_ref:.3f} ranks {percentile.score:.1f}; "
                f"display C_runoff={c_runoff:.2f}, flood penalty={flood_penalty:.3f}. "
                "This is refill readiness, not flood risk."
            ),
            proof_steps=[
                f"CN_I={cn_i:.3f}, CN_III={cn_iii:.3f} from CN_II={cn_ii:.2f}",
                f"s=clamp((θ-θ_wp)/(θ_fc-θ_wp))={saturation:.3f}",
                f"CN_eff={cn_eff:.3f}; S=25400/CN_eff-254={storage:.3f} mm",
                f"Q=({p_ref:.3f}-0.2·{storage:.3f})²/({p_ref:.3f}+0.8·{storage:.3f})"
                f"={runoff:.3f} mm",
                f"C_ref=Q/P_ref={c_ref:.5f}; rank={percentile.score:.3f} (N={percentile.n})",
                f"SRRI={percentile.score:.3f}·(1-0.15·{flood_penalty:.3f})={score:.3f}",
            ],
        )
