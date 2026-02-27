from prioritizer.analysis import get_code_segment_from_file_based_on_line_number, build_llm_analysis_report, build_project_structure
from prioritizer.history.git_file_data_retrieval import build_git_input_for_llm

import pandas as pd
from git import Repo
import random
import json
from typing import List, Any

def read_and_store_relevant_smells(smell_filter: List[str]) ->  List[dict[str, Any]]: 
    df = pd.read_csv("python_smells_detector/code_quality_report.csv")
    docs: List[dict[str, Any]] = []

    i = 1

    for _, row in df.iterrows():
        if row["Name"] not in smell_filter:
            continue
        
        code_smell = {
            "index": i,
            "type_of_smell": row["Type"],
            "name": row["Name"],
            "file_path": row["File"],
            "module_or_class": row["Module/Class"],
            "line_number": row["Line Number"],
            "description": row["Description"],
        }
            
        docs.append(code_smell)

        i += 1

    # Randomize the list
    random.seed(42)
    random.shuffle(docs)

    return docs

def add_further_context(project_name: str, code_smells: List[dict], git_stats: bool = True, pylint: bool = True, code_segment: bool = True) -> List[dict]:
    git_cache: dict[str, str] = {}
    pylint_cache: dict[str, str] = {}
    code_cache: dict[tuple[str, int], str] = {}

    for smell in code_smells:
        file_path = smell["file_path"]
        line_number = smell["line_number"]

        if file_path.startswith("../"):
            normalized_path = file_path[3:]
            file_path = file_path.split(project_name+"/")[-1]
        else:
            normalized_path = file_path

        if git_stats:
            if file_path not in git_cache:
                git_cache[file_path] = build_git_input_for_llm(
                    project_name, 
                    file_path,
                )
            smell["git_analysis"] = git_cache[file_path]

        if pylint:
            if normalized_path not in pylint_cache:
                pylint_cache[normalized_path] = build_llm_analysis_report(
                    normalized_path
                )["text"]
            smell["pylint_report"] = pylint_cache[normalized_path]

        if code_segment:
            key = (normalized_path, str(line_number))
            if key not in code_cache:
                code_cache[key] = get_code_segment_from_file_based_on_line_number(
                    start_line=line_number,
                    file_path=normalized_path,
                ) or ""
            smell["code_segment"] = code_cache[key]

    return code_smells


def write_docs_to_file() -> None:
    smells = ['Long Method', 'Large Class', 'Long File', 'High Cyclomatic Complexity', 'Feature Envy', 'Cyclic Dependency'] 
    docs = read_and_store_relevant_smells(smells)
    simapy = Repo(f"test_projects/simapy")
    docs = add_further_context(simapy, docs, False, False, True)

    def _normalize_line_number(value: Any) -> Any:
        """Convert NaN/None/float line numbers into JSON-friendly values."""
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass

        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    sanitized_docs: List[dict[str, Any]] = []
    for smell in docs:
        sanitized = dict(smell)
        sanitized["line_number"] = _normalize_line_number(smell.get("line_number"))
        code_value = smell.get("code_segment")
        if isinstance(code_value, str) and code_value.strip():
            # Wrap code in a small schema to signal its nature.
            sanitized["code_segment"] = {
                "language": "python",
                "code": code_value
            }
        sanitized_docs.append(sanitized)

    payload = {"smells": sanitized_docs}

    with open("docs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)


def write_docs_to_text_file() -> None:
    """
    Write code smell entries to a human-readable text file (docs.txt).
    Mirrors write_docs_to_file but uses a formatted plain-text layout.
    """
    smells = ['Long Method', 'Large Class', 'Long File', 'High Cyclomatic Complexity', 'Feature Envy', 'Cyclic Dependency'] 
    docs = read_and_store_relevant_smells(smells)
    simapy = Repo(f"test_projects/simapy")
    docs = add_further_context(simapy, docs, False, False, True)

    def _fmt_line(value: Any) -> str:
        try:
            if pd.isna(value):
                return "N/A"
        except TypeError:
            pass
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    sections: List[str] = []
    for smell in docs:

        section = "\n".join(
            [
                f"SMELL #{smell.get('index')}: {smell.get('name')}",
                f"Type         : {smell.get('type_of_smell')}",
                f"File         : {smell.get('file_path')}",
                f"Module/Class : {smell.get('module_or_class')}",
                f"Line         : {_fmt_line(smell.get('line_number'))}",
                "Description:",
                str(smell.get('description', '')).strip(),
                "-" * 60,
            ]
        )
        sections.append(section)

    content = "\n\n".join(sections) if sections else "No matching smells were found."

    with open("docs.txt", "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    write_docs_to_file()
    write_docs_to_text_file()
