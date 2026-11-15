"""SAI — Subsurface & Aquifer Index with a GRACE footprint-aware policy."""
from __future__ import annotations

import math

from core.services.contracts import IndexContext, IndexEvaluationResult, clamp
from core.services.indices.base import BaseIndexProvider
from core.services.stats import ols_slope, percentile_score

PILOT_AREA_THRESHOLD_KM2 = 70_000.0


def _annual_means(months) -> tuple[list[float], list[float]]:
    by_year: dict[int, list[float]] = {}
    for month in months:
        gwsa = month.gwsa_mm
        if gwsa is None or not math.isfinite(gwsa):
            continue
        by_year.setdefault(month.month.year, []).append(gwsa)
    years = sorted(by_year)
    means = [sum(by_year[year]) / len(by_year[year]) for year in years]
    return [float(year) for year in years], means


def _slope_with_ci(months):
    years, means = _annual_means(months)
    if len(years) < 2:
        return 0.0, 0.0, 0.0, 0.0
    slope, intercept, r2 = ols_slope(years, means)
    n = len(years)
    ci = 0.0
    if n > 2:
        mean_x = sum(years) / n
        sxx = sum((x - mean_x) ** 2 for x in years)
        if sxx > 0:
            ss_res = sum(
                (y - (intercept + slope * x)) ** 2 for x, y in zip(years, means)
            )
            se = math.sqrt(max(0.0, ss_res) / (n - 2) / sxx)
            ci = 1.96 * se
    return slope, slope - ci, slope + ci, r2


class SAIProvider(BaseIndexProvider):
    index_id = "SAI"
    version = "1.0"

    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        area_km2 = float(ctx.basin.area_km2 or ctx.dam.basin_area_km2 or 0.0)
        valid_months = [
            month
            for month in ctx.grace.months
            if month.gwsa_mm is not None and math.isfinite(month.gwsa_mm)
        ]
        gwsa_values = [month.gwsa_mm for month in valid_months]
        current_gwsa = gwsa_values[-1] if gwsa_values else None
        baseline = ctx.climatology_values("sai_gwsa")
        percentile = percentile_score(baseline, current_gwsa) if current_gwsa is not None else None
        slope, ci_low, ci_high, r2 = _slope_with_ci(valid_months)

        components = {
            "basin_area_km2": area_km2,
            "policy_threshold_km2": PILOT_AREA_THRESHOLD_KM2,
            "n_months": len(valid_months),
            "gwsa_mm": current_gwsa,
            "regional_percentile": percentile.score if percentile else None,
            "baseline_n": percentile.n if percentile else 0,
            "slope_mm_yr": slope,
            "slope_ci_low": ci_low,
            "slope_ci_high": ci_high,
            "slope_r2": r2,
            "kernel_corrected": ctx.grace.kernel_corrected,
        }

        if area_km2 < PILOT_AREA_THRESHOLD_KM2:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                contributions={"SAI": 0.0},
                explanation=(
                    f"GRACE's ~300 km footprint is coarser than this "
                    f"{area_km2:,.0f} km² basin. SAI is shown as NO_DATA with "
                    "regional GRACE percentile and depletion slope as display-only "
                    "diagnostics."
                ),
                proof_steps=[
                    "A_basin < 70,000 km² → SAI unavailable in the pilot policy",
                    f"Regional GWSA percentile = {components['regional_percentile']}",
                    f"Regional depletion slope = {slope:.3f} mm/yr "
                    f"[{ci_low:.3f}, {ci_high:.3f}] (display-only)",
                ],
            )

        if not ctx.grace.kernel_corrected:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components={**components, "reason": "kernel_correction_missing"},
                contributions={"SAI": 0.0},
                explanation=(
                    "A basin this large still requires identical-kernel convolution "
                    "and mascon gain/leakage correction before SAI is valid."
                ),
                proof_steps=["kernel_corrected=False → NO_DATA"],
            )

        if not valid_months or percentile is None or percentile.n == 0:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                contributions={"SAI": 0.0},
                explanation="No valid GRACE months or baseline; SAI is unavailable.",
                proof_steps=["N=0 GRACE months → NO_DATA"],
            )

        slope_score = clamp(50.0 + 5.0 * slope, 0.0, 100.0)
        score = clamp(0.8 * percentile.score + 0.2 * slope_score)
        support = clamp(area_km2 / PILOT_AREA_THRESHOLD_KM2, 0.0, 1.0)
        confidence = percentile.confidence * support
        components.update(
            {
                "slope_score": slope_score,
                "support": support,
                "p_gwsa": percentile.score,
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
            contributions={"SAI": round(score, 6)},
            explanation=(
                f"GWSA={current_gwsa:.2f} mm ranks {percentile.score:.1f}; "
                f"slope {slope:.2f} mm/yr scores {slope_score:.1f}. "
                f"SAI = 0.8·P(GWSA) + 0.2·slope = {score:.2f}."
            ),
            proof_steps=[
                f"GWSA = TWSA - SMSA - SWSA = {current_gwsa:.3f} mm",
                f"Regional percentile {percentile.score:.3f} from N={percentile.n}",
                f"Slope {slope:.3f} mm/yr, CI [{ci_low:.3f}, {ci_high:.3f}], "
                f"R²={r2:.3f}",
                f"SAI = 0.8·{percentile.score:.3f} + 0.2·{slope_score:.3f} = "
                f"{score:.3f}",
            ],
        )
