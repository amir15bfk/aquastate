"""AI-ready boundary: contracts, slots and a non-mutating audit pipeline.

The MVP has no active agents. These contracts reserve the places an agent may
contribute later without allowing it to rewrite the deterministic index.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from django.conf import settings


class AgentStage(str, Enum):
    POST_SUBINDEX_ADVICE = "post_subindex_advice"
    HORIZON_NARRATIVE = "horizon_narrative"
    CONFIDENCE_CALIBRATION = "confidence_calibration"
    ANOMALY_EXPLANATION = "anomaly_explanation"


BUILTIN_SLOTS = [
    {
        "name": "reservoir-context-agent",
        "stage": AgentStage.POST_SUBINDEX_ADVICE.value,
        "description": "Reserved: explains anomalous reservoir storage against local operations context. Advisory only.",
        "max_delta": 0.0,
        "weight": 0.0,
        "contract_version": "1.0",
        "metadata": {"mutates_core": False, "status": "reserved"},
    },
    {
        "name": "horizon-narrative-agent",
        "stage": AgentStage.HORIZON_NARRATIVE.value,
        "description": "Reserved: turns the deterministic horizon simulation into a plain-language briefing.",
        "max_delta": 0.0,
        "weight": 0.0,
        "contract_version": "1.0",
        "metadata": {"mutates_core": False, "status": "reserved"},
    },
    {
        "name": "confidence-calibration-agent",
        "stage": AgentStage.CONFIDENCE_CALIBRATION.value,
        "description": "Reserved: proposes a separate confidence adjustment from source agreement. Never changes the score.",
        "max_delta": 5.0,
        "weight": 1.0,
        "contract_version": "1.0",
        "metadata": {"mutates_core": False, "status": "reserved"},
    },
    {
        "name": "anomaly-explanation-agent",
        "stage": AgentStage.ANOMALY_EXPLANATION.value,
        "description": "Reserved: flags an unexplained jump or divergence for analyst review.",
        "max_delta": 0.0,
        "weight": 0.0,
        "contract_version": "1.0",
        "metadata": {"mutates_core": False, "status": "reserved"},
    },
    {
        "name": "scenario-critic-agent",
        "stage": AgentStage.POST_SUBINDEX_ADVICE.value,
        "description": "Reserved: argues against the current scenario and lists missing evidence. Advisory only.",
        "max_delta": 0.0,
        "weight": 0.0,
        "contract_version": "1.0",
        "metadata": {"mutates_core": False, "status": "reserved"},
    },
]

FORBIDDEN_PAYLOAD_KEYS = {
    "pillars",
    "index",
    "base_index",
    "final_index",
    "formula",
    "weights",
    "horizon",
    "verdict",
    "inputs",
    "reservoirs",
}


@dataclass(frozen=True)
class AgentContext:
    country_iso2: str
    result: dict
    scenario: dict
    as_of: str


@dataclass(frozen=True)
class AgentSuggestion:
    slot: str
    stage: str
    rationale: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
    proposed_delta: float = 0.0


def validate_suggestion(suggestion: AgentSuggestion, *, max_delta: float) -> list[str]:
    errors = []
    if suggestion.stage not in {stage.value for stage in AgentStage}:
        errors.append(f"unknown stage: {suggestion.stage}")
    if not 0.0 <= suggestion.confidence <= 1.0:
        errors.append("confidence must be between 0 and 1")
    if abs(suggestion.proposed_delta) > max_delta + 1e-9:
        errors.append(f"proposed delta {suggestion.proposed_delta} exceeds max {max_delta}")
    forbidden = FORBIDDEN_PAYLOAD_KEYS.intersection(suggestion.payload)
    if forbidden:
        errors.append(f"payload attempts to mutate core keys: {sorted(forbidden)}")
    if len(suggestion.rationale.strip()) < 8:
        errors.append("rationale is too short to audit")
    return errors


POLICY = {
    "allow_subindex_adjustment": settings.AI_ALLOW_SUBINDEX_ADJUSTMENT,
    "max_adjustment": settings.AI_MAX_ADJUSTMENT,
    "core_formula_mutable": False,
    "requires_rationale": True,
    "requires_confidence": True,
    "audit_all_suggestions": True,
    "default_behavior": "advisory-only",
}
