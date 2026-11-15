from __future__ import annotations

import copy

from django.conf import settings

from hydro.ai.contracts import AgentSuggestion, POLICY, validate_suggestion
from hydro.ai.registry import effective_policy, enabled_slots, slots_payload


def run_ai_layer(result: dict, *, suggestions: list[AgentSuggestion] | None = None) -> dict:
    """Attach the reserved slots and audit suggestions without touching core math.

    The function is a no-op on the deterministic core. Even when a caller
    supplies suggestions, the most they can produce is a separate advisory
    trace and a confidence note; the index, pillars, formulas and horizon
    verdict are copied unchanged.
    """
    output = copy.deepcopy(result)
    policy = effective_policy()
    trace = output.setdefault("ai_trace", {})
    trace["enabled"] = policy["enabled"]
    trace["policy"] = policy
    trace["slots"] = slots_payload()
    trace.setdefault("contributions", [])

    if not settings.AI_AGENTS_ENABLED or not suggestions:
        trace["status"] = "disabled" if not settings.AI_AGENTS_ENABLED else "idle"
        return output

    active = enabled_slots()
    allowed_names = {slot.name for slot in active}
    max_delta = min(
        [slot.max_delta for slot in active if slot.max_delta > 0] or [0.0]
    )
    for suggestion in suggestions:
        errors = validate_suggestion(suggestion, max_delta=max_delta)
        if suggestion.slot not in allowed_names:
            errors.append("slot is not enabled")
        applied = False
        delta = 0.0
        if not errors and policy["allow_subindex_adjustment"] and suggestion.proposed_delta:
            # No core mutation even here: the delta is an explicit advisory
            # number, and is never added to the current-state score.
            applied = True
            delta = max(-max_delta, min(max_delta, suggestion.proposed_delta))
        trace["contributions"].append(
            {
                "slot": suggestion.slot,
                "stage": suggestion.stage,
                "rationale": suggestion.rationale,
                "confidence": suggestion.confidence,
                "proposed": suggestion.payload,
                "applied": applied,
                "delta": delta,
                "errors": errors,
                "core_unchanged": True,
            }
        )
    trace["status"] = "audited"
    return output


def reserved_slots_payload() -> dict:
    return {
        "policy": effective_policy(),
        "slots": slots_payload(),
        "contract": "Agent suggestions are advisory only. Core formula, inputs, pillars, horizon verdict and score are immutable by contract.",
        "policy_reference": POLICY,
    }
