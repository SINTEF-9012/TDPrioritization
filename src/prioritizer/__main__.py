# src/prioritizer/pipelines/dispatcher.py
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path
from haystack_integrations.document_stores.chroma import ChromaDocumentStore

from prioritizer.cli.args import parse_args
from prioritizer.pipelines.baseline_rag.smells_prioritizer import run_rag_pipeline
from prioritizer.pipelines.agentic.ai_agent import run_agent_pipeline

def run() -> Path:
    args = parse_args()
    smells = ['Long Method', 'Large Class', 'Long File', 'High Cyclomatic Complexity', 'Feature Envy'] 
    document_store = ChromaDocumentStore(persist_path="src/prioritizer/data/embeddings_db")


    if args.pipeline == "rag":
        return run_rag_pipeline(args, smells, document_store)
    elif args.pipeline == "agent":
        return run_agent_pipeline(args, smells)
    else:
        raise ValueError(f"Unknown pipeline mode: {args.pipeline!r}")


def main():
    run()


if __name__ == "__main__":
    main()