"""Observed-honest scenario overrides with strict validation and URL round-trip."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode

from pydantic import BaseModel, ConfigDict, Field

from core.services.contracts import ClimateDay, DemandDay, ForecastDay, IndexContext
from core.services.hri import HRISynthesizer, HRISynthesisResult


class ScenarioOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    rain_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    demand_multiplier: float = Field(default=1.0, ge=0.5, le=2.0)
    soil_saturation: float | None = Field(default=None, ge=0.0, le=1.0)
    storm_arrival_day: int | None = Field(default=None, ge=1, le=14)

    def is_default(self) -> bool:
        return (
            self.rain_multiplier == 1.0
            and self.demand_multiplier == 1.0
            and self.soil_saturation is None
            and self.storm_arrival_day is None
        )

    def to_query(self) -> str:
        params: dict[str, str] = {}
        if self.rain_multiplier != 1.0:
            params["rain"] = f"{self.rain_multiplier:g}"
        if self.demand_multiplier != 1.0:
            params["demand"] = f"{self.demand_multiplier:g}"
        if self.soil_saturation is not None:
            params["soil"] = f"{self.soil_saturation:g}"
        if self.storm_arrival_day is not None:
            params["storm"] = str(self.storm_arrival_day)
        return urlencode(params)

    @classmethod
    def from_query(cls, query: str) -> "ScenarioOverrides":
        parsed = parse_qs(query.lstrip("?"), keep_blank_values=True)
        values: dict = {}
        if "rain" in parsed:
            values["rain_multiplier"] = parsed["rain"][0]
        if "demand" in parsed:
            values["demand_multiplier"] = parsed["demand"][0]
        if "soil" in parsed and parsed["soil"][0] != "":
            values["soil_saturation"] = parsed["soil"][0]
        if "storm" in parsed and parsed["storm"][0] != "":
            values["storm_arrival_day"] = parsed["storm"][0]
        return cls(**values)


@dataclass
class ScenarioResult:
    observed_hri: float
    scenario_hri: float
    delta: float
    overrides: dict
    is_scenario: bool
    observed_result: HRISynthesisResult
    scenario_result: HRISynthesisResult


class ScenarioService:
    def apply(self, ctx: IndexContext, overrides: ScenarioOverrides | dict) -> ScenarioResult:
        if not isinstance(overrides, ScenarioOverrides):
            overrides = ScenarioOverrides.model_validate(overrides)
        observed = HRISynthesizer().compute(ctx)
        scenario_ctx = self.apply_overrides(ctx, overrides)
        scenario = HRISynthesizer().compute(scenario_ctx)
        return ScenarioResult(
            observed_hri=observed.hri,
            scenario_hri=scenario.hri,
            delta=scenario.hri - observed.hri,
            overrides=overrides.model_dump(),
            is_scenario=not overrides.is_default(),
            observed_result=observed,
            scenario_result=scenario,
        )

    def apply_overrides(
        self, ctx: IndexContext, overrides: ScenarioOverrides
    ) -> IndexContext:
        forecast_days = [
            replace(
                day,
                precip_mm=(day.precip_mm or 0.0) * overrides.rain_multiplier,
            )
            for day in ctx.forecast.days
        ]
        if overrides.storm_arrival_day is not None and forecast_days:
            values = [day.precip_mm or 0.0 for day in forecast_days]
            first_wet = next((i for i, value in enumerate(values) if value >= 1.0), None)
            if first_wet is not None:
                shifted = [0.0] * len(values)
                for offset, value in enumerate(values[first_wet:]):
                    target = overrides.storm_arrival_day - 1 + offset
                    if target < len(shifted):
                        shifted[target] = value
                forecast_days = [
                    replace(day, precip_mm=shifted[i])
                    for i, day in enumerate(forecast_days)
                ]

        demand_days = [
            DemandDay(
                date=day.date,
                demand_m3_day=day.demand_m3_day * overrides.demand_multiplier,
            )
            for day in ctx.demand.days
        ]

        climate_days = list(ctx.climate.days)
        if overrides.soil_saturation is not None and climate_days:
            latest = climate_days[-1]
            climate_days[-1] = replace(
                latest, soil_moisture_m3m3=overrides.soil_saturation
            )

        metadata = dict(ctx.dam.metadata or {})
        if overrides.soil_saturation is not None:
            metadata["projected_soil_moisture"] = overrides.soil_saturation
        dam = replace(ctx.dam, metadata=metadata)
        return replace(
            ctx,
            dam=dam,
            forecast=replace(ctx.forecast, days=forecast_days),
            demand=replace(ctx.demand, days=demand_days),
            climate=replace(ctx.climate, days=climate_days),
            scenario_overrides={
                **ctx.scenario_overrides,
                **overrides.model_dump(exclude_none=True),
            },
        )
