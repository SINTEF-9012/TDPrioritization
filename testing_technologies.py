from haystack import Pipeline, Document, component
from haystack.utils import Secret
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.builders.prompt_builder import PromptBuilder

import requests
import csv

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
                writer.writerow([prompt, result["response"]])

        return {"replies": [result["response"]]}


def main():
    # Write documents to InMemoryDocumentStore
    document_store = InMemoryDocumentStore()
    document_store.write_documents([
        Document(content="My name is Jean and I live in Paris."),
        Document(content="My name is Mark and I live in Berlin."),
        Document(content="My name is Giorgio and I live in Rome.")
    ])

    # Build a RAG pipeline
    prompt_template = """
You are a helpful assistant.
Given these documents, answer the question.\n
Documents:\n{% for doc in documents %}{{ doc.content }}{% endfor %}\n
Question: {{question}}\n
Answer:
"""

    # Define required variables explicitly
    prompt_builder = PromptBuilder(template=prompt_template, required_variables={"question", "documents"})

    retriever = InMemoryBM25Retriever(document_store=document_store)
    llm = OllamaGenerator(model="llama3.2:latest", save_to_file=True, save_file="output.csv")

    rag_pipeline = Pipeline()
    rag_pipeline.add_component("retriever", retriever)
    rag_pipeline.add_component("prompt_builder", prompt_builder)
    rag_pipeline.add_component("llm", llm)
    rag_pipeline.connect("retriever", "prompt_builder.documents")
    rag_pipeline.connect("prompt_builder", "llm")

    # Ask a question
    question = "Who lives in Paris?"
    results = rag_pipeline.run(
        {
            "retriever": {"query": question},
            "prompt_builder": {"question": question},
        }
    )

    print(results["llm"]["replies"])

main()
