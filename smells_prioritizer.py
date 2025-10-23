from haystack import Pipeline, Document, component
from haystack.utils import Secret
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.builders.prompt_builder import PromptBuilder

from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack_integrations.components.retrievers.chroma import ChromaQueryTextRetriever
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.chroma import ChromaEmbeddingRetriever

import argparse
import requests
import csv
import pandas as pd
import os
from utils import get_entity_snippet_from_line, build_llm_analysis_report, create_pylinter_and_jsonReporter_object
from git_history import build_report
from chunking import convert_chunked_text_to_haystack_documents
from prompt_template import PROMPT_TEMPLATE
from git import Repo

@component
class OllamaGenerator:
    def __init__(self, model="qwen3:4b", url="http://localhost:11434/api/generate", save_to_file: bool = False, save_file: str = None, full_prompt_file: str = None):
        self.model = model
        self.url = url
        self.save_to_file = save_to_file
        self.save_file = save_file
        self.full_prompt_file = full_prompt_file

    def run(self, prompt: str):
        response = requests.post(self.url, json={
            "model": self.model,
            "prompt": prompt,
            "stream": False
        })

        result = response.json()

        if self.save_to_file:
            with open(self.save_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([result["response"]])
        
        with open(self.full_prompt_file, "w", newline="", encoding="utf-8") as f: 
            writer = csv.writer(f)
            writer.writerow([prompt])

        return {"replies": [result["response"]]}
    

def read_code_smells_and_write_to_documents(csv_path, smell_filter, repo_path):
    df = pd.read_csv(csv_path)
    report_dir = os.path.dirname(csv_path)
    docs = []
    linter, reporter = create_pylinter_and_jsonReporter_object()

    for _, row in df.iterrows():
        if row["Name"] not in smell_filter:
            continue

        file_path = os.path.normpath(os.path.join(report_dir, row["File"]))
        code_segment = ""
        if os.path.isfile(file_path):
            code_segment = get_entity_snippet_from_line(row["Line Number"], file_path)
            code_metadata_report = build_llm_analysis_report(file_path, reporter, linter)["text"]
            git_analysis_report = build_report(repo_path, file_path.split("/")[-1])


        content = (
            f"Type of smell: {row['Type']}\n"
            f"Code smell: {row['Name']}\n"
            f"Description: {row['Description']}\n"
            f"File: {row['File']}\n"
            f"Severity: {row['Severity']}\n"
            f"Code segment (for context only):\n{code_segment}\n"
            f"{code_metadata_report}\n"
            f"{git_analysis_report}\n"
        )
        docs.append(Document(content=content, meta={"type": "smell"}))
    return docs

def load_embedder_pair(model_name="sentence-transformers/all-MiniLM-L6-v2"):
    doc_embedder = SentenceTransformersDocumentEmbedder(model=model_name)
    query_embedder = SentenceTransformersTextEmbedder(model=model_name)
    doc_embedder.warm_up()
    query_embedder.warm_up()
    return doc_embedder, query_embedder


def build_rag_pipeline(document_store, prompt_template, model_name, prompt_file, llm_output_file):
    retriever = ChromaEmbeddingRetriever(document_store=document_store)
    prompt_builder = PromptBuilder(template=prompt_template, required_variables={"question", "documents", "smells"})
    llm = OllamaGenerator(model=model_name, save_to_file=True, save_file=llm_output_file, full_prompt_file=prompt_file)

    pipeline = Pipeline()
    pipeline.add_component("retriever", retriever)
    pipeline.add_component("prompt_builder", prompt_builder)
    pipeline.add_component("llm", llm)

    pipeline.connect("retriever", "prompt_builder.documents")
    pipeline.connect("prompt_builder", "llm")

    return pipeline


def main():
    parser = argparse.ArgumentParser(description="Analyze and prioritize code smells for a project.")
    parser.add_argument("project", help="Name of the project directory (e.g., cerberus)")
    parser.add_argument("--model", default="qwen3:4b", help="Which Ollama LLM model to use")
    parser.add_argument("--output", default="llm_output.txt", help="File to save results from the LLM")
    parser.add_argument("--base_line", default="base_line", help="directory where the different files should be stored")
    parser.add_argument("--outdir", default="baseline", help="Directory where the output files should be stored")

    args = parser.parse_args()

    code_smell_documents = []
    smells = ['Long Method', 'Large Class', 'Long File'] 
    repo = Repo(f"projects/{args.project}")

    dir_name = args.outdir+"_"+args.model
    os.makedirs(dir_name, exist_ok=True)
    documents_file = os.path.join(dir_name, "full_prompt.txt")
    llm_output_file = os.path.join(dir_name, "llm_output.txt")


    code_smell_documents = read_code_smells_and_write_to_documents("python_smells_detector/code_quality_report.csv", smells, repo)

    # There are no documents.
    if len(code_smell_documents) == 0:
        print("The project does not contain any of the code smells you inquired about")
        return 0
    
    document_store = ChromaDocumentStore()

    #print(document_store.count_documents())

    chunked_docs_of_articles = convert_chunked_text_to_haystack_documents()

    question = (
        "Considering both the cost of refactoring and the potential benefits to software quality, "
        "rank the provided code smells by the order in which they should be addressed. "
        "Explain briefly for each smell how its severity, propagation risk, and long-term impact justify its position."
    )
            
    doc_embedder, query_embedder = load_embedder_pair()

    embedded_articles = doc_embedder.run(documents=chunked_docs_of_articles)["documents"]
    print(f"Embedded {len(embedded_articles)} article chunks.")

    # Quick check of embedding dimensions
    if len(embedded_articles) > 0:
        print("Sample article embedding length:", len(embedded_articles[0].embedding))

    embedded_smells_doc = doc_embedder.run(documents=code_smell_documents)["documents"]

    document_store.write_documents(embedded_articles)
    print("Wrote article chunks to Chroma.")

    smells_text = "\n".join([doc.content for doc in code_smell_documents])
    query_embedding = query_embedder.run(smells_text)["embedding"]

    rag_pipeline = build_rag_pipeline(document_store, PROMPT_TEMPLATE, args.model, documents_file, llm_output_file)

    print("Running model: " + args.model)
    results = rag_pipeline.run(
        {
            "retriever": {"query_embedding": query_embedding},
            "prompt_builder": {
                "question": question,
                "smells": embedded_smells_doc
                },
        }
    )

main()


"""
Send the code segment alone to the llm for it to analyze, store the text from it and use text as metadata to the relevant document?

personification - Assign the role (minimal responsibility) - work as a prioritizing agent. 

Lang chain

google cli - coding agents - gemini CLI and claude CLI to evaluate againt my prototype. 

Provide metadata rather than hard text and code
"""