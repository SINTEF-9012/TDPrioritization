from prioritizer.analysis import get_code_segment_from_file_based_on_line_number, build_llm_analysis_report, build_project_structure
from prioritizer.history.git_history import build_report

import pandas as pd
from git import Repo
import random
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

def add_further_context(project_name: Repo, code_smells: List[dict], git_stats: bool = True, pylint: bool = True, code_segment: bool = True) -> List[dict]:
    git_cache: dict[str, str] = {}
    pylint_cache: dict[str, str] = {}
    code_cache: dict[tuple[str, int], str] = {}

    for smell in code_smells:
        file_path = smell["file_path"]
        line_number = smell["line_number"]

        if file_path.startswith("../"):
            normalized_path = file_path[3:]
        else:
            normalized_path = file_path

        if git_stats:
            if normalized_path not in git_cache:
                git_cache[normalized_path] = build_report(
                    project_name, 
                    normalized_path,
                )
            smell["git_analysis"] = git_cache[normalized_path]

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
