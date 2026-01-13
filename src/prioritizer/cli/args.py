from __future__ import annotations

import argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze and prioritize code smells for a project."
    )

    parser.add_argument(
        "project_name",
        metavar="project",
        help="Name of the project directory (e.g., cerberus)",
    )

    parser.add_argument(
        "--llm-provider",
        choices=["ollama", "azure"],
        default="ollama",
        help="Determines if the pipeline uses a personal azure deployment or ollama.",
        dest="llm_provider"
    )

    parser.add_argument(
        "--ollama-model",
        default="gpt-oss:120b-cloud",
        help="Ollama model to use (only when --llm-provider=ollama).",
        dest="ollama_model"
    )

    parser.add_argument(
        "--azure-deployment",
        help="Azure OpenAI deployment name (only when --llm-provider=azure).",
    )

    parser.add_argument(
        "--pipeline",
        choices=["rag", "agent"],
        default="rag",
        help="Which pipeline to run: 'rag' baseline or 'agent' agentic pipeline.",
    )

    parser.add_argument(
        "--outdir",
        dest="output_dir",
        default="baseline",
        help="Directory where the output files should be stored",
    )

    parser.add_argument(
        "--no-git-stats",
        dest="include_git_stats",
        action="store_false",
        help="Disable Git statistics.",
    )
    parser.set_defaults(include_git_stats=True)

    parser.add_argument(
        "--no-pylint-astroid",
        dest="run_pylint_astroid",
        action="store_false",
        help="Disable static analysis.",
    )
    parser.set_defaults(run_pylint_astroid=True)

    parser.add_argument(
        "--no-articles",
        dest="include_articles",
        action="store_false",
        help="Disable embedding of articles to the LLM.",
    )
    parser.set_defaults(include_articles=True)

    parser.add_argument(
        "--add-project-structure",
        dest="include_project_structure",
        action="store_true",
        help="Add the project folder structure to the prompt.",
    )
    parser.set_defaults(include_project_structure=False)

    parser.add_argument(
        "--persistent-storage",
        dest="persistent_storage",
        action="store_true",
        help="Enable persistent storage of embedded articles to chroma db"
    )
    parser.set_defaults(persistent_storage=False)

    parser.add_argument(
        "--code-context",
        dest="code_context_mode",
        choices=["analysis", "code"],
        default="analysis",
        help="Use AI summaries of code segments or embed the raw code snippets directly."
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)
