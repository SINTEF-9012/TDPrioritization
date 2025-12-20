import ast
from typing import Any, Dict, List

import radon.complexity as radon_cc
import radon.metrics as radon_metrics

_FILE_METRICS_CACHE: Dict[str, Dict[str, Any]] = {}

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
