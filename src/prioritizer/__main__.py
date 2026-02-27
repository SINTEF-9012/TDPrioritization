# src/prioritizer/pipelines/dispatcher.py
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path
from haystack_integrations.document_stores.chroma import ChromaDocumentStore

from prioritizer.cli.args import parse_args
from prioritizer.pipelines.baseline_rag.smells_prioritizer import run_rag_pipeline
from prioritizer.pipelines.agentic.ai_agent import run_agent_pipeline
from prioritizer.evaluation.evaluation import write_evaluation_report

def main() -> Path:
    args = parse_args()
    smells = ['Long Method', 'Large Class', 'Long File', 'High Cyclomatic Complexity', 'Feature Envy', 'Cyclic Dependency'] # 'Cyclic Dependency' 
    document_store = ChromaDocumentStore(persist_path="src/prioritizer/data/embeddings_db")
    project_path = f"test_projects/{args.project_name}"

    if args.pipeline == "rag":
        output_path = run_rag_pipeline(args, smells, document_store, project_path)
    elif args.pipeline == "agent":
        output_path = run_agent_pipeline(args, smells, project_path)
    else:
        raise ValueError(f"Unknown pipeline mode: {args.pipeline!r}")
    
    return write_evaluation_report("src/prioritizer/data/ground_truth/prioritized_smells_simapy.csv", output_path, args)

if __name__ == "__main__":
    main()