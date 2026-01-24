from langchain_core.messages import SystemMessage, HumanMessage

from prioritizer.pipelines.agentic.agent_state import State

REPAIR_SYSTEM = """\
You are a strict output repair assistant.

Return ONLY a corrected pipe-separated table.
- The first row MUST be the exact header.
- Then exactly one row per smell Id.
- No extra text, no code fences, no quotes.
"""

EXPECTED_HEADER = "Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization"


def repair_output_node(state: State) -> State:
    attempts = state.get("repair_attempts", 0)
    max_attempts = state.get("max_repair_attempts", 2)

    # If already exceeded, do nothing (review routing will stop)
    if attempts >= max_attempts:
        return state

    smells = state.get("smells") or []
    expected_ids = [str(s.get("index")) for s in smells]

    errors = state.get("validation_errors") or {}
    prior = state.get("output_text") or ""

    llm = state.get("llm")

    user_msg = f"""\
Fix the output to satisfy all constraints.

Required header (must be first row, exact):
{EXPECTED_HEADER}

Expected smell Ids (each exactly once):
{expected_ids}

Validation errors (fix ALL):
{errors}

Prior output to repair:
{prior}
"""

    resp = llm.invoke([
        SystemMessage(content=REPAIR_SYSTEM),
        HumanMessage(content=user_msg),
    ])

    fixed = (resp.content or "").strip()
    return {
        **state,
        "output_text": fixed,
        "repair_attempts": attempts + 1,
    }
