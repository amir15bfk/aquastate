"""Typed contracts shared by providers, index calculators, and the API.

These dataclasses are the stable seam between data access and math. Keep
physical values in SI units and every score on a 0–100 scale.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class BathymetryPointData:
    elevation_m: float
    area_km2: float
    volume_m3: float
    order: int = 0


@dataclass
class DamSnapshot:
    slug: str
    name: str
    country_iso3: str
    lat: float
    lon: float
    capacity_m3: float
    dead_storage_m3: float
    basin_area_km2: float
    bathymetry: list[BathymetryPointData] = field(default_factory=list)
    name_ar: str = ""
    name_fr: str = ""
    max_surface_area_km2: float | None = None
    purposes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    as_of: dt.date | None = None
    current_volume_m3: float | None = None
    current_level_m: float | None = None
    current_fill_pct: float | None = None
    current_surface_area_km2: float | None = None
    observation_date: dt.date | None = None
    observation_quality: str = "OK"
    observation_source: str = "seeded"

    @property
    def usable_capacity_m3(self) -> float:
        return float(self.capacity_m3) - float(self.dead_storage_m3)

    @property
    def usable_volume_m3(self) -> float:
        capacity = self.usable_capacity_m3
        if capacity <= 0 or self.current_volume_m3 is None:
            return 0.0
        return max(0.0, float(self.current_volume_m3) - float(self.dead_storage_m3))


@dataclass
class BasinSnapshot:
    basin_id: int | None
    country_iso3: str
    name: str
    area_km2: float
    hydrosheds_id: str = ""
    geometry: dict = field(default_factory=dict)
    centroid_lat: float = 0.0
    centroid_lon: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ClimateDay:
    date: dt.date
    precip_mm: float | None = None
    et_mm: float | None = None
    pet_mm: float | None = None
    lst_k: float | None = None
    soil_moisture_m3m3: float | None = None


@dataclass
class ClimateWindow:
    days: list[ClimateDay] = field(default_factory=list)
    source: str = "seeded"

    @property
    def start(self) -> dt.date | None:
        return self.days[0].date if self.days else None

    @property
    def end(self) -> dt.date | None:
        return self.days[-1].date if self.days else None

    def total(self, field_name: str, days: int | None = None) -> float | None:
        window = self.days[-days:] if days else self.days
        values = [getattr(day, field_name) for day in window]
        if not values or any(value is None for value in values):
            return None
        return float(sum(values))

    def days_since_rain(self, threshold_mm: float = 5.0, cap: int = 180) -> int:
        count = 0
        for day in reversed(self.days):
            rain = day.precip_mm or 0.0
            if rain > threshold_mm:
                return count
            count += 1
            if count >= cap:
                return cap
        return min(count, cap) if count else cap


@dataclass
class ForecastDay:
    date: dt.date
    precip_mm: float | None = None
    confidence: float = 1.0
    source: str = "seeded"


@dataclass
class ForecastWindow:
    days: list[ForecastDay] = field(default_factory=list)
    issued_at: dt.datetime | None = None
    confidence: float = 1.0
    forecast_type: str = "deterministic_single"
    source: str = "seeded"


@dataclass
class GraceMonth:
    month: dt.date
    twsa_mm: float | None = None
    smsa_mm: float | None = None
    swsa_mm: float | None = None

    @property
    def gwsa_mm(self) -> float | None:
        if self.twsa_mm is None or self.smsa_mm is None or self.swsa_mm is None:
            return None
        return self.twsa_mm - self.smsa_mm - self.swsa_mm


@dataclass
class GraceWindow:
    months: list[GraceMonth] = field(default_factory=list)
    basin_area_km2: float = 0.0
    baseline_epoch: dt.date | None = None
    kernel_corrected: bool = False
    source: str = "seeded"


@dataclass
class ETDay:
    date: dt.date
    et_mm: float | None = None
    pet_mm: float | None = None
    lst_k: float | None = None


@dataclass
class ETWindow:
    days: list[ETDay] = field(default_factory=list)
    source: str = "seeded"


@dataclass
class DemandDay:
    date: dt.date
    demand_m3_day: float = 0.0


@dataclass
class DemandWindow:
    days: list[DemandDay] = field(default_factory=list)
    source: str = "seeded"

    @property
    def latest_m3_day(self) -> float | None:
        return self.days[-1].demand_m3_day if self.days else None


@dataclass
class ClimatologyBinData:
    metric: str
    week: int
    values: list[float] = field(default_factory=list)
    n: int = 0
    mean: float | None = None
    std: float | None = None


@dataclass
class IndexContext:
    dam: DamSnapshot
    basin: BasinSnapshot
    climate: ClimateWindow = field(default_factory=ClimateWindow)
    forecast: ForecastWindow = field(default_factory=ForecastWindow)
    grace: GraceWindow = field(default_factory=GraceWindow)
    et: ETWindow = field(default_factory=ETWindow)
    demand: DemandWindow = field(default_factory=DemandWindow)
    climatology: dict[str, dict[int, ClimatologyBinData]] = field(default_factory=dict)
    as_of: dt.date | None = None
    week: int = 1
    data_mode: str = "seeded"
    provider_name: str = "seeded"
    scenario_overrides: dict = field(default_factory=dict)

    def climatology_bin(
        self, metric: str, week: int | None = None
    ) -> ClimatologyBinData | None:
        weeks = self.climatology.get(metric, {})
        return weeks.get(self.week if week is None else week)

    def climatology_values(self, metric: str, week: int | None = None) -> list[float]:
        bucket = self.climatology_bin(metric, week)
        return list(bucket.values) if bucket else []

    def current_climate(self) -> ClimateDay | None:
        return self.climate.days[-1] if self.climate.days else None


@dataclass
class IndexEvaluationResult:
    index_id: str
    score: float = 0.0
    status: str = "OK"
    available: bool = True
    data_status: str = "OK"
    confidence: float = 1.0
    components: dict = field(default_factory=dict)
    explanation: str = ""
    proof_steps: list[str] = field(default_factory=list)
    contributions: dict = field(default_factory=dict)
    agent_slot_status: str = "DETERMINISTIC_MVP"
    agent_id: str | None = None
    agent_reasoning_trace: str | None = None
    agent_weight_override: float | None = None


@runtime_checkable
class AgentHook(Protocol):
    """Reserved Phase-2 seam. Disabled by default; never required at runtime."""

    enabled: bool

    def modify(
        self, result: IndexEvaluationResult, ctx: IndexContext
    ) -> IndexEvaluationResult: ...


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def sanitize_number(value: float | int | None, digits: int = 6) -> float | None:
    """Round for display/serialization while rejecting NaN and Infinity."""
    import math

    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, digits)
