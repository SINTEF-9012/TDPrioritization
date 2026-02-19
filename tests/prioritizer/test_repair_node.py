import pytest
from pathlib import Path

from prioritizer.pipelines.agentic.repair_node import repair_output_node
from prioritizer.pipelines.agentic.reviewing_output import EXPECTED_HEADER

from mocking_objects.fake_llm import FakeLLM

def make_state_for_repair(llm, smells, output_text, errors, attempts=0, max_attempts=2):
    return {
        "smell_types": [],
        "smells": smells,
        "repo": None,
        "use_git": False,
        "use_pylint": False,
        "use_code": False,
        "llm": llm,
        "output_text": output_text,
        "out_dir": Path("experiments/mock"),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "validation_errors": errors,
        "is_valid": False,
        "repair_attempts": attempts,
        "max_repair_attempts": max_attempts,
    }

def test_repair_node_increments_attempts_and_replaces_output():
    smells = [{"index": "14"}, {"index": "20"}]
    errors = {"Invalid header format": "Header is wrong."}
    prior = "BAD OUTPUT"

    fixed_output = (
        f"{EXPECTED_HEADER}\n"
        "1|14|Feature Envy|a|f.py|HIGH|Reason\n"
        "2|20|Feature Envy|b|g.py|HIGH|Reason\n"
    )

    llm = FakeLLM(response_text=fixed_output)
    state = make_state_for_repair(llm, smells, prior, errors)

    out = repair_output_node(state)

    assert out["repair_attempts"] == 1
    assert out["output_text"].startswith(EXPECTED_HEADER)

    assert llm.last_messages is not None
    user_msg = llm.last_messages[-1].content  
    assert EXPECTED_HEADER in user_msg
    assert "['14', '20']" in user_msg
    assert "Invalid header format" in user_msg
    assert "BAD OUTPUT" in user_msg
