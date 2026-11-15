"""SSI — Surface Storage Index."""
from __future__ import annotations

from core.services.contracts import IndexContext, IndexEvaluationResult, clamp
from core.services.indices.base import BaseIndexProvider
from core.services.stats import percentile_score
from core.services.units import level_to_volume_m3


def _freshness(days: int | None) -> float:
    if days is None:
        return 0.5
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.75
    return 0.5


class SSIProvider(BaseIndexProvider):
    index_id = "SSI"
    version = "1.0"

    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        dam = ctx.dam
        usable_capacity = dam.usable_capacity_m3
        components = {
            "capacity_m3": dam.capacity_m3,
            "dead_storage_m3": dam.dead_storage_m3,
            "usable_capacity_m3": usable_capacity,
            "volume_m3": dam.current_volume_m3,
            "observation_date": str(dam.observation_date) if dam.observation_date else None,
        }
        if usable_capacity <= 0:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="INVALID",
                confidence=0.0,
                components=components,
                explanation="Usable capacity is zero or negative; SSI is invalid.",
                proof_steps=["V_uc = V_max - V_dead <= 0 → INVALID"],
            )

        volume = dam.current_volume_m3
        if volume is None and dam.current_level_m is not None:
            volume = level_to_volume_m3(dam.current_level_m, dam.bathymetry)
            components["volume_from_level_m3"] = volume
        if volume is None:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                explanation="No current volume or water level is available for this dam.",
                proof_steps=["V_t missing → NO_DATA"],
            )

        usable_volume = max(0.0, float(volume) - dam.dead_storage_m3)
        fill_pct = clamp(100.0 * usable_volume / usable_capacity, 0.0, 100.0)
        components.update(
            {
                "volume_m3": float(volume),
                "usable_volume_m3": usable_volume,
                "fill_pct": fill_pct,
            }
        )

        baseline = ctx.climatology_values("ssi_fill_pct")
        percentile = percentile_score(baseline, fill_pct, higher_is_better=True)
        age = (
            (ctx.as_of - dam.observation_date).days
            if ctx.as_of and dam.observation_date
            else None
        )
        confidence = percentile.confidence * _freshness(age)
        components.update(
            {
                "p_fill": percentile.score,
                "rank": percentile.rank,
                "baseline_n": percentile.n,
                "observation_age_days": age,
                "freshness": _freshness(age),
                "percentile_status": percentile.data_status,
            }
        )
        available = percentile.n > 0
        data_status = percentile.data_status if available else "NO_DATA"
        explanation = (
            f"Usable storage is {usable_volume / 1e6:,.2f} Mm³ of "
            f"{usable_capacity / 1e6:,.2f} Mm³ ({fill_pct:.2f}%). "
            f"The week-{ctx.week} baseline ranks this at the "
            f"{percentile.score:.1f}th percentile."
        )
        return IndexEvaluationResult(
            index_id=self.index_id,
            score=round(percentile.score, 6),
            status="OK" if available else "NO_DATA",
            available=available,
            data_status=data_status,
            confidence=round(confidence, 6),
            components=components,
            explanation=explanation,
            proof_steps=[
                f"V_uc = {dam.capacity_m3:,.0f} - {dam.dead_storage_m3:,.0f} "
                f"= {usable_capacity:,.0f} m³",
                f"V_u = max(0, {float(volume):,.0f} - {dam.dead_storage_m3:,.0f}) "
                f"= {usable_volume:,.0f} m³",
                f"Fill% = 100·V_u/V_uc = {fill_pct:.3f}%",
                f"N = {percentile.n}; mid-rank percentile = {percentile.score:.3f}",
            ],
        )
