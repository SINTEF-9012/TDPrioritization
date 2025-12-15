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
        "--model",
        dest="model_name",
        default="gpt-oss:20b-cloud",
        help="Which Ollama LLM model to use",
    )
    parser.add_argument(
        "--outdir",
        dest="output_dir",
        default="baseline",
        help="Directory where the output files should be stored",
    )

    parser.add_argument(
        "--git-stats",
        dest="include_git_stats",
        action="store_true",
        help="Include Git statistics in the context.",
    )
    parser.add_argument(
        "--no-git-stats",
        dest="include_git_stats",
        action="store_false",
        help="Disable Git statistics.",
    )
    parser.set_defaults(include_git_stats=True)

    parser.add_argument(
        "--pylint-astroid",
        dest="run_pylint_astroid",
        action="store_true",
        help="Perform static analysis using pylint and astroid.",
    )
    parser.add_argument(
        "--no-pylint-astroid",
        dest="run_pylint_astroid",
        action="store_false",
        help="Disable static analysis.",
    )
    parser.set_defaults(run_pylint_astroid=True)

    parser.add_argument(
        "--articles",
        dest="include_articles",
        action="store_true",
        help="Enable embedded articles to the LLM.",
    )
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

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)
