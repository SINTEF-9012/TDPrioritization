import ast
from typing import Optional
import math

import os
import ast
import radon.complexity as radon_cc
import radon.metrics as radon_metrics
from pylint.lint import Run
from git import Repo
from io import StringIO
import contextlib
from pylint.reporters.json_reporter import JSONReporter



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

def analyze_file(file_path, repo_path=None):
    metadata = {"file": file_path}
    
    # --- Radon Metrics ---
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Cyclomatic Complexity
    cc_results = radon_cc.cc_visit(code)
    metadata["complexity"] = {f.name: f.complexity for f in cc_results}
    
    # Maintainability Index
    mi_score = radon_metrics.mi_visit(code, True)
    metadata["maintainability_index"] = mi_score
    
    # --- AST Analysis ---
    tree = ast.parse(code)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    metadata["functions"] = [{
        "name": f.name,
        "args": len(f.args.args),
        "docstring": ast.get_docstring(f),
        "nested_blocks": sum(isinstance(n, (ast.If, ast.For, ast.While)) for n in ast.walk(f))
    } for f in funcs]
        
    
    return metadata

def get_pylint_metadata(file_path: str):
    buffer = StringIO()
    reporter = JSONReporter(output=buffer)

    # Redirect output, run pylint
    with contextlib.redirect_stdout(StringIO()):
        Run([file_path], reporter=reporter, exit=False)

    buffer.seek(0)
    results = buffer.read()

    # You now have a JSON string with all the pylint findings
    # (errors, warnings, refactor suggestions, conventions, etc.)
    return results


# For debugging purposes
if __name__ == "__main__":
    repo_path = "projects/text-classification" 

    meta = analyze_file("projects/text_classification/hf_upload_example.py")
    pylint = get_pylint_metadata("projects/text_classification/hf_upload_example.py")
    print(meta)
    print(pylint)