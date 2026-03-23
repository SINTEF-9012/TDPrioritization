# src/prioritizer/pipelines/__main__.py
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from haystack_integrations.document_stores.chroma import ChromaDocumentStore

from prioritizer.analysis.test_coverage import run_coverage_analysis
from prioritizer.cli.args import parse_args
from prioritizer.evaluation.evaluation import write_evaluation_report
from prioritizer.pipelines.agentic.ai_agent import run_agent_pipeline
from prioritizer.pipelines.haystack.smells_prioritizer import run_rag_pipeline

load_dotenv()

SMELLS: list[str] = [
    "Long Method",
    "Large Class",
    "Long File",
    "High Cyclomatic Complexity",
    "Feature Envy",
    "Cyclic Dependency",
]

EMBEDDINGS_DB_PATH = Path("src/prioritizer/data/embeddings_db")
GROUND_TRUTH_PATH = Path("src/prioritizer/data/ground_truth/prioritized_smells_simapy.csv")
EXPERIMENTS_ROOT = Path("experiments")


def get_project_path(project_name: str) -> str:
    return f"test_projects/{project_name}"


def get_document_store() -> ChromaDocumentStore:
    return ChromaDocumentStore(persist_path=str(EMBEDDINGS_DB_PATH))


def resolve_azure_deployment_name(deployment_arg: str) -> str:
    """
    Resolve the Azure deployment name from environment variables based on the CLI deployment argument.
    """
    if deployment_arg == "gpt-3.5":
        env_var = "UIO_SE_GROUP_GPT_DEPLOYMENT_NAME"
    else:
        env_var = "UIO_SE_GROUP_CODEX_DEPLOYMENT_NAME"

    deployment_name = os.environ.get(env_var)
    if not deployment_name:
        raise ValueError(f"Missing required environment variable: {env_var}")

    return deployment_name


def get_model_prefix(deployment_name: str) -> str:
    """
    Extract the experiment-friendly model prefix from an Azure deployment name.
    """
    return deployment_name.split("-AM-MT-", 1)[0]


def build_experiments_dir(args, deployment_name: str | None = None) -> Path:
    """
    Build the experiment output directory for the selected pipeline/provider/model.
    """
    if args.llm_provider == "azure":
        if not deployment_name:
            raise ValueError("deployment_name is required when llm_provider='azure'")
        model_part = get_model_prefix(deployment_name)
        return EXPERIMENTS_ROOT / f"{args.pipeline}_pipeline_azure_{model_part}"

    safe_model = args.ollama_model.replace(":", "_").replace("/", "_")
    return EXPERIMENTS_ROOT / f"{args.pipeline}_pipeline_ollama_{safe_model}"


def maybe_run_test_coverage(args, project_path: str) -> None:
    if args.use_test_coverage:
        run_coverage_analysis(project_path)


def run_selected_pipeline(args, smells: list[str], project_path: str, experiments_dir: Path) -> Path:
    """
    Dispatch to the selected pipeline and return the output path.
    """
    if args.pipeline == "haystack":
        document_store = get_document_store()
        return run_rag_pipeline(
            args=args,
            smells=smells,
            document_store=document_store,
            project_path=project_path,
            experiments_dir=experiments_dir,
            deployment_name=args.deployment,
        )

    if args.pipeline == "agent":
        deployment_name = resolve_azure_deployment_name(args.deployment) if args.llm_provider == "azure" else args.deployment
        return run_agent_pipeline(
            args=args,
            smells=smells,
            project_path=project_path,
            experiments_dir=experiments_dir,
            deployment_name=deployment_name,
        )

    raise ValueError(f"Unknown pipeline mode: {args.pipeline!r}")


def main() -> Path:
    start_time = time.perf_counter()

    args = parse_args()
    project_path = get_project_path(args.project_name)

    maybe_run_test_coverage(args, project_path)

    deployment_name = None
    if args.llm_provider == "azure":
        deployment_name = resolve_azure_deployment_name(args.deployment)

    experiments_dir = build_experiments_dir(args, deployment_name=deployment_name)
    output_path = run_selected_pipeline(args, SMELLS, project_path, experiments_dir)

    total_runtime = time.perf_counter() - start_time

    return write_evaluation_report(GROUND_TRUTH_PATH, output_path, args, total_runtime)


if __name__ == "__main__":
    main()