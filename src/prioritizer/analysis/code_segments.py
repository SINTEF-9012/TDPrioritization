import ast
import math
from typing import Optional

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