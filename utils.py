import ast
import json
import math
import os
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import radon.complexity as radon_cc
import radon.metrics as radon_metrics
from pylint.lint import PyLinter
from pylint.reporters.json_reporter import JSONReporter

# -----------------------------
# Global caches & configuration
# -----------------------------

EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", ".idea", ".mypy_cache"}

_FILE_METRICS_CACHE: Dict[str, Dict[str, Any]] = {}
_PYLINT_RESULTS_CACHE: Dict[str, Tuple[Dict[str, int], List[Dict[str, Any]]]] = {}
_PYLINTER_SINGLETON: Optional[Tuple[PyLinter, JSONReporter]] = None

def patch_astroid_namespace_bug():
    """
    Work around a bug in astroid's namespace detection for certain environments.

    This patch is idempotent and safe to call at import time.
    """
    import astroid.interpreter._import.util as util  # type: ignore
    from pathlib import Path as _Path

    if hasattr(util, "is_namespace"):
        orig_any = util.is_namespace

        def safe_is_namespace(modname: str) -> bool:
            try:
                # Ensure it does not break if STD_AND_EXT_LIB_DIRS contains Path objects.
                for location in getattr(util, "STD_AND_EXT_LIB_DIRS", []):
                    if isinstance(location, _Path):
                        continue
                return orig_any(modname)
            except AttributeError:
                # If astroid internals change, fail closed but not catastrophically.
                return False

        util.is_namespace = safe_is_namespace  # type: ignore[assignment]

patch_astroid_namespace_bug()

def get_code_segment_from_file_based_on_line_number(start_line: float, file_path: Optional[str] = None, code: Optional[str] = None) -> Optional[str]:
    """
    Return the source code snippet for the class or function starting at `start_line`.

    Args:
        start_line:
            1-based line number where the entity starts. If NaN, the entire file/code
            is returned.
        file_path:
            Path to the Python source file. Mutually exclusive with `code`.
        code:
            Raw Python source code string. Mutually exclusive with `file_path`.

    Returns:
        The source code snippet as a string if an entity is found, the entire code
        if start_line is NaN, or None if no matching entity is found.

    Raises:
        ValueError: If neither `file_path` nor `code` is provided or if the source
        code cannot be parsed.
    """
    if file_path and code is not None:
        raise ValueError("Provide only one of `file_path` or `code`, not both.")

    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    elif code is None:
        raise ValueError("Either `file_path` or `code` must be provided.")

    # Handle NaN line numbers (e.g., for smells not tied to a specific line).
    if isinstance(start_line, float) and math.isnan(start_line):
        return code

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Invalid Python code: {e}") from e

    lines = code.splitlines(keepends=True)
    start_line_int = int(start_line)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno == start_line_int:
                if getattr(node, "end_lineno", None) is not None:
                    end = node.end_lineno
                else:
                    end = max(
                        getattr(n, "lineno", start_line_int) for n in ast.walk(node)
                    )
                return "".join(lines[start_line_int - 1 : end])

    return None

# -----------------------------
# File-level static metrics
# -----------------------------

def _read_code(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def analyze_file(file_path: str) -> Dict[str, Any]:
    """
    Compute static, file-level metrics using AST and Radon.

    This function is relatively expensive but deterministic for a given file.
    Per-file results are cached to avoid recomputation.

    Returns:
        A dict with keys:
          - file, loc, num_classes, num_functions, imports
          - avg_cc, max_cc, cc_std, maintainability_index
          - classes: list of per-class metrics
    """
    if file_path in _FILE_METRICS_CACHE:
        return _FILE_METRICS_CACHE[file_path]

    code = _read_code(file_path)
    tree = ast.parse(code)
    lines = len(code.splitlines())

    # Basic counts
    num_classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    num_functions = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    num_imports = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))

    # Radon CC
    cc_scores = radon_cc.cc_visit(code)
    if cc_scores:
        complexities = [c.complexity for c in cc_scores]
        avg_cc = sum(complexities) / len(complexities)
        max_cc = max(complexities)
        cc_std = (sum((c - avg_cc) ** 2 for c in complexities) / len(complexities)) ** 0.5
    else:
        avg_cc = max_cc = cc_std = 0.0

    maintainability_index = radon_metrics.mi_visit(code, True)

    # Per-class metrics (for potential future use)
    classes: List[Dict[str, Any]] = []
    for c in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        methods = [n for n in c.body if isinstance(n, ast.FunctionDef)]
        if methods:
            method_lengths = [
                len(ast.get_source_segment(code, m).splitlines())  # type: ignore[arg-type]
                for m in methods
            ]
            avg_method_len = sum(method_lengths) / len(method_lengths)
        else:
            avg_method_len = 0

        class_src = ast.get_source_segment(code, c)  # type: ignore[arg-type]
        total_lines = len(class_src.splitlines()) if class_src is not None else 0

        classes.append(
            {
                "name": c.name,
                "methods": len(methods),
                "avg_method_len": avg_method_len,
                "total_lines": total_lines,
            }
        )

    meta: Dict[str, Any] = {
        "file": file_path,
        "loc": lines,
        "num_classes": num_classes,
        "num_functions": num_functions,
        "imports": num_imports,
        "avg_cc": avg_cc,
        "max_cc": max_cc,
        "cc_std": cc_std,
        "maintainability_index": maintainability_index,
        "classes": classes,
    }

    _FILE_METRICS_CACHE[file_path] = meta
    return meta


# -----------------------------
# Pylint integration
# -----------------------------

def _get_pylinter_singleton() -> Tuple[PyLinter, JSONReporter]:
    """
    Lazily create and cache a PyLinter + JSONReporter instance.

    This avoids paying plugin loading + configuration cost on every call.
    """
    global _PYLINTER_SINGLETON
    if _PYLINTER_SINGLETON is not None:
        return _PYLINTER_SINGLETON

    reporter = JSONReporter()
    linter = PyLinter(reporter=reporter)

    linter.load_default_plugins()
    linter.disable("all")

    # Enable only relevant categories (convention, refactor, warning, error, fatal)
    for cat in ("C", "R", "W", "E", "F"):
        linter.enable(cat)

    # Optionally skip heavy third-party modules
    linter.config.ignore = ["torch", "transformers", "datasets"]

    _PYLINTER_SINGLETON = (linter, reporter)
    return _PYLINTER_SINGLETON
    
def get_pylint_metadata(
    file_path: str, reporter: JSONReporter, linter: PyLinter
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """
    Run pylint on a single file and return a summary and a simplified list of messages.

    Results are cached per file to avoid duplicate analysis.
    """
    if file_path in _PYLINT_RESULTS_CACHE:
        return _PYLINT_RESULTS_CACHE[file_path]

    reporter._output = StringIO()
    linter.check([file_path])

    raw = reporter._output.getvalue() or "[]"
    results = json.loads(raw)

    summary = {
        "convention": 0,
        "refactor": 0,
        "warning": 0,
        "error": 0,
        "fatal": 0,
    }

    simplified_results: List[Dict[str, Any]] = []
    for msg in results:
        msg_type = msg.get("type", "")
        if msg_type in summary:
            summary[msg_type] += 1

        simplified_results.append(
            {
                "type": msg_type,
                "module": msg.get("module"),
                "line": msg.get("line"),
                "path": msg.get("path"),
                "message": msg.get("message"),
            }
        )

    _PYLINT_RESULTS_CACHE[file_path] = (summary, simplified_results)
    return summary, simplified_results

# -----------------------------
# High-level LLM analysis report
# -----------------------------

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
        linter, reporter = _get_pylinter_singleton()

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

# -----------------------------
# Project structure
# -----------------------------

def build_project_structure(root_dir):
    """
    Build a simple textual tree of the project under `root_dir`.

    Excludes common transient/virtual directories (venv, .git, etc.).
    """
    structure = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        level = root.replace(root_dir, "").count(os.sep)
        indent_str = "│   " * level
        structure.append(f"{indent_str}├── {os.path.basename(root)}/")
        for f in files:
            structure.append(f"{indent_str}│   ├── {f}")
    return "\n".join(structure)


# For debugging the functions
if __name__ == "__main__":
    # Pylinter and Astroid is very slow. This is the reason their functions are commented out for the moment.
    #linter, reporter = create_pylinter_and_jsonReporter_object()
    #report = build_llm_analysis_report("projects/text_classification/app.py", reporter, linter)
    #print(report["text"])

    PROJECT_STRUCTURE = build_project_structure("projects/text_classification")

    print(PROJECT_STRUCTURE)
