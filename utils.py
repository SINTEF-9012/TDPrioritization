import ast
from typing import Optional
import math
import ast
import radon.complexity as radon_cc
import radon.metrics as radon_metrics
from pylint.lint import Run, PyLinter
from io import StringIO
from pylint.reporters.json_reporter import JSONReporter
import json

def patch_astroid_namespace_bug():
    import astroid.interpreter._import.util as util
    from pathlib import Path
    if hasattr(util, "is_namespace"):
        orig_any = util.is_namespace
        def safe_is_namespace(modname):
            try:
                for location in getattr(util, "STD_AND_EXT_LIB_DIRS", []):
                    if isinstance(location, Path):
                        continue
                return orig_any(modname)
            except AttributeError:
                return False
        util.is_namespace = safe_is_namespace

def get_entity_snippet_from_line(
    start_line: float,
    file_path: Optional[str] = None,
    code: Optional[str] = None):
    """
    Return the source code snippet for the class or function starting at `start_line`.

    Args:
        file_path: Path to the Python source file. Mutually exclusive with `code`.
        code: Raw Python source code string. Mutually exclusive with `file_path`.
        start_line: Line number where the entity starts (1-based).
    
    Returns:
        The source code snippet as a string, or None if no entity found.
    """

    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    elif code is None:
        raise ValueError("Either file_path or code must be provided.")
    
    if isinstance(start_line, float) and math.isnan(start_line):
        return code

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Invalid Python code: {e}") from e
    
    lines = code.splitlines(keepends=True)
    start_line = int(start_line)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno == start_line: 
                # Find end line
                if hasattr(node, "end_lineno") and node.end_lineno is not None:
                    end = node.end_lineno
                else:
                    end = max(getattr(n, "lineno", start_line) for n in ast.walk(node))

                return "".join(lines[start_line-1:end])


    return None 

def analyze_file(file_path):
    metadata = {"file": file_path}
    
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    tree = ast.parse(code)
    lines = len(code.splitlines())

    # --- File-Level Metrics ---
    metadata["loc"] = lines
    metadata["num_classes"] = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
    metadata["num_functions"] = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
    metadata["imports"] = len([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))])

    # --- Radon Metrics ---
    cc_scores = radon_cc.cc_visit(code)
    metadata["avg_cc"] = sum(c.complexity for c in cc_scores) / len(cc_scores) if cc_scores else 0
    metadata["max_cc"] = max((c.complexity for c in cc_scores), default=0)
    metadata["cc_std"] = (sum((c.complexity - metadata["avg_cc"]) ** 2 for c in cc_scores) / len(cc_scores)) ** 0.5 if cc_scores else 0
    metadata["maintainability_index"] = radon_metrics.mi_visit(code, True)

    # --- Large Class & Method-Specific ---
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    class_data = []
    for c in classes:
        methods = [n for n in c.body if isinstance(n, ast.FunctionDef)]
        avg_method_len = sum(len(ast.get_source_segment(code, m).splitlines()) for m in methods) / len(methods) if methods else 0
        class_data.append({
            "name": c.name,
            "methods": len(methods),
            "avg_method_len": avg_method_len,
            "total_lines": len(ast.get_source_segment(code, c).splitlines())
        })
    metadata["classes"] = class_data

    return metadata

def create_pylinter_and_jsonReporter_object():
    reporter = JSONReporter()
    pylinter_obj = PyLinter(reporter=reporter)

    pylinter_obj.load_default_plugins()
    pylinter_obj.disable('all')

    # Enable only relevant categories
    for cat in ('C', 'R', 'W', 'E', 'F'):
        pylinter_obj.enable(cat)
    
    # Optionally skip heavy modules
    pylinter_obj.config.ignore = ['torch', 'transformers', 'datasets']

    return pylinter_obj, reporter

def get_pylint_metadata(file_path: str, reporter: JSONReporter, linter: PyLinter):
    reporter._output = StringIO()
    linter.check([file_path])
    results = json.loads(reporter._output.getvalue() or "[]")

    summary = {
        "convention": 0,
        "refactor": 0,
        "warning": 0,
        "error": 0,
        "fatal": 0,
    }

    simplified_results = []

    for msg in results:
        summary[msg["type"]] += 1

        temp = {}
        temp["type"] = msg["type"]
        temp["module"] = msg["module"]
        temp["line"] = msg["line"]
        temp["path"] = msg["path"]
        temp["message"] = msg["message"]

        simplified_results.append(temp)

    return summary, simplified_results

def build_llm_analysis_report(file_path: str, reporter: JSONReporter, linter: PyLinter):
    """
    Combine Radon, AST, and Pylint results into an LLM-friendly analysis summary.
    Produces a natural-language text block plus structured metadata.
    """

    if file_path is None:
        return "An invalid filepath was provided."

    meta = analyze_file(file_path)
    pylint_summary, pylint_msgs = get_pylint_metadata(file_path, reporter, linter)

    # --- Interpret basic metrics ---
    interpretations = []

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

    # --- Pylint findings summary ---
    pylint_examples = []
    for msg in pylint_msgs[:5]:  # Limit to 5 examples for readability
        pylint_examples.append(f"Line {msg['line']}: {msg['message']}")

    pylint_summary_text = "\n".join(pylint_examples) if pylint_examples else "No specific linting issues found."

    # --- Compose final text ---
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
{" ".join(interpretations) if interpretations else "No major maintainability risks detected."}

--- Instruction for LLM ---
Use this report to evaluate how maintainable, complex, or stylistically consistent the file is.
When prioritizing technical debt, files with higher complexity, lower maintainability index,
or multiple convention/refactor issues should be ranked higher.
"""

    # --- Return both raw data and text block for RAG ingestion ---
    return {
        "text": summary_text.strip(),
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
            "technical_risk_score": (
                meta["avg_cc"] / 10
                + (100 - meta["maintainability_index"]) / 20
                + pylint_summary["refactor"] * 0.5
                + pylint_summary["warning"] * 0.5
            )
        }
    }


# For debugging the functions
if __name__ == "__main__":
    linter, reporter = create_pylinter_and_jsonReporter_object()

    report = build_llm_analysis_report("projects/text_classification/app.py", reporter, linter)

    print(report["text"])