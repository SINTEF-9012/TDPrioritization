#!/bin/bash

# Exit on error
set -e 

if [ -z "$1" ]; then
    echo "Usage: $0 <project-name> [--model <model>] [--output <file>]"
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_PATH="../test_projects/$PROJECT_NAME/"

# Shift so $@ contains only the remaining optional args
shift

LAST_PROJECT_FILE=".last_project"

if [ -f "$LAST_PROJECT_FILE" ] && [ "$(cat $LAST_PROJECT_FILE)" = "$PROJECT_NAME" ]; then
    echo "[INFO] Skipping detector - project '$PROJECT_NAME' already analyzed."
else
    echo "[INFO] Running Python Smells Detector on $PROJECT_NAME ..."
    cd python_smells_detector
    analyze_code_quality "$PROJECT_PATH" --config code_quality_config.yaml
    cd ..
    echo "$PROJECT_NAME" > "$LAST_PROJECT_FILE"
fi

echo "[INFO] Running smells prioritizer ..."
python -m prioritizer "$PROJECT_NAME" "$@"

echo -e "[DONE] Analysis and prioritization complete!\n"
