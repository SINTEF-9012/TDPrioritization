# python-smells-prioritizer

This project is part of a master’s thesis investigating whether **large language models (LLMs)** can support **technical debt prioritization** by ranking detected code smells when supplied with relevant contextual information.

The artifact combines code smell detection with configurable contextual signals, including:

- Static-analysis information
- Repository-mining and Git-based metrics
- Retrieved background knowledge through **Retrieval-Augmented Generation (RAG)**
- Test coverage information
- Source-code context or AI-generated code summaries

The goal is to explore whether these contextual additions improve the quality of LLM-generated code smell prioritizations.

---

## Requirements

- Python **3.11 or 3.12**
- A recent version of `pip`
- Internet access for dependency downloads and, when applicable, cloud-based LLM usage
- Git, if repository mining is enabled
- An external static-analysis tool: [`python_smells_detector`](https://github.com/KarthikShivasankar/python_smells_detector)

---

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
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows
```bash
python3 -m venv .venv
.\.venv\Scripts\activate
```

### External dependency: python_smells_detector

This project depends on an external static analysis tool for detecting Python code smells.

Clone into the project directory and install it **in the same virtual environment**:

```bash
git clone https://github.com/KarthikShivasankar/python_smells_detector.git
cd python_smells_detector
pip install -e .
cd ..
```

### Install project dependencies and the artifact

```bash
pip install -r requirements.txt
pip install -e .
```

### Model configuration

The artifact supports LLMs accessed through **Ollama** and **Azure OpenAI**. Depending on the selected provider and model, additional configuration may be required.

#### Ollama

- Install and start Ollama separately
- Ensure the selected model is pulled and available

Example:
```bash
ollama pull <model-name>
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

The artifact can be executed either as a **single prioritization run** or as a **repeated experiment** across one or more configurations.

---

### Running a single prioritization

The main entry point for a single run is the `run_prioritizer.sh` script.

**Basic usage:**
```bash
bash run_prioritizer.sh <project> [options]
```

**Common options:**
| Option                                     | Description                                                             |
| ------------------------------------------ | ----------------------------------------------------------------------- |
| `<project>`                                | Name of the project to be analyzed and prioritized                      |
| `--llm-provider`                           | LLM backend to use, such as `ollama` or `azure`                         |
| `--pipeline`                               | Pipeline implementation to run, such as the agent-based pipeline        |
| `--model`                                  | Model identifier for the selected provider                              |
| `--azure-deployment`                       | Azure OpenAI deployment name, when using the Azure provider             |
| `--git-stats` / `--no-git-stats`           | Enable or disable repository-mining and Git-based metrics               |
| `--pylint-astroid` / `--no-pylint-astroid` | Enable or disable Pylint/Astroid-based static-analysis context          |
| `--code-context`                           | Select the code-context strategy, such as `none`, `code`, or `analysis` |
| `--test-coverage`                          | Include test coverage information                                       |
| `--rag`                                    | Include retrieved background knowledge through RAG                      |
| `--out-dir`                                | Name of the output directory used to store results for the run          |

**Example:**
```bash
bash run_prioritizer.sh simapy \
    --llm-provider ollama \
    --pipeline agent \
    --code-context analysis \
    --test-coverage \
    --rag \
    --out-dir simapy_analysis_rag
```

Available modes and options may evolve as part of ongoing thesis work.

### Running repeated experiments

The `run_experiments.sh` script can be used to execute the artifact repeatedly with a selected configuration. This is useful for collecting multiple runs of the same setup and generating aggregated statistics afterward.

Run the script with:

```bash
bash run_experiments.sh
```

Before execution, the script can be edited to control:

- `N`: the number of repeated runs
- The project being analyzed
- The LLM provider and pipeline
- Which contextual signals are enabled
- The output directory used for storing results

For example, the following configuration runs the agent pipeline on the `simapy` project using Ollama, AI-generated code analysis, test coverage, and RAG:

```bash
N=5

for ((i=1; i<=N; i++)); do
    echo "[INFO] Running experiment $i of $N"

    bash run_prioritizer.sh simapy \
        --llm-provider ollama \
        --pipeline agent \
        --code-context analysis \
        --test-coverage \
        --rag \
        --out-dir pylint_analysis_rag

    sleep 1
done

python3 src/prioritizer/evaluation/statistics_collector.py
```

After the repeated runs are completed, the script invokes:

```bash
python3 src/prioritizer/evaluation/statistics_collector.py
```

This aggregates the generated evaluation outputs and produces summary statistics for the completed experiment runs.


## Outputs

Each execution stores generated artifacts in the configured experiment/output directory. Outputs include:

- The constructed prompt for the LLM
- The LLM-generated output
- Evaluation reports containing metrics, runtime information, and configuration metadata

## Notes
- The artifact is intended as a research prototype developed for thesis experimentation.
- Available modes, providers, and configuration options may evolve during continued development.
- For reproducible use, ensure that the Python version and installed dependencies match the project configuration.
