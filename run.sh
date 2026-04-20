#!/usr/bin/env bash
# run.sh — CLI wrapper for shizenkan-lite
#
# Usage:
#   ./run.sh sync
#   ./run.sh sync --dry-run
#   ./run.sh deadlines
#   ./run.sh status
#   ./run.sh courses --auto-detect
#   ./run.sh setup
#
# This script resolves the Python interpreter and PYTHONPATH automatically,
# so it works whether you use a venv, uv, or plain system Python.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Resolve Python interpreter ---
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif command -v uv &>/dev/null; then
    # uv will use the project's managed Python
    PYTHON="uv run python"
else
    PYTHON="python3"
fi

# --- Run ---
export PYTHONPATH="$SCRIPT_DIR/src:${PYTHONPATH:-}"
exec $PYTHON -m shizenkan_lite "$@"
