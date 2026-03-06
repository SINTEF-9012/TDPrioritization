from typing import Any, Dict, List, Optional, Tuple

from .static_metrics import analyze_file
from .pylint_analysis import get_pylint_metadata, get_pylinter_singleton

from pylint.lint import PyLinter
from pylint.reporters.json_reporter import JSONReporter


def _bucket(value: float, low: float, high: float) -> str:
    if value >= high:
        return "HIGH"
    if value >= low:
        return "MED"
    return "LOW"

def _pick_top_pylint_messages(pylint_msgs: List[Dict[str, Any]], k: int = 3) -> List[str]:
    """
    Prefer higher-severity / more informative messages.
    This assumes common pylint keys; degrade gracefully if missing.
    """
    # Pylint msg categories are not strict severities, but errors/warnings tend to matter more than conventions.
    category_weight = {
        "fatal": 5,
        "error": 4,
        "warning": 3,
        "refactor": 2,
        "convention": 1,
        "info": 0,
    }

    def score(msg: Dict[str, Any]) -> Tuple[int, int]:
        cat = str(msg.get("category", "")).lower()
        w = category_weight.get(cat, 0)
        # Prefer messages with a symbol/message-id if present (often more specific)
        has_symbol = 1 if msg.get("symbol") or msg.get("message-id") else 0
        return (w, has_symbol)

    msgs_sorted = sorted(pylint_msgs, key=score, reverse=True)

    picked: List[str] = []
    for msg in msgs_sorted[:k]:
        line = msg.get("line", "?")
        symbol = msg.get("symbol") or msg.get("message-id") or ""
        message = msg.get("message", "")
        symbol_part = f"{symbol}: " if symbol else ""
        picked.append(f"L{line} {symbol_part}{message}".strip())
    return picked

def format_llm_file_context_concise(
    meta: Dict[str, Any],
    pylint_summary: Dict[str, int],
    pylint_msgs: List[Dict[str, Any]],
    technical_risk_score: float,
) -> str:
    loc = int(meta.get("loc", 0) or 0)
    avg_cc = float(meta.get("avg_cc", 0.0) or 0.0)
    max_cc = int(meta.get("max_cc", 0) or 0)
    mi = float(meta.get("maintainability_index", 0.0) or 0.0)
    num_classes = int(meta.get("num_classes", 0) or 0)
    num_funcs = int(meta.get("num_functions", 0) or 0)

    conv = int(pylint_summary.get("convention", 0) or 0)
    refac = int(pylint_summary.get("refactor", 0) or 0)
    warn = int(pylint_summary.get("warning", 0) or 0)
    err = int(pylint_summary.get("error", 0) or 0)
    fatal = int(pylint_summary.get("fatal", 0) or 0)

    # Flags (keep short, machine-ish)
    flags: List[str] = []
    if avg_cc >= 10: flags.append("HIGH_CC")
    elif avg_cc >= 7: flags.append("MED_CC")

    if mi < 65: flags.append("LOW_MI")
    elif mi < 75: flags.append("MED_MI")

    if num_classes > 5: flags.append("MANY_CLASSES")
    if warn + err + fatal >= 5: flags.append("MANY_WARN_ERR")
    if refac >= 3: flags.append("MANY_REFACTOR")

    cc_level = _bucket(avg_cc, low=7, high=10)
    mi_level = "LOW" if mi < 65 else ("MED" if mi < 75 else "HIGH")
    lint_level = "HIGH" if (fatal + err) > 0 else ("MED" if warn > 0 or refac > 0 else "LOW")

    top_issues = _pick_top_pylint_messages(pylint_msgs, k=3)
    top_issues_text = "; ".join(top_issues) if top_issues else "none"

    file_name = meta.get("file", "<unknown>")

    return (
        f"FILE={file_name}\n"
        f"METRICS: LOC={loc}, CC(avg/max)={avg_cc:.1f}/{max_cc}, MI={mi:.1f}, classes={num_classes}, funcs={num_funcs}\n"
        f"PYLINT: F={fatal}, E={err}, W={warn}, R={refac}, C={conv} | levels: CC={cc_level}, MI={mi_level}, LINT={lint_level}\n"
        f"RISK_SCORE={technical_risk_score:.2f} | FLAGS={','.join(flags) if flags else 'none'} | TOP_ISSUES={top_issues_text}"
    )

def build_llm_analysis_report(file_path: str, reporter: Optional[JSONReporter] = None, linter: Optional[PyLinter] = None,
) -> Dict[str, Any]:
    """
    Combine Radon, AST, and Pylint results into an LLM-friendly analysis summary.

    This is the main entry point you should call from tools/agents.

    Args:
        file_path:
            Path to the Python file to analyze.
        reporter, linter:
            Optional pre-instantiated Pylint objects. If not provided, a cached
            singleton pair will be used.

    Returns:
        dict with:
            - 'text': human-readable summary string
            - 'meta': structured numeric metrics, including a 'technical_risk_score'
    """
    if not file_path:
        return {"text": "An invalid filepath was provided.", "meta": {}}

    meta = analyze_file(file_path)

    if linter is None or reporter is None:
        linter, reporter = get_pylinter_singleton()

    pylint_summary, pylint_msgs = get_pylint_metadata(file_path, reporter, linter)

    pylint_examples: List[str] = []
    for msg in pylint_msgs[:5]:
        pylint_examples.append(f"Line {msg['line']}: {msg['message']}")

    pylint_summary_text = (
        "\n".join(pylint_examples) if pylint_examples else "No specific linting issues found."
    )

    technical_risk_score = (
        meta["avg_cc"] / 10
        + (100 - meta["maintainability_index"]) / 20
        + pylint_summary["refactor"] * 0.5
        + pylint_summary["warning"] * 0.5
    )

    summary_text = format_llm_file_context_concise(meta, pylint_summary, pylint_msgs, technical_risk_score)

    return {
        "text": summary_text,
        "meta": {
            "file": meta["file"],
            "loc": meta["loc"],
            "avg_cc": meta["avg_cc"],
            "maintainability_index": meta["maintainability_index"],
            "num_classes": meta["num_classes"],
            "num_functions": meta["num_functions"],
            "pylint_convention": pylint_summary["convention"],
            "pylint_refactor": pylint_summary["refactor"],
            "pylint_warning": pylint_summary["warning"],
            "pylint_error": pylint_summary["error"],
            "technical_risk_score": technical_risk_score,
        },
    }
