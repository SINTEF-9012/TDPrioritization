from prioritizer.pipelines.agentic.agent_state import State

import re
from typing import Tuple, List

EXPECTED_HEADER = "Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization"
SEVERITY_ORDER = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

def normalize_llm_output(text: str) -> str:
    if not text:
        return text

    text = text.strip()

    for token in ('```csv', '```text', '```', '"', "'"):
        if text.startswith(token): text = text[len(token):].strip()
        if text.endswith(token): text = text[:-len(token)].strip()

    text = re.sub(r'^[^0-9A-Za-z]+', '', text)
    text = re.sub(r'[^0-9A-Za-z]+$', '', text)

    return text


def _parse_table(text: str) -> Tuple[List[str], List[List[str]]]:
    """
    Returns (lines, rows) where rows are split by '|' and stripped.
    Ignores empty lines.
    """
    text = normalize_llm_output(text)

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return [], []

    lines = [ln for ln in lines if ln not in ("```", "```text", "```csv")]

    rows = []
    for ln in lines:
        # Skip separator lines if it tries markdown tables
        if re.fullmatch(r"[-|:\s]+", ln):
            continue
        parts = [p.strip() for p in ln.split("|")]
        rows.append(parts)

    return lines, rows

def review_output_node(state: State) -> State:
    smells = state.get("smells") or []
    expected_ids = [str(s.get("index")) for s in smells]
    expected_id_set = set(expected_ids)
    n = len(expected_ids)

    text = (state.get("output_text") or "").strip()
    errors: dict[str, str] = {}

    if not text:
        errors["Empty output"] = "Empty output_text."
        return {**state, "validation_errors": errors, "is_valid": False}

    _, rows = _parse_table(text)
    if not rows:
        errors["Empty rows"] = "Could not parse any rows from output."
        return {**state, "validation_errors": errors, "is_valid": False}

    header = "|".join(rows[0]).strip()
    if header != EXPECTED_HEADER:
        errors["Invalid header format"] = f"The table header is incorrect. The first row MUST be exactly: '{EXPECTED_HEADER}'. Do not add, remove, or rename columns."


    data_rows = rows[1:]
    if len(data_rows) != n:
        errors["Incorrect number of rows"] = f"The output must contain exactly one data row per smell. Expected {n} rows (excluding the header), but found {len(data_rows)}."

    seen_ranks = []
    seen_ids = []
    severities_in_rank_order = []

    for i, r in enumerate(data_rows, start=1):
        if len(r) != 7:
            errors["Invalid column count"] = f"Row {i} does not have the required 7 columns. "\
            "Each row MUST follow the format: "\
            "Rank|Id|Name of Smell|Name|File|Severity|Reason for Prioritization."

            continue

        rank_s, id_s, smell_name, name, file_path, severity, reason = r

        if not rank_s.isdigit():
            errors["Invalid rank value"] = f"Row {i} has an invalid Rank value ('{rank_s}'). "\
            "Rank MUST be a positive integer starting at 1."
        else:
            seen_ranks.append(int(rank_s))

        if not id_s:
            errors["Non-numerical id"] = f"Row {i}: Missing Id."
        else:
            seen_ids.append(id_s)

        severity_u = (severity or "").strip().upper()
        if severity_u not in SEVERITY_ORDER:
            errors["Invalid severity value"] = f"Row {i} has an invalid Severity ('{severity}'). "\
            "Severity MUST be one of: HIGH, MEDIUM, LOW."
        else:
            severities_in_rank_order.append(severity_u)

        if not reason or len(reason) < 5:
            errors["Lacking description"] = f"Row {i}: Reason is too short or missing."

    
    if seen_ranks:
        if sorted(seen_ranks) != list(range(1, n + 1)):
            errors["Invalid rank ordering"] = f"Ranks must be sequential integers from 1 to {n} with no gaps or duplicates. "\
            f"Detected ranks: {sorted(seen_ranks)}."

    if seen_ids:
        seen_id_set = set(seen_ids)
        missing = sorted(expected_id_set - seen_id_set)
        extra = sorted(seen_id_set - expected_id_set)

        
        dupes = sorted({x for x in seen_ids if seen_ids.count(x) > 1})
        if missing:
            errors["Missing smell identifiers"] = f"The output does not include all required smell Ids. "\
            f"Missing Ids: {missing}. Each smell MUST appear exactly once."

        if extra:
            errors["Unexpected smell identifiers"] = f"The output contains Ids that were not part of the input: {extra}. "\
            "Only the provided smell Ids may be used."
            
        if dupes:
            errors["Duplicate smell identifiers"] = f"The following smell Ids appear more than once: {dupes}. "\
            "Each smell Id MUST appear exactly once."

    # Severity constraint: LOW cannot appear above any MEDIUM/HIGH
    if severities_in_rank_order:
        seen_low = False
        for idx, sev in enumerate(severities_in_rank_order, start=1):
            if sev == "LOW":
                seen_low = True
            elif seen_low and sev in ("MEDIUM", "HIGH"):
                errors["Severity ordering violation"] = f"A {sev}-severity smell appears at rank {idx} after a LOW-severity smell. "\
                "LOW severity smells MUST NOT be ranked above MEDIUM or HIGH severity smells."
                break

    is_valid = len(errors) == 0
    return {**state, "validation_errors": errors, "is_valid": is_valid}
