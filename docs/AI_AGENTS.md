# AI Agent Boundary

**Status:** five slots reserved, all disabled (`AI_AGENTS_ENABLED = False`). No network model is called in the MVP.

The deterministic index is the source of truth. AI is a future **advisory** layer only; it cannot rewrite the score,
the pillars, the inputs, the formulas, the horizon simulation or the verdict.

---

## Stages and slots

| Slot | Stage | Reserved for | Max delta | Default |
|---|---|---|---|---|
| `reservoir-context-agent` | `post_subindex_advice` | Operations context around an anomalous reservoir | 0.0 | off |
| `horizon-narrative-agent` | `horizon_narrative` | Plain-language briefing of the deterministic horizon | 0.0 | off |
| `confidence-calibration-agent` | `confidence_calibration` | Separate confidence adjustment from source agreement | 5.0 | off |
| `anomaly-explanation-agent` | `anomaly_explanation` | Flag an unexplained jump for analyst review | 0.0 | off |
| `scenario-critic-agent` | `post_subindex_advice` | Argue against the scenario; list missing evidence | 0.0 | off |

Slots are seeded by `ensure_slots()` into `AIAgentSlot` and exposed at `/api/ai/slots/`.

---

## Contract

```python
from hydro.ai import AgentSuggestion, run_ai_layer

suggestion = AgentSuggestion(
    slot="horizon-narrative-agent",
    stage="horizon_narrative",
    rationale="Explain the storm gap without changing the math.",
    confidence=0.82,
    payload={"text": "The reserve is covered through Thursday."},
    proposed_delta=0.0,
)
result = run_ai_layer(result, suggestions=[suggestion])
```

Validation rejects:

- an unknown stage or a slot that is not enabled;
- confidence outside 0–1;
- `abs(proposed_delta) > max_delta` (rejected, never silently clamped);
- a payload containing any core key: `index`, `pillars`, `formula`, `weights`, `horizon`, `verdict`, `inputs`,
  `reservoirs`, `base_index`, `final_index`;
- a rationale shorter than 8 characters.

Every suggestion is written to `ai_trace.contributions` with `applied`, `delta`, `errors` and `core_unchanged: true`.
The default result is identical with AI on or off; only `ai_trace` changes.

---

## Policy

```json
{
  "enabled": false,
  "allow_subindex_adjustment": false,
  "max_adjustment": 5.0,
  "core_formula_mutable": false,
  "default_behavior": "advisory-only"
}
```

Even with `AI_ALLOW_SUBINDEX_ADJUSTMENT = True`, an enabled slot may only emit a separate advisory delta. It cannot
change `index.value`, `index.base_value`, the pillars or the horizon verdict. The dashboard's “AI layer” note states
this in plain language.

---

## Adding an agent later

1. Implement a client that returns an `AgentSuggestion`; keep the call **outside** `compute_index`.
2. Register a slot in `hydro/ai/contracts.py` (`BUILTIN_SLOTS`).
3. Require a rationale and confidence; validate before persistence.
4. Persist the suggestion and its audit row; never write it into the deterministic core.
5. Add a test that the core result is byte-identical after the agent runs, excluding `ai_trace` and timestamps.
6. If the agent ever proposes a score effect, put it behind an explicit human approval and a separate “advisory” number.
7. Keep the model endpoint and key out of the repository; use environment variables.

---

## Audit endpoints

- `GET /api/ai/slots/` — slots, policy, contract text.
- `GET /api/country/<ISO2>/audit/` — full pillar/horizon audit plus `ai_trace`.
- `GET /api/country/<ISO2>/` — the same trace inside the dashboard payload.

The MVP never sends country data to an external model.
