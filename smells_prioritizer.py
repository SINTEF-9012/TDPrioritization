from haystack import Pipeline, Document, component
from haystack.utils import Secret
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.builders.prompt_builder import PromptBuilder

import argparse
import requests
import csv
import pandas as pd
import os
from utils import get_entity_snippet_from_line
from git import Repo

@component
class OllamaGenerator:
    def __init__(self, model="qwen3:4b", url="http://localhost:11434/api/generate", save_to_file: bool = False, save_file: str = None):
        self.model = model
        self.url = url
        self.save_to_file = save_to_file
        self.save_file = save_file

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

        return {"replies": [result["response"]]}


def main():
    parser = argparse.ArgumentParser(description="Analyze and prioritize code smells for a project.")
    parser.add_argument("project", help="Name of the project directory (e.g., cerberus)")
    parser.add_argument("--model", default="llama3.2:latest", help="Which Ollama LLM model to use")
    parser.add_argument("--output", default="llm_output.txt", help="File to save results from the LLM")
    parser.add_argument("--base_line", default="base_line", help="directory where the different files should be stored")
    parser.add_argument("--outdir", default="baseline", help="Directory where the output files should be stored")

    args = parser.parse_args()

    documents = []
    data_frame = pd.read_csv("python_smells_detector/code_quality_report.csv")
    report_dir = os.path.dirname("python_smells_detector/code_quality_report.csv")
    smells = ['Duplicate Code', 'Long Method', 'Large Class'] 
    repo = Repo(f"projects/{args.project}")

    os.makedirs(args.outdir, exist_ok=True)
    smells_file = os.path.join(args.outdir, "smells.txt")
    documents_file = os.path.join(args.outdir, "documents.txt")
    output_file = os.path.join(args.outdir, args.output)
    prompt_file = os.path.join(args.outdir, "prompt_template.txt")


    with open(smells_file, "w") as f, open(documents_file, "w") as f2:
        f.write("------ CODE SMELLS TO BE PRIORITIZED BY THE LLM ------\n")
        f2.write("------ CREATED DOCUMENTS ------\n")

        for _, column in data_frame.iterrows():
            if column['Name'] not in smells: continue

            f.write(str(column) + "\n\n")

            file_path = os.path.normpath(os.path.join(report_dir, column["File"])) 
            code_segment = ""

            if os.path.isfile(file_path): 
                code_segment = get_entity_snippet_from_line(column['Line Number'], file_path )
            
            content = (
                f"Type of smell: {column['Type']}\n"
                f"Name: {column['Name']}\n"
                f"Description: {column['Description']}\n"
                f"File: {column['File']}\n"
                f"Module/Class: {column['Module/Class']}\n"
                f"Line Number: {column['Line Number']}\n"
                #f"Severity: {column['Severity']}\n"
                f"Code segment:\n{code_segment}\n"
                f"\n"
            )

            f2.write(content)
            documents.append(Document(content=content))

    # There are no documents.
    if len(documents) == 0:
        print("The project does not contain any of the code smells you inquired about")
        return 0

    # Write documents to InMemoryDocumentStore
    document_store = InMemoryDocumentStore()
    document_store.write_documents(documents)

    #print(document_store.count_documents())

    # Build a RAG pipeline
    prompt_template = """
You are a helpful assistant specialized in software quality and technical debt.
Given these documents, analyze and prioritize the identified code smells.\n
Documents:\n{% for doc in documents %}{{ doc.content }}{% endfor %}\n

When answering, consider:
- Contextual relevance: How Retrieval-Augmented Generation (RAG) enriches prioritization by grounding in the provided documents.

Question: {{question}}\n
Answer:
"""

    question = "Based on the documents, can you prioritize the identified smells by considering their contextual relevance, long-term risk (change- and fault-proneness), and their impact on developer workflows?"
    
    # Define required variables explicitly
    prompt_builder = PromptBuilder(template=prompt_template, required_variables={"question", "documents"})

    # top_k tells the retriever that we want the n most relevant documents.
    retriever = InMemoryBM25Retriever(document_store=document_store, top_k=10)
    llm = OllamaGenerator(model=args.model, save_to_file=True, save_file=output_file)

    with open(prompt_file, "w") as f:
        f.write("LLM: "+ args.model + "\n")
        f.write("Question: " + question+"\n")
        f.write("Prompt template:\n")
        f.write(prompt_template)

    rag_pipeline = Pipeline()
    rag_pipeline.add_component("retriever", retriever)
    rag_pipeline.add_component("prompt_builder", prompt_builder)
    rag_pipeline.add_component("llm", llm)
    rag_pipeline.connect("retriever", "prompt_builder.documents")
    rag_pipeline.connect("prompt_builder", "llm")

    results = rag_pipeline.run(
        {
            "retriever": {"query": question},
            "prompt_builder": {"question": question},
        }
    )

    #print(results["llm"]["replies"][0])


main()

"""
You are a helpful assistant specialized in software quality and technical debt.
Given these documents, analyze and prioritize the identified code smells.\n
Documents:\n{% for doc in documents %}{{ doc.content }}{% endfor %}\n

When answering, consider:
- Contextual relevance: How Retrieval-Augmented Generation (RAG) enriches prioritization by grounding in the provided documents.
- Risk factors: Change-proneness and fault-proneness (i.e., likelihood of a component to be modified or fail in the future).
- Workflow integration: How the prioritization would fit into practical developer workflows (IDEs, CI/CD, code review), focusing on actionable insights.

Question: {{question}}\n
Answer:
"""
