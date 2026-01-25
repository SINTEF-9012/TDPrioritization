import pytest
from typing import List, Dict, Any

from prioritizer.pipelines.agentic.reviewing_output import review_output_node

from mocking_objects.mock_states import (
    make_mock_state, 
    CORRECT_OUTPUT, 
    MOCK_SMELLS, 
    FAULTY_NO_HEADER, 
    FAULTY_DUPLICATE_ID, 
    FAULTY_SEVERITY_ORDER, 
    FAULTY_RANKS, 
    FAULTY_EXTRA_TEXT
)

def test_correct_output_is_valid():
    state = make_mock_state(CORRECT_OUTPUT, MOCK_SMELLS)
    out = review_output_node(state)

    assert out["is_valid"] is True
    assert out["validation_errors"] == {}

def _assert_has_error_keys(out: Dict[str, Any], expected_keys: List[str]):
    assert out["is_valid"] is False
    assert isinstance(out["validation_errors"], dict)

    for k in expected_keys:
        assert k in out["validation_errors"], f"Expected error key '{k}' not found. Keys={list(out['validation_errors'].keys())}"

@pytest.mark.parametrize(
    "output_text, expected_keys",
    [
        (FAULTY_NO_HEADER, ["Invalid header format"]),

        (FAULTY_DUPLICATE_ID, ["Incorrect number of rows", "Duplicate smell identifiers", "Missing smell identifiers"]),

        (FAULTY_SEVERITY_ORDER, ["Severity ordering violation"]),

        (FAULTY_RANKS, ["Invalid rank ordering"]),

        (FAULTY_EXTRA_TEXT, ["Invalid header format"]),
    ],
)
def test_faulty_outputs_detected(output_text, expected_keys):
    state = make_mock_state(output_text, MOCK_SMELLS)
    out = review_output_node(state)
    _assert_has_error_keys(out, expected_keys)