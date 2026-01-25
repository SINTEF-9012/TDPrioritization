# python-smells-prioritizer

This project is part of a master thesis investigating how AI techniques, such as **Retrieval-Augmented Generation (RAG)**, can be used to improve **technical debt prioritization**. The goal is to explore whether large language models in combination with static code analysis, repository mining and other related AI techniques can provide better insights and prioritization strategies for managing technical debt in source code.

## Requirements

- Python **3.11+**
- A recent version of `pip` (`pip install --upgrade pip`)
- Internet access (for dependency downloads and optional cloud-based LLMs)
- Git (required if repository mining is enabled)
- An external static analysis tool: **python_smells_detector**

## Installation

Follow these steps to set up and run the project in a Python virtual environment.

### Clone the repository and navigate to the project directory
```bash
git clone <repository-url>
cd python-smells-prioritizer
```

### Create a virtual environment

#### MacOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows
```bash
python -m venv venv
.\venv\Scripts\activate
```

### External dependency: python_smells_detector

This project depends on an external static analysis tool for detecting Python code smells.

Clone into the project directory and install it **in the same virtual environment**:

```bash
git clone https://github.com/KarthikShivasankar/python_smells_detector.git
cd python_smells_detector
pip install -e .
```

### Install necessary dependencies and packages:
```bash
pip install -r requirements.txt

pip install -e .
```

### Model configuration

The analyzer supports both **local** and **cloud-based** LLM providers. Depending on the selected model, additional configuration may be required.

#### Ollama (local models)

- Install and start Ollama separately
- Ensure the selected model is pulled and available

Example:
```bash
ollama pull gpt-oss:20b-cloud
```

#### Azure OpenAI (optional)

If using Azure OpenAI models, configure the following environment variables:

- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_DEPLOYMENT_NAME

## Preparing projects for analysis
Create a folder containing the Python projects you want to analyze:

```bash
mkdir test_projects
```

Each project:
- Should be a valid Python code base
- Should be a Git repository if the --git_stats option is enabled

Place one or more projects inside the test_projects/ directory.

## Running the analyzer
The main entry point is the run_analyzer.sh script.

**Basic usage:**
```bash
bash run_analyzer.sh <mode> [options]
```

**Example:**
```bash
bash run_analyzer.sh text_classification --model gpt-oss:20b-cloud --git_stats
```

**Common options:**
- `<project>`: name of the project to be analyzed and prioritized (e.g., `text_classification`).
- `--llm-provider`: The name of the framework used for deploying models (`ollama` or `azure`).
- `--model`: LLM model identifier. The model name passed to --model must correspond to an available local or remote model.
- `--git_stats`: Enable repository mining and Git-based metrics

Available modes and options may evolve as part of ongoing thesis work.
