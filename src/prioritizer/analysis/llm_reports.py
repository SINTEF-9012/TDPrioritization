from typing import Any, Dict, List, Optional

from .static_metrics import analyze_file
from .pylint_analysis import get_pylint_metadata, get_pylinter_singleton

from pylint.lint import PyLinter
from pylint.reporters.json_reporter import JSONReporter

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

    # Interpret metrics
    interpretations: List[str] = []

    if meta["avg_cc"] >= 10:
        interpretations.append("High cyclomatic complexity indicates dense logical branching.")
    elif meta["avg_cc"] >= 7:
        interpretations.append("Moderate complexity; may still benefit from refactoring.")

    if meta["maintainability_index"] < 65:
        interpretations.append("Low maintainability index suggests high technical debt risk.")
    elif meta["maintainability_index"] < 75:
        interpretations.append("Slightly reduced maintainability; monitor this file over time.")

    if meta["loc"] > 250:
        interpretations.append("The file size is large, which may indicate a 'Large File' smell.")
    if meta["num_classes"] > 5:
        interpretations.append("Multiple class definitions may indicate over-responsibility.")
    if pylint_summary["refactor"] > 0 or pylint_summary["warning"] > 0:
        interpretations.append("Refactor or warning messages suggest design or correctness issues.")
    if pylint_summary["convention"] > 10:
        interpretations.append("Many convention issues; inconsistent style may reduce readability.")

    pylint_examples: List[str] = []
    for msg in pylint_msgs[:5]:
        pylint_examples.append(f"Line {msg['line']}: {msg['message']}")

    pylint_summary_text = (
        "\n".join(pylint_examples) if pylint_examples else "No specific linting issues found."
    )

    summary_text = f"""
### File Analysis Report: {meta['file']}

--- Static Code Metrics ---
- Lines of Code (LOC): {meta['loc']}
- Number of Classes: {meta['num_classes']}
- Number of Functions: {meta['num_functions']}
- Imports: {meta['imports']}
- Average Cyclomatic Complexity: {meta['avg_cc']:.2f}
- Maximum Cyclomatic Complexity: {meta['max_cc']}
- Maintainability Index: {meta['maintainability_index']:.2f}

--- Pylint Summary ---
- Convention issues: {pylint_summary['convention']}
- Refactor suggestions: {pylint_summary['refactor']}
- Warnings: {pylint_summary['warning']}
- Errors: {pylint_summary['error']}
- Fatal errors: {pylint_summary['fatal']}

--- Example Lint Messages ---
{pylint_summary_text}

--- Interpretation ---
{ " ".join(interpretations) if interpretations else "No major maintainability risks detected." }

--- Instruction for LLM ---
Use this report to evaluate how maintainable, complex, or stylistically consistent the file is.
When prioritizing technical debt, files with higher complexity, lower maintainability index,
or multiple convention/refactor issues should be ranked higher.
""".strip()

    technical_risk_score = (
        meta["avg_cc"] / 10
        + (100 - meta["maintainability_index"]) / 20
        + pylint_summary["refactor"] * 0.5
        + pylint_summary["warning"] * 0.5
    )

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
