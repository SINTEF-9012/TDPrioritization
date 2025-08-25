import ast
from typing import Optional
import math


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
