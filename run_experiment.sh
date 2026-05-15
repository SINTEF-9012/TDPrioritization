#!/bin/bash

# Exit immediately if any command fails
set -e

# -------------------------------------------------------------------
# Experiment settings
# -------------------------------------------------------------------

# Number of times the same experiment configuration should be repeated
N=5

# Name of the project under test_projects/
PROJECT="simapy"

# Output folder name for this experiment configuration
OUT_DIR="baseline"

# -------------------------------------------------------------------
# Available configuration flags
# -------------------------------------------------------------------
#
# LLM provider:
#   --llm-provider ollama
#   --llm-provider azure
#
# Pipeline:
#   --pipeline agent
#   --pipeline haystack
#
# Model selection:
#   --model <ollama-model-name>
#   --azure-deployment <azure-deployment-name>
#
# Repository-mining context:
#   --git-stats
#   --no-git-stats
#
# Static-analysis context:
#   --pylint-astroid
#   --no-pylint-astroid
#
# Code context:
#   --code-context none
#   --code-context code
#   --code-context analysis
#
# Additional contextual signals:
#   --test-coverage
#   --rag
#
# Output:
#   --out-dir <folder-name>
#
# -------------------------------------------------------------------
# Prioritizer configuration
# -------------------------------------------------------------------
# Edit these flags to define the experiment setup.

FLAGS=(
    --llm-provider azure
    --pipeline haystack
    --code-context none
    --no-pylint-astroid
    --no-git-stats
)

echo "[INFO] Starting experiment"
echo "[INFO] Project: $PROJECT"
echo "[INFO] Repetitions: $N"
echo


# Store the directory containing the generated evaluation reports
EVALUATION_DIR=""

for ((i=1; i<=N; i++)); do
    echo "[INFO] Running experiment $i of $N"

    RUN_OUTPUT=$(
        bash run_prioritizer.sh "$PROJECT" \
            "${FLAGS[@]}" \
            --out-dir "$OUT_DIR" \
            | tee /dev/tty
    )

    CURRENT_EVALUATION_DIR=$(
        echo "$RUN_OUTPUT" \
            | grep '^EVALUATION_DIR=' \
            | tail -n 1 \
            | cut -d'=' -f2-
    )

    if [[ -z "$CURRENT_EVALUATION_DIR" ]]; then
        echo "[ERROR] Could not determine evaluation directory from prioritizer output."
        exit 1
    fi

    if [[ -z "$EVALUATION_DIR" ]]; then
        EVALUATION_DIR="$CURRENT_EVALUATION_DIR"
    fi

    echo "[INFO] Evaluation directory: $CURRENT_EVALUATION_DIR"
    echo "[INFO] Completed experiment $i of $N"
    echo

    sleep 1
done

# -------------------------------------------------------------------
# Aggregate statistics
# -------------------------------------------------------------------

echo "[INFO] Collecting experiment statistics"

python src/prioritizer/evaluation/statistics_collector.py "$EVALUATION_DIR"

echo "[INFO] Experiment completed successfully"
