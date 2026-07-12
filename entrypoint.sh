#!/usr/bin/env bash
# ZeroProof container entrypoint.
# Runs the agent, which reads /input/tasks.json and writes /output/results.json.
# The agent is engineered to always exit 0 with a valid, complete output file.
set -u
export PYTHONPATH="/app/src:${PYTHONPATH:-}"
export ZP_MODEL_PATH="${ZP_MODEL_PATH:-/models/model.gguf}"
exec python -m zeroproof.main
