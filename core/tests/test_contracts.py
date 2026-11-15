from core.services.contracts import IndexEvaluationResult


def test_index_evaluation_result_defaults_are_deterministic():
    result = IndexEvaluationResult(index_id="SSI")
    assert result.available is True
    assert result.data_status == "OK"
    assert result.agent_slot_status == "DETERMINISTIC_MVP"
    assert result.agent_id is None
    assert result.agent_reasoning_trace is None
    assert result.agent_weight_override is None
    assert result.components == {}
    assert result.proof_steps == []
