from haystack import Pipeline, Document
from haystack.components.builders.prompt_builder import PromptBuilder

from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack_integrations.components.retrievers.chroma import ChromaQueryTextRetriever
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.chroma import ChromaEmbeddingRetriever

import csv
import pandas as pd
import os
from git import Repo
import random
from pathlib import Path


from prioritizer.analysis import get_code_segment_from_file_based_on_line_number, build_llm_analysis_report, build_project_structure
from prioritizer.history.git_history import build_report
from prioritizer.ingestion.chunking import convert_chunked_text_to_haystack_documents
from prioritizer.llm.analyze_code_segment import analyze_code_segments_via_ai
from prioritizer.cli.cli import parse_args
from prioritizer.llm.prompt_template import PROMPT_TEMPLATE
from prioritizer.llm.ollama_client import OllamaGenerator
from typing import List, Any


from langchain_ollama import ChatOllama

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

def load_embedder_pair(model_name="sentence-transformers/all-MiniLM-L6-v2") -> tuple[SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder]:
    doc_embedder = SentenceTransformersDocumentEmbedder(model=model_name)
    query_embedder = SentenceTransformersTextEmbedder(model=model_name)
    doc_embedder.warm_up()
    query_embedder.warm_up()
    return doc_embedder, query_embedder


def build_rag_pipeline(document_store, prompt_template, model_name, prompt_file) -> Pipeline:
    retriever = ChromaEmbeddingRetriever(document_store=document_store)
    prompt_builder = PromptBuilder(template=prompt_template, required_variables={"question", "documents", "smells", "project_structure"})
    llm = OllamaGenerator(model=model_name, full_prompt_file=prompt_file)

    pipeline = Pipeline()
    pipeline.add_component("retriever", retriever)
    pipeline.add_component("prompt_builder", prompt_builder)
    pipeline.add_component("llm", llm)

    pipeline.connect("retriever", "prompt_builder.documents")
    pipeline.connect("prompt_builder", "llm")

    return pipeline


def main():
    args = parse_args()

    smells = ['Long Method', 'Large Class', 'Long File', 'High Cyclomatic Complexity', 'Feature Envy'] 
    project_to_be_analyzed = Repo(f"src/prioritizer/data/projects/{args.project_name}")

    experiments_dir = Path("experiments") / "baseline_run_001"
    experiments_dir.mkdir(parents=True, exist_ok=True)

    full_prompt_file = experiments_dir / "full_prompt.txt"

    code_smells_dic = read_relevant_code_smells_and_write_to_documents(smells) 
    code_smells_dic = add_further_context(project_to_be_analyzed, code_smells_dic, True, True, True)

    llm = ChatOllama(
        model="gpt-oss:20b-cloud",
        temperature=0,
        seed=42,
    )

    code_smells_dic = analyze_code_segments_via_ai(code_smells_dic, llm, True)
    documents = build_haystack_documents(code_smells_dic)

    if len(documents) == 0:
        print("The project does not contain any of the code smells you inquired about")
        return 0
    
    document_store = ChromaDocumentStore()
   
    doc_embedder, query_embedder = load_embedder_pair()

    if args.include_articles:
        chunked_docs_of_articles = convert_chunked_text_to_haystack_documents()
        embedded_articles = doc_embedder.run(documents=chunked_docs_of_articles)["documents"]
        document_store.write_documents(embedded_articles)
        print(f"Embedded {len(embedded_articles[0].embedding)} article chunks and wrote them to Chroma.")
    else:
        print("Articles disabled; proceeding without embedded literature.")

    rag_pipeline = build_rag_pipeline(document_store, PROMPT_TEMPLATE, args.model_name, full_prompt_file)

    question = (
        "Use evidence from the embedded research (INFO ON CODE SMELLS AND TECHNICAL DEBT) to rank ALL code smells \
        by refactoring priority in this project. The smells to consider are: Long Method, Large Class, Long File, \
        High Cyclomatic Complexity, and Feature Envy.\
        For each smell instance, justify its rank using research-backed signals such as change-proneness \
        (e.g., churn and recency), fault/defect-proneness (bug association), severity metrics \
        (e.g., size, cyclomatic or cognitive complexity), propagation risk, and expected refactoring ROI \
        (cost versus long-term maintainability benefit). \
        When the research discusses any of these smells—or closely related concepts such as God Class, \
        Large/God Method, complexity, coupling, or cohesion—explicitly apply those principles to the \
        available project-specific evidence (git statistics, churn, recency, static analysis, and lint results)."
    )

    query_embedding = query_embedder.run(question)["embedding"]

    print("Running model: " + args.model_name)
    results = rag_pipeline.run(
        {
            "retriever": {"query_embedding": query_embedding},
            "prompt_builder": {
                "question": question,
                "smells": documents,
                "project_structure": build_project_structure(f"data/projects/{args.project_name}") if args.include_project_structure else "Not included."
                },
        }
    )["llm"]

    llm_output_file = experiments_dir / "llm_output"

    with open(llm_output_file.with_suffix(".txt"), "w", encoding="utf-8") as f1, \
        open(llm_output_file.with_suffix(".csv"), "w", encoding="utf-8") as f2:

        writer1 = csv.writer(f1)
        writer1.writerow([results["response"]])

        writer2 = csv.writer(f2)
        writer2.writerow([results["response"]])
    

if __name__ == "__main__":
    main()


"""
What is left of the basline:
- Add more articles about TD and code smells.

Plasubility score - defined by myself - should be justified. 

Ranking - function (is it correct)
Embedding - (any other alternatigves to huging face)

Run 10 times (minimum).

personification - Assign the role (minimal responsibility) - work as a prioritizing agent. 

google cli - coding agents - gemini CLI and claude CLI to evaluate againt my prototype. 

Cumulative lift chart

bash run_analyzer.sh gitmetrics --model gpt-oss:20b-cloud --add-project-structure

Sekvens diagram for agentene
"""
