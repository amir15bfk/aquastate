"""Compute, explain, and persist one dam's HRI snapshot."""
from __future__ import annotations

import datetime as dt

from core.models import Dam, IndexSnapshot
from core.services.analog import AnalogEngine, AnalogMatch
from core.services.contracts import IndexContext, IndexEvaluationResult
from core.services.exceptions import MissingDataError
from core.services.hri import HRISynthesizer, HRISynthesisResult
from core.services.indices.registry import INDEX_REGISTRY
from core.services.providers.registry import get_provider
from core.services.scenario import ScenarioOverrides, ScenarioService
from core.services.serializers import (
    analog_payload,
    dam_brief_payload,
    hri_payload,
    sub_index_payload,
)


def latest_snapshot(dam: Dam) -> IndexSnapshot | None:
    return dam.snapshots.order_by("-as_of", "-id").first()


def _as_date(value) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    return dt.date.today()


def compute_current_results(ctx: IndexContext) -> dict[str, IndexEvaluationResult]:
    current: dict[str, IndexEvaluationResult] = {}
    for index, index_provider in INDEX_REGISTRY.items():
        try:
            current[index] = index_provider.compute(ctx)
        except Exception:
            current[index] = IndexEvaluationResult(
                index_id=index,
                available=False,
                status="NO_DATA",
                data_status="NO_DATA",
                confidence=0.0,
            )
    return current


def build_state_payload(
    dam: Dam,
    ctx: IndexContext,
    outcome: HRISynthesisResult,
    current: dict[str, IndexEvaluationResult],
    analogs: list[AnalogMatch] | None = None,
    *,
    snapshot_id: int | None = None,
    is_scenario: bool = False,
    observed_state: dict | None = None,
    overrides: dict | None = None,
) -> dict:
    payload = {
        **hri_payload(outcome),
        "dam": dam_brief_payload(dam),
        "as_of": ctx.as_of.isoformat() if ctx.as_of else None,
        "week": ctx.week,
        "data_mode": ctx.data_mode,
        "provider": ctx.provider_name,
        "sub_indices": {key: sub_index_payload(value) for key, value in current.items()},
        "analogs": [analog_payload(match) for match in (analogs or [])],
        "snapshot_id": snapshot_id,
        "is_scenario": is_scenario,
        "observed": observed_state,
        "overrides": overrides or {},
        "disclaimer": (
            "Deterministic MVP data calibrated to NASA Earth observations. "
            "Not for operational decisions."
        ),
    }
    return payload


def compute_dam_state(dam_slug: str, as_of=None, provider=None) -> dict:
    dam = Dam.objects.select_related("basin", "country").filter(slug=dam_slug).first()
    if dam is None:
        raise MissingDataError(f"unknown dam: {dam_slug}")
    provider = provider or get_provider()
    as_of = _as_date(as_of) if as_of is not None else None
    ctx = provider.build_context(dam_slug, as_of)
    current = compute_current_results(ctx)
    outcome = HRISynthesizer().compute(ctx, current)
    try:
        analogs = AnalogEngine.find_analogs(
            ctx, AnalogEngine.current_features(ctx), top_n=3
        )
    except Exception:
        analogs = []

    snapshot, _ = IndexSnapshot.objects.update_or_create(
        dam=dam,
        as_of=ctx.as_of,
        data_mode=ctx.data_mode,
        defaults={
            "week": ctx.week,
            "hri": outcome.hri if outcome.available else None,
            "status": outcome.status,
            "confidence": outcome.confidence,
            "phi": outcome.phi,
            "sub_indices": {key: value.score for key, value in current.items()},
            "contributions": outcome.contributions,
            "components": outcome.components,
            "explanation": outcome.explanation,
            "analog_years": [match.year for match in analogs],
        },
    )
    return build_state_payload(
        dam, ctx, outcome, current, analogs, snapshot_id=snapshot.id
    )


def compute_scenario_state(
    dam_slug: str,
    overrides: ScenarioOverrides,
    as_of=None,
    provider=None,
) -> tuple[dict, dict, float]:
    """Return (observed_payload, scenario_payload, delta) without persisting."""
    dam = Dam.objects.select_related("basin", "country").filter(slug=dam_slug).first()
    if dam is None:
        raise MissingDataError(f"unknown dam: {dam_slug}")
    provider = provider or get_provider()
    as_of = _as_date(as_of) if as_of is not None else None
    ctx = provider.build_context(dam_slug, as_of)
    observed_current = compute_current_results(ctx)
    observed_outcome = HRISynthesizer().compute(ctx, observed_current)
    try:
        analogs = AnalogEngine.find_analogs(
            ctx, AnalogEngine.current_features(ctx), top_n=3
        )
    except Exception:
        analogs = []
    observed_payload = build_state_payload(
        dam, ctx, observed_outcome, observed_current, analogs
    )

    scenario_ctx = ScenarioService().apply_overrides(ctx, overrides)
    scenario_current = compute_current_results(scenario_ctx)
    scenario_outcome = HRISynthesizer().compute(scenario_ctx, scenario_current)
    scenario_payload = build_state_payload(
        dam,
        scenario_ctx,
        scenario_outcome,
        scenario_current,
        analogs,
        is_scenario=not overrides.is_default(),
        observed_state=observed_payload,
        overrides=overrides.model_dump(),
    )
    return (
        observed_payload,
        scenario_payload,
        scenario_payload["hri"] - observed_payload["hri"],
    )
