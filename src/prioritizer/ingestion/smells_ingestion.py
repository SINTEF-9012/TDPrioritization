from haystack import Document
from haystack.components.builders.prompt_builder import PromptBuilder

from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack_integrations.components.retrievers.chroma import ChromaQueryTextRetriever
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.chroma import ChromaEmbeddingRetriever
import pandas as pd
from git import Repo
import random

from analysis import get_code_segment_from_file_based_on_line_number, build_llm_analysis_report
from history.git_history import build_report
from typing import List, Any

def read_relevant_code_smells_and_write_to_documents(smell_filter: List[str]) ->  List[dict[str, Any]]:
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

def build_haystack_documents(smells: dict[str, Any]) -> List[Document]:
    docs: List[Document] = []
    for s in smells:
        content = (
            f"SMELL\n"
            f"- id: {s.get('index')}\n"
            f"- type_of_smell: {s.get('type_of_smell')}\n"
            f"- name: {s.get('name')}\n"
            f"- file_path: {s.get('file_path')}\n"
            f"- module_or_class: {s.get('module_or_class')}\n"
            f"- line_number: {s.get('line_number')}\n\n"
            f"DESCRIPTION\n{s.get('description')}\n\n"
            f"GIT_ANALYSIS\n{s.get('git_analysis', 'N/A')}\n\n"
            f"PYLINT_REPORT\n{s.get('pylint_report', 'N/A')}\n\n"
            f"AI SUMMARIZATION OF THE CODE\n{s.get('ai_code_segment_summary', 'N/A')}\n"
        )

        docs.append(Document(
            content=content,
            meta={
                "type": "smell",
                "index": s.get("index"),
                "smell_name": s.get("name"),
                "file_path": s.get("file_path"),
                "description": s.get("description"),
            }
        ))
    return docs