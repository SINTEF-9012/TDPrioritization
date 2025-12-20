import os
from typing import Set

EXCLUDE_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".mypy_cache",
}

def build_project_structure(root_dir) -> str:
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


# Testing and debugging
if __name__ == "__main__":
    project_structure = build_project_structure("projects/text_classification")
    print(project_structure)
