from __future__ import annotations

from django.test import SimpleTestCase, TestCase, override_settings

from hydro.ai import (
    AgentSuggestion,
    ensure_slots,
    reserved_slots_payload,
    run_ai_layer,
    validate_suggestion,
)
from hydro.models import AIAgentSlot


def sample_result(value: float = 42.0) -> dict:
    return {
        "meta": {"version": "WRI-1.0"},
        "index": {"value": value, "base_value": value, "status": "stressed"},
        "pillars": [{"key": "buffer", "value": 20.0}],
        "horizon": {"state": "tight", "verdict": "Tight before rain"},
        "narrative": {"summary": "Fixture", "headline": "Fixture"},
        "ai_trace": {"enabled": False, "contributions": [], "slots": []},
    }


class AIContractTests(TestCase):
    def setUp(self):
        ensure_slots()

    def test_five_reserved_slots_disabled(self):
        slots = AIAgentSlot.objects.all()
        self.assertEqual(slots.count(), 5)
        self.assertTrue(all(not slot.enabled for slot in slots))
        payload = reserved_slots_payload()
        self.assertFalse(payload["policy"]["enabled"])
        self.assertFalse(payload["policy"]["allow_subindex_adjustment"])
        self.assertEqual(len(payload["slots"]), 5)

    def test_disabled_layer_does_not_change_core(self):
        result = sample_result(42.0)
        layered = run_ai_layer(result)
        self.assertEqual(layered["index"]["value"], 42.0)
        self.assertFalse(layered["ai_trace"]["enabled"])
        self.assertEqual(layered["ai_trace"]["contributions"], [])
        self.assertEqual(len(layered["ai_trace"]["slots"]), 5)

    def test_oversized_delta_is_rejected(self):
        suggestion = AgentSuggestion(
            slot="confidence-calibration-agent",
            stage="confidence_calibration",
            rationale="A sufficiently long rationale for audit.",
            confidence=0.7,
            proposed_delta=99,
        )
        errors = validate_suggestion(suggestion, max_delta=5.0)
        self.assertTrue(any("exceeds max" in error for error in errors))

    def test_payload_cannot_mutate_core(self):
        suggestion = AgentSuggestion(
            slot="horizon-narrative-agent",
            stage="horizon_narrative",
            rationale="A sufficiently long rationale for audit.",
            confidence=0.7,
            payload={"index": 100, "verdict": "OK"},
        )
        errors = validate_suggestion(suggestion, max_delta=5.0)
        self.assertTrue(any("core keys" in error for error in errors))

    def test_short_rationale_is_rejected(self):
        suggestion = AgentSuggestion(
            slot="horizon-narrative-agent",
            stage="horizon_narrative",
            rationale="ok",
            confidence=0.7,
        )
        errors = validate_suggestion(suggestion, max_delta=5.0)
        self.assertTrue(any("rationale" in error for error in errors))

    @override_settings(AI_AGENTS_ENABLED=True, AI_ALLOW_SUBINDEX_ADJUSTMENT=True)
    def test_enabled_slot_is_bounded_and_core_unchanged(self):
        slot = AIAgentSlot.objects.get(name="confidence-calibration-agent")
        slot.enabled = True
        slot.max_delta = 5.0
        slot.save()
        result = sample_result(42.0)
        layered = run_ai_layer(
            result,
            suggestions=[
                AgentSuggestion(
                    slot=slot.name,
                    stage=slot.stage,
                    rationale="Independent cross-check found no contradiction.",
                    confidence=0.8,
                    payload={"note": "advisory only"},
                    proposed_delta=99,
                )
            ],
        )
        self.assertEqual(layered["index"]["value"], 42.0)
        self.assertEqual(layered["index"]["base_value"], 42.0)
        self.assertEqual(layered["ai_trace"]["contributions"][0]["applied"], False)
        self.assertTrue(layered["ai_trace"]["contributions"][0]["core_unchanged"])
        self.assertTrue(layered["ai_trace"]["contributions"][0]["errors"])

    @override_settings(AI_AGENTS_ENABLED=True, AI_ALLOW_SUBINDEX_ADJUSTMENT=True)
    def test_enabled_slot_within_bounds_is_audited(self):
        slot = AIAgentSlot.objects.get(name="confidence-calibration-agent")
        slot.enabled = True
        slot.max_delta = 5.0
        slot.save()
        layered = run_ai_layer(
            sample_result(42.0),
            suggestions=[
                AgentSuggestion(
                    slot=slot.name,
                    stage=slot.stage,
                    rationale="Independent cross-check found no contradiction.",
                    confidence=0.8,
                    payload={"note": "advisory only"},
                    proposed_delta=3.0,
                )
            ],
        )
        contribution = layered["ai_trace"]["contributions"][0]
        self.assertTrue(contribution["applied"])
        self.assertEqual(contribution["delta"], 3.0)
        self.assertTrue(contribution["core_unchanged"])
        self.assertEqual(layered["index"]["value"], 42.0)
