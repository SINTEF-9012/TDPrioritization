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
from utils import get_entity_snippet_from_line, get_pylint_metadata, analyze_file
from chunking import convert_chunked_text_to_haystack_documents
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


def main():
    parser = argparse.ArgumentParser(description="Analyze and prioritize code smells for a project.")
    parser.add_argument("project", help="Name of the project directory (e.g., cerberus)")
    parser.add_argument("--model", default="qwen3:4b", help="Which Ollama LLM model to use")
    parser.add_argument("--output", default="llm_output.txt", help="File to save results from the LLM")
    parser.add_argument("--base_line", default="base_line", help="directory where the different files should be stored")
    parser.add_argument("--outdir", default="baseline", help="Directory where the output files should be stored")

    args = parser.parse_args()

    code_smell_documents = []
    data_frame = pd.read_csv("python_smells_detector/code_quality_report.csv")
    report_dir = os.path.dirname("python_smells_detector/code_quality_report.csv")
    smells = ['Long Method', 'Large Class', 'Long File'] 
    repo = Repo(f"projects/{args.project}")

    dir_name = args.outdir+"_"+args.model
    os.makedirs(dir_name, exist_ok=True)
    smells_file = os.path.join(dir_name, "smells.txt")
    documents_file = os.path.join(dir_name, "documents.txt")
    output_file = os.path.join(dir_name, args.output)
    prompt_file = os.path.join(dir_name, "prompt_template.txt")

    with open(smells_file, "w") as f:
        f.write("------ CODE SMELLS TO BE PRIORITIZED BY THE LLM ------\n")
        counter = 0

        for _, column in data_frame.iterrows():
            if column['Name'] not in smells: continue

            f.write(str(column) + "\n\n")

            file_path = os.path.normpath(os.path.join(report_dir, column["File"])) 
            code_segment = ""
            code_metadata = None
            pylint = None

            if os.path.isfile(file_path): 
                code_segment = get_entity_snippet_from_line(column['Line Number'], file_path )
                #code_metadata = analyze_file(file_path)
                #pylint = get_pylint_metadata(file_path)
            
            content = (
                f"\nType of smell: {column['Type']}\n"
                f"Code smell: {column['Name']}\n"
                f"Description: {column['Description']}\n"
                f"File: {column['File']}\n"
                f"Module/Class: {column['Module/Class']}\n"
                f"Line Number: {column['Line Number']}\n"
                f"Severity: {column['Severity']}\n"
                f"Code segment (for context only, not analysis):\n{code_segment}"
                #f"Metadata received from pylint: {pylint}\n"
                #f"General metadata received through radon: {code_metadata}\n"

                f"\n"
            )
            
            counter += 1
            code_smell_documents.append(Document(content=content, meta={"type":"smell"}))

    # There are no documents.
    if len(code_smell_documents) == 0:
        print("The project does not contain any of the code smells you inquired about")
        return 0
    
    # Write documents to InMemoryDocumentStore
    document_store = ChromaDocumentStore()

    #print(document_store.count_documents())

    # Build a RAG pipeline
    prompt_template = """
You are a prioritizing agent specialized in analyzing software quality and prioritizing technical debt. 
You are practical with prioritizing technical debt, and are given a report of different types of code smells located in a project. 
Answer the user's question based on the context below. 

Follow these steps carefully:

1. Use the best practices for managing and prioritizing technical debt. Refer to definitions of technical debt categories (e.g., code smells, architectural issues, documentation gaps, testing debt).
2. Read the question carefully and make sure you understand what the user is asking about prioritization.
3. Look for relevant information in the provided documents that contain information about files, smells, and context.
4. Each document contains information about one smell found in the source code of the project. Each document is independent of each other, and you must not use information from one document to prioritize or analyze a different smell/document.
5. When formulating the answer, provide detailed reasoning. Explain why some debts should be prioritized over others (e.g., high defect association, or large impact on maintainability).
6. When formulating the answer, provide the rankings in the given format:
<Rank>, <Name of smell>, <Type of smell>, <File name>, <Reason for prioritization>.
7. Consider multiple dimensions for prioritization: recency of changes, frequency of changes, severity of impact, dependencies, and criticality of the affected component.
8. You must include **all smells** from the documents in your ranking. 
- Example: If there are 8 documents, your answer must contain exactly 8 ranked items.
- Do not merge, ignore, or drop any smells. Even if smells are similar, list them separately.
9. Double-check before answering:
- Did you include every smell from the documents?
- Is each smell represented exactly once?

------ INFO ON CODE SMELLS AND TECHNICAL DEBT ------
{% for doc in documents %}
{{ doc.content }}
{% endfor %}

------ CODE SMELLS FOUND IN A PYTHON PROJECT ------
{% for smell in smells %}
{{ smell.content }}
{% endfor %}

Question: {{question}}

Now provide the ranked prioritization list of all given smells.
"""

    chunked_docs_of_articles = convert_chunked_text_to_haystack_documents()

    question = "Based on the provided code smells, how would you prioritize them?"
        
    # Define required variables explicitly
    prompt_builder = PromptBuilder(template=prompt_template, required_variables={"question", "documents", "smells"})

    # 3. Embed & write documents
    doc_embedder = SentenceTransformersDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2")
    query_embedder = SentenceTransformersTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2")

    # Warm them up (loads the HF model)
    doc_embedder.warm_up()
    query_embedder.warm_up()

    embedded_articles = doc_embedder.run(documents=chunked_docs_of_articles)["documents"]
    print(f"Embedded {len(embedded_articles)} article chunks.")

    # Quick check of embedding dimensions
    if len(embedded_articles) > 0:
        print("Sample article embedding length:", len(embedded_articles[0].embedding))

    embedded_smells_doc = doc_embedder.run(documents=code_smell_documents)["documents"]

    document_store.write_documents(embedded_articles)
    print("Wrote article chunks to Chroma.")


    # top_k tells the retriever that we want the n most relevant documents.
    retriever = ChromaEmbeddingRetriever(document_store=document_store)
    llm = OllamaGenerator(model=args.model, save_to_file=True, save_file=output_file, full_prompt_file = documents_file)

    smells_text = "\n".join([doc.content for doc in code_smell_documents])
    query_embedding = query_embedder.run(smells_text)["embedding"]

    with open(prompt_file, "w") as f:
        f.write("Question: " + question+"\n")
        f.write("Prompt template:\n")
        f.write(prompt_template)

    rag_pipeline = Pipeline()
    rag_pipeline.add_component("retriever", retriever)
    rag_pipeline.add_component("prompt_builder", prompt_builder)
    rag_pipeline.add_component("llm", llm)

    rag_pipeline.connect("retriever", "prompt_builder.documents")
    rag_pipeline.connect("prompt_builder", "llm")

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