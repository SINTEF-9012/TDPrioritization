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
        choices=["gpt-3.5", "codex"],
        dest="deployment",
        default="gpt-3.5",
        help="Azure OpenAI deployment name (only when --llm-provider=azure).",
    )

    parser.add_argument(
        "--pipeline",
        choices=["haystack", "agent"],
        default="haystack",
        help="Which pipeline to run: 'haystack' or 'agent' pipeline.",
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
        choices=["analysis", "code", "none"],
        default="analysis",
        help="Use AI summaries of code segments or embed the raw code snippets directly."
    )

    parser.add_argument(
        "--rag",
        dest="use_rag",
        action="store_true",
        help="Use rag to retrieve additional contextual information from scientific journals.",
    )
    parser.set_defaults(use_rag=False)

    parser.add_argument(
        "--test-coverage",
        dest="use_test_coverage",
        action="store_true",
        help="Measure test coverage and use it as context for the llm.",
    )
    parser.set_defaults(use_rag=False)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)

# TODO No code or analysis option