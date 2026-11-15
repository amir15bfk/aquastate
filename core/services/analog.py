"""Deterministic historical analog engine (no circular week encoding)."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from statistics import NormalDist

from core.services.contracts import IndexContext
from core.services.exceptions import ScenarioValidationError
from core.services.stats import percentile_score, week_bin

FEATURE_NAMES = ("fill_pct", "spi3", "c_ref", "storage_anomaly")
DISCLAIMER = (
    "Historical analog only — not a forecast. Similarity is a feature-space "
    "distance over 2000–2025 observations."
)


@dataclass
class AnalogCandidate:
    year: int
    week: int
    features: dict
    trajectory: list[float] = field(default_factory=list)
    window_available: bool = True


@dataclass
class AnalogMatch:
    year: int
    week: int
    distance: float
    similarity: float
    delta_fill_90d: float
    trajectory: list[float]
    disclaimer: str = DISCLAIMER


def _week_distance(a: int, b: int) -> int:
    diff = abs(int(a) - int(b))
    return min(diff, 52 - diff)


def _finite_features(features: dict) -> dict[str, float]:
    missing = [name for name in FEATURE_NAMES if name not in features]
    if missing:
        raise ScenarioValidationError(
            f"analog feature vector is missing: {', '.join(missing)}"
        )
    clean = {}
    for name in FEATURE_NAMES:
        value = features[name]
        if value is None or not math.isfinite(float(value)):
            raise ScenarioValidationError(f"analog feature {name} is not finite")
        clean[name] = float(value)
    return clean


class AnalogEngine:
    @classmethod
    def find_analogs(
        cls,
        ctx: IndexContext,
        current_features: dict | None = None,
        top_n: int = 3,
        history: list[AnalogCandidate] | None = None,
    ) -> list[AnalogMatch]:
        current = _finite_features(
            current_features if current_features is not None else cls.current_features(ctx)
        )
        candidates = history if history is not None else cls._history_from_context(ctx)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.window_available
            and _week_distance(candidate.week, ctx.week) <= 4
            and candidate.year <= (ctx.as_of.year - 1 if ctx.as_of else 9999)
        ]
        if not candidates:
            return []

        means: dict[str, float] = {}
        stds: dict[str, float] = {}
        for name in FEATURE_NAMES:
            values = [float(candidate.features[name]) for candidate in candidates]
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            means[name] = mean
            stds[name] = max(1e-9, math.sqrt(variance))

        def distance(features: dict) -> float:
            return math.sqrt(
                sum(
                    ((float(features[name]) - means[name]) / stds[name]) ** 2
                    for name in FEATURE_NAMES
                )
            )

        current_standardized = {
            name: (current[name] - means[name]) / stds[name] for name in FEATURE_NAMES
        }
        scored = []
        for candidate in candidates:
            candidate_standardized = {
                name: (candidate.features[name] - means[name]) / stds[name]
                for name in FEATURE_NAMES
            }
            dist = math.sqrt(
                sum(
                    (current_standardized[name] - candidate_standardized[name]) ** 2
                    for name in FEATURE_NAMES
                )
            )
            scored.append((dist, candidate))

        # One best week per year, then nearest first.
        by_year: dict[int, tuple[float, AnalogCandidate]] = {}
        for dist, candidate in scored:
            existing = by_year.get(candidate.year)
            if existing is None or dist < existing[0]:
                by_year[candidate.year] = (dist, candidate)
        ordered = sorted(by_year.values(), key=lambda item: (item[0], item[1].year))
        matches = []
        for dist, candidate in ordered[: max(0, top_n)]:
            trajectory = list(candidate.trajectory)
            matches.append(
                AnalogMatch(
                    year=candidate.year,
                    week=candidate.week,
                    distance=round(dist, 6),
                    similarity=round(1.0 / (1.0 + dist), 6),
                    delta_fill_90d=round(trajectory[-1], 6) if trajectory else 0.0,
                    trajectory=trajectory,
                )
            )
        return matches

    @classmethod
    def current_features(cls, ctx: IndexContext) -> dict:
        fill = ctx.dam.current_fill_pct
        if fill is None:
            fill = 100.0 * ctx.dam.usable_volume_m3 / max(1.0, ctx.dam.usable_capacity_m3)
        p90_total = ctx.climate.total("precip_mm", 90)
        spi3 = 0.0
        if p90_total is not None:
            percentile = percentile_score(ctx.climatology_values("cmi_p90"), p90_total)
            spi3 = NormalDist().inv_cdf(max(0.001, min(0.999, percentile.score / 100.0)))
        from core.services.indices.srri import SRRIProvider

        srri = SRRIProvider().compute(ctx)
        c_ref = float(srri.components.get("c_ref", 0.0) or 0.0)
        baseline = ctx.climatology_values("ssi_fill_pct")
        median = sorted(baseline)[len(baseline) // 2] if baseline else 0.0
        return {
            "fill_pct": float(fill),
            "spi3": float(spi3),
            "c_ref": c_ref,
            "storage_anomaly": float(fill) - float(median),
        }

    @classmethod
    def _history_from_context(cls, ctx: IndexContext) -> list[AnalogCandidate]:
        from core.models import ClimateObservation, ReservoirObservation

        dam_slug = ctx.dam.slug
        observations = list(
            ReservoirObservation.objects.filter(
                dam__slug=dam_slug, date__lte=ctx.as_of
            ).order_by("date")
        )
        if not observations:
            return []
        climate = list(
            ClimateObservation.objects.filter(
                basin__dams__slug=dam_slug, date__lte=ctx.as_of
            ).order_by("date")
        )
        climate_by_date = {row.date: row for row in climate}
        obs_by_date = {row.date: row for row in observations}
        last_date = max(obs_by_date)
        baseline_year_end = ctx.as_of.year - 1 if ctx.as_of else last_date.year

        def nearest_observation(target: dt.date):
            row = obs_by_date.get(target)
            if row is not None:
                return row
            for delta in (1, 2, 3):
                for sign in (-1, 1):
                    row = obs_by_date.get(target + dt.timedelta(days=sign * delta))
                    if row is not None:
                        return row
            return None

        candidates: list[AnalogCandidate] = []
        for obs in observations:
            if obs.fill_pct is None or obs.date.year > baseline_year_end:
                continue
            week = week_bin(obs.date.timetuple().tm_yday)
            if _week_distance(week, ctx.week) > 4:
                continue

            p90_values = [
                climate_by_date.get(obs.date - dt.timedelta(days=offset))
                for offset in range(90)
            ]
            if any(row is None or row.precip_mm is None for row in p90_values):
                spi3 = 0.0
            else:
                total = sum(row.precip_mm for row in p90_values)
                percentile = percentile_score(
                    ctx.climatology_values("cmi_p90", week), total
                )
                spi3 = NormalDist().inv_cdf(
                    max(0.001, min(0.999, percentile.score / 100.0))
                )

            latest = climate_by_date.get(obs.date)
            soil = latest.soil_moisture_m3m3 if latest and latest.soil_moisture_m3m3 else 0.2
            metadata = ctx.dam.metadata or {}
            cn_ii = float(metadata.get("cn_ii", 75.0))
            cn_i = max(0.0, min(100.0, 4.2 * cn_ii / (10.0 - 0.058 * cn_ii)))
            cn_iii = max(0.0, min(100.0, 23.0 * cn_ii / (10.0 + 0.13 * cn_ii)))
            saturation = max(0.0, min(1.0, (soil - 0.12) / (0.32 - 0.12)))
            cn_eff = cn_i + saturation * (cn_iii - cn_i)
            p_ref = float(metadata.get("design_storm_mm") or 25.0)
            storage = max(1e-9, 25400.0 / max(1.0, cn_eff) - 254.0)
            runoff = (
                (p_ref - 0.2 * storage) ** 2 / (p_ref + 0.8 * storage)
                if p_ref > 0.2 * storage
                else 0.0
            )
            c_ref = runoff / p_ref if p_ref > 0 else 0.0

            baseline = ctx.climatology_values("ssi_fill_pct", week)
            median = sorted(baseline)[len(baseline) // 2] if baseline else 0.0
            trajectory = []
            available = True
            for horizon in range(1, 14):
                target = obs.date + dt.timedelta(days=7 * horizon)
                if target > ctx.as_of or target > last_date:
                    available = False
                    break
                row = nearest_observation(target)
                if row is None or row.fill_pct is None:
                    available = False
                    break
                trajectory.append(float(row.fill_pct) - float(obs.fill_pct))
            if not available:
                continue
            candidates.append(
                AnalogCandidate(
                    year=obs.date.year,
                    week=week,
                    features={
                        "fill_pct": float(obs.fill_pct),
                        "spi3": float(spi3),
                        "c_ref": float(c_ref),
                        "storage_anomaly": float(obs.fill_pct) - float(median),
                    },
                    trajectory=trajectory,
                    window_available=True,
                )
            )
        return candidates
