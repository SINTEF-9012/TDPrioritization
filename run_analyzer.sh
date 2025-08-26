# !/bin/bash

# Exit on error
set -e 

# Check if the project name was provided
if [ -z "$1" ]; then
    echo "Usage: $0 <project-name> [--model <model>] [--output <file>]"
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_PATH="../projects/$PROJECT_NAME/"

# Shift so $@ contains only the remaining optional args
shift

LAST_PROJECT_FILE=".last_project"

# Check if detector needs to run
if [ -f "$LAST_PROJECT_FILE" ] && [ "$(cat $LAST_PROJECT_FILE)" = "$PROJECT_NAME" ]; then
    echo "Skipping detector - project '$PROJECT_NAME' already analyzed ✅"
else
    echo "Running Python Smells Detector on $PROJECT_PATH ..."
    cd python_smells_detector
    analyze_code_quality "$PROJECT_PATH" --config code_quality_config.yaml
    cd ..
    echo "$PROJECT_NAME" > "$LAST_PROJECT_FILE"   # remember this project
fi

echo "Running Smells Prioritizer ..."
time python3 smells_prioritizer.py "$PROJECT_NAME" "$@"

echo "Analysis and prioritization complete! ✅ "