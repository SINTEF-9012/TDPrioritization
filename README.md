# python-smells-prioritizer

This project is part of a master thesis investigating how AI techniques, such as **Retrieval-Augmented Generation (RAG)**, can be used to improve **technical debt prioritization**. The goal is to explore whether large language models in combination with static code analysis, some repository mining and other related AI techniques can provide better insights and prioritization strategies for managing technical debt in source code.

## Project structure
python-smells-prioritizer/
│
├── smells_prioritizer.py         # Main RAG-based prioritization pipeline
├── chunking.py                   # Document chunking for embeddings
├── utils/                        # Helper functions for metrics & Git analysis
├── requirements.txt              # Dependency list
├── run_analyzer.sh               # Entry-point shell script
└── README.md


## Requirements

- Python 3.11+
- A recent version of **pip** (`pip install --upgrade pip`)
- Internet access for downloading necessary dependencies
- Python_smells_detector (A seprate project that must be cloned from `https://github.com/KarthikShivasankar/python_smells_detector`)

## Installation

Follow these steps to set up and run the project in a Python virtual environment.

### Clone the repository

```bash
git clone git@github.uio.no:jasuhany/python-smells-prioritizer.git
cd python-smells-prioritizer
```

### Create a virtual environment

#### MacOs/Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows
```bash
python -m venv venv
.\venv\Scripts\activate
```

## Install necessary dependencies and packages:
```bash
pip install -r requirements.txt
```

## Create a projects folder
Create a projects folder where you will copy the python code base you wish to analyze. 

```bash
mkdir projects
```

## Example of how to run from project folder:
```bash
bash run_analyzer.sh text_classification --model gpt-oss:20b-cloud --git_stats
```
