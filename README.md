# python-smells-prioritizer

This project is part of a master thesis investigating how AI tools, such as **Retrieval-Augmented Generation (RAG)**, can be used to improve **technical debt prioritization**.  
The goal is to explore whether large language models and related AI techniques can provide better insights and prioritization strategies for managing technical debt in source code.

## Requirements

- Python 3.11+
- [haystack-ai](https://github.com/deepset-ai/haystack) (v2, requires Pydantic v2)
- [GitPython](https://gitpython.readthedocs.io/)

## Installation

Create and activate a virtual environment, then install the dependencies:

```bash
pip install haystack-ai
pip install gitpython
pip install --upgrade "pydantic>=2.0.0"
