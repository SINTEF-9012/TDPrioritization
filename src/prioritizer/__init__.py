"""
prioritizer
===========

Core package for technical-debt prioritization based on code smells, static analysis,
evolutionary (git) signals, and LLM-based reasoning. The package exposes two main
pipelines:

- Baseline RAG prioritization
- Agentic (tool-using) prioritization

Most users will interact with a prioritizer implementation rather than importing
the underlying modules directly.
"""

from importlib.metadata import version

# Expose version if package is installed
try:
    __version__ = version("prioritizer")
except Exception:
    __version__ = "0.0.0"

__all__ = [
    "analysis",
    "history",
    "ingestion",
    "llm",
    "pipelines",
    "evaluation",
    "cli"
]