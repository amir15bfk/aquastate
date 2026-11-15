"""JSON-safe serializers for HRI results and sub-index detail."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, is_dataclass

from core.services.contracts import IndexEvaluationResult
from core.services.hri import HRISynthesisResult


def sanitize(value):
    """Recursively replace NaN/Inf and coerce dataclasses/dates to JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return sanitize(asdict(value))
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def sub_index_payload(result: IndexEvaluationResult) -> dict:
    return sanitize(
        {
            "index_id": result.index_id,
            "score": result.score,
            "status": result.status,
            "available": result.available,
            "data_status": result.data_status,
            "confidence": result.confidence,
            "components": result.components,
            "explanation": result.explanation,
            "proof_steps": result.proof_steps,
            "contributions": result.contributions,
            "agent_slot_status": result.agent_slot_status,
            "agent_id": result.agent_id,
            "agent_reasoning_trace": result.agent_reasoning_trace,
            "agent_weight_override": result.agent_weight_override,
        }
    )


def hri_payload(result: HRISynthesisResult) -> dict:
    return sanitize(
        {
            "hri": result.hri,
            "status": result.status,
            "confidence": result.confidence,
            "phi": result.phi,
            "hri_now": result.hri_now,
            "hri_proj": result.hri_proj,
            "sub_indices": result.sub_indices,
            "contributions": result.contributions,
            "components": result.components,
            "explanation": result.explanation,
            "proof_steps": result.proof_steps,
            "available": result.available,
            "data_status": result.data_status,
            "agent_slot_status": "DETERMINISTIC_MVP",
            "agent_id": None,
        }
    )


def analog_payload(match) -> dict:
    return sanitize(
        {
            "year": match.year,
            "week": match.week,
            "distance": match.distance,
            "similarity": match.similarity,
            "delta_fill_pct": match.delta_fill_90d,
            "trajectory": match.trajectory,
            "disclaimer": match.disclaimer,
        }
    )


def dam_brief_payload(dam) -> dict:
    snapshot = dam.snapshots.order_by("-as_of").first() if hasattr(dam, "snapshots") else None
    observation = dam.observations.order_by("-date").first()
    return sanitize(
        {
            "slug": dam.slug,
            "name": dam.name,
            "country": dam.country.iso3,
            "lat": dam.lat,
            "lon": dam.lon,
            "capacity_m3": dam.capacity_m3,
            "dead_storage_m3": dam.dead_storage_m3,
            "basin_area_km2": dam.basin.area_km2,
            "fill_pct": observation.fill_pct if observation else None,
            "hri": snapshot.hri if snapshot else None,
            "status": snapshot.status if snapshot else "NO_DATA",
        }
    )
