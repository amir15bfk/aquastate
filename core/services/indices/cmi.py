"""CMI — Catchment Meteorological Index (current state only)."""
from __future__ import annotations

from statistics import NormalDist

from core.services.contracts import IndexContext, IndexEvaluationResult, clamp
from core.services.indices.base import BaseIndexProvider
from core.services.stats import percentile_score


def _total(days, field_name: str, count: int):
    window = days[-count:]
    if len(window) < count:
        return None
    values = [getattr(day, field_name) for day in window]
    if any(value is None for value in values):
        return None
    return float(sum(values))


class CMIProvider(BaseIndexProvider):
    index_id = "CMI"
    version = "1.0"

    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        p30_total = _total(ctx.climate.days, "precip_mm", 30)
        p90_total = _total(ctx.climate.days, "precip_mm", 90)
        components = {
            "p30_total_mm": p30_total,
            "p90_total_mm": p90_total,
            "week": ctx.week,
            "spi_method": "empirical_26y",
        }
        if p30_total is None or p90_total is None:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                explanation="The 30-day or 90-day precipitation window is incomplete.",
                proof_steps=["30/90-day precipitation missing → NO_DATA"],
            )

        p30_base = ctx.climatology_values("cmi_p30")
        p90_base = ctx.climatology_values("cmi_p90")
        dry_base = ctx.climatology_values("dry_spell")
        p30 = percentile_score(p30_base, p30_total)
        p90 = percentile_score(p90_base, p90_total)

        dry_days = ctx.climate.days_since_rain(threshold_mm=5.0, cap=180)
        projected = bool(ctx.scenario_overrides.get("projected"))
        storm_recharged = projected and any(
            (day.precip_mm or 0.0) >= 10.0 for day in ctx.climate.days[-14:]
        )
        if storm_recharged:
            p_dry = 0.0
            dry_score = 100.0
            dry_n = 26
        else:
            dry_percentile = percentile_score(
                dry_base, float(dry_days), higher_is_better=False
            )
            p_dry = 100.0 - dry_percentile.score
            dry_score = dry_percentile.score
            dry_n = dry_percentile.n

        available = p30.n > 0 and p90.n > 0 and dry_n > 0
        if not available:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components={
                    **components,
                    "p30": p30.score,
                    "p90": p90.score,
                    "dry_spell_days": dry_days,
                    "p_dry": p_dry,
                    "dry_score": dry_score,
                },
                explanation="One or more CMI baselines are empty; CMI is unavailable.",
                proof_steps=["N=0 in a CMI baseline → NO_DATA"],
            )

        score = clamp(0.60 * p90.score + 0.25 * p30.score + 0.15 * dry_score)
        confidence = min(p30.confidence, p90.confidence)
        spi1 = NormalDist().inv_cdf(clamp(p30.score / 100.0, 0.001, 0.999))
        spi3 = NormalDist().inv_cdf(clamp(p90.score / 100.0, 0.001, 0.999))
        components.update(
            {
                "p30": round(p30.score, 6),
                "p90": round(p90.score, 6),
                "p_dry": round(p_dry, 6),
                "dry_score": round(dry_score, 6),
                "dry_spell_days": dry_days,
                "spi1": round(spi1, 6),
                "spi3": round(spi3, 6),
                "p30_n": p30.n,
                "p90_n": p90.n,
                "dry_n": dry_n,
                "projected": projected,
            }
        )
        return IndexEvaluationResult(
            index_id=self.index_id,
            score=round(score, 6),
            status="OK",
            available=True,
            data_status="OK",
            confidence=round(confidence, 6),
            components=components,
            explanation=(
                f"30-day rain {p30_total:.1f} mm ranks {p30.score:.1f}; "
                f"90-day rain {p90_total:.1f} mm ranks {p90.score:.1f}; "
                f"{dry_days} dry days score {dry_score:.1f}. "
                f"CMI = 0.60·P90 + 0.25·P30 + 0.15·dry = {score:.2f}."
            ),
            proof_steps=[
                f"P30 = {p30_total:.2f} mm → mid-rank {p30.score:.3f} (N={p30.n})",
                f"P90 = {p90_total:.2f} mm → mid-rank {p90.score:.3f} (N={p90.n})",
                f"Dry spell = {dry_days} d → score {dry_score:.3f} (N={dry_n})",
                f"CMI = 0.60·{p90.score:.3f} + 0.25·{p30.score:.3f} + "
                f"0.15·{dry_score:.3f} = {score:.3f}",
            ],
        )
