#!/bin/bash

# Exit on error
set -e

N=1

CONFIGS=(
  "--llm-provider ollama --pipeline agent --no-git-stats --no-pylint-astroid --code-context none --out-dir baseline"
)

: << 'COMMENT'    
FLAGS:   
--llm-provider azure \
--pipeline agent \
--azure-deployment o4-mini \
--no-git-stats \
--no-pylint-astroid \
--code-context code \
--test-coverage \
--out-dir code_segment
--rag
COMMENT

for((i=1; i<=N; i++)); do
    echo "[INFO] Running experiment $i of $N" 
    bash run_prioritizer.sh simapy \
        --llm-provider ollama \
        --pipeline agent \
        --code-context analysis \
        --no-git-stats \
        --out-dir pylint_analysis \

    sleep 1
done

python3 src/prioritizer/evaluation/statistics_collector.py