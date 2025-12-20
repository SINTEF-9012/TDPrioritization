import json
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

from pylint.lint import PyLinter
from pylint.reporters.json_reporter import JSONReporter

from .astroid_patches import patch_astroid_namespace_bug

patch_astroid_namespace_bug()

_PYLINT_RESULTS_CACHE: Dict[str, Tuple[Dict[str, int], List[Dict[str, Any]]]] = {}
_PYLINTER_SINGLETON: Optional[Tuple[PyLinter, JSONReporter]] = None

def get_pylinter_singleton() -> Tuple[PyLinter, JSONReporter]:
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