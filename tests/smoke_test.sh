#!/usr/bin/env bash
# smoke_test.sh — Isolated smoke tests for shizen_lec_helper
#
# Tests run in /tmp/slh_test/ so they never touch your production
# ~/.config/shizen_lec_helper/ or ~/Shizenkan/ directories.
#
# Requires: an existing Moodle token at one of the known locations.
# Run `python -m shizen_lec_helper setup` first if you don't have one.
#
# Steps:
#   1. Create isolated environment at /tmp/slh_test/
#   2. Copy an existing Moodle token (read-only)
#   3. Run each CLI command against the isolated env
#   4. Remove /tmp/slh_test/ on exit (trap)

set -euo pipefail

TEST_DIR="/tmp/slh_test"
TEST_CONFIG="$TEST_DIR/config"
TEST_BASE="$TEST_DIR/Shizenkan"

# Prefer lite's own token; fall back to author's legacy shizenkan location.
if [ -f "$HOME/.config/shizen_lec_helper/moodle-token.json" ]; then
    EXISTING_TOKEN="$HOME/.config/shizen_lec_helper/moodle-token.json"
elif [ -f "$HOME/.config/ai-agent/credentials/moodle-token.json" ]; then
    EXISTING_TOKEN="$HOME/.config/ai-agent/credentials/moodle-token.json"
else
    echo "ERROR: No Moodle token found." >&2
    echo "Run 'python -m shizen_lec_helper setup' first." >&2
    exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
    echo "[cleanup] Removing $TEST_DIR"
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

echo "[1/6] Creating isolated test environment at $TEST_DIR"
mkdir -p "$TEST_CONFIG" "$TEST_BASE"

echo "[2/6] Copying Moodle token from $EXISTING_TOKEN"
cp "$EXISTING_TOKEN" "$TEST_CONFIG/moodle-token.json"

echo "[3/6] Generating minimal test config"
cat > "$TEST_CONFIG/config.json" <<EOF
{
  "site_url": "https://campus.shizenkan.ac.jp",
  "base_path": "$TEST_BASE",
  "active_courses": [],
  "download_videos": false,
  "new_course_policy": "ask",
  "notification_format": "markdown"
}
EOF

cd "$SCRIPT_DIR"

# Use env vars to isolate from production config.
# Avoids argparse parent/child conflict with --config-dir flag.
export SLH_CONFIG_DIR="$TEST_CONFIG"
export SLH_BASE_PATH="$TEST_BASE"

echo "[4/6] Test: status"
./run.sh status

echo "[5/6] Test: courses --auto-detect (Moodle API call)"
./run.sh courses --auto-detect

echo "[6/6] Test: sync --dry-run (with one active course)"
# Populate active_courses with one detected course to exercise sync path
python3 <<PYEOF
import json
from pathlib import Path
p = Path("$TEST_CONFIG/config.json")
cfg = json.loads(p.read_text())
cfg["active_courses"] = ["GUIDANCE_EN_2027"]
p.write_text(json.dumps(cfg, indent=2))
PYEOF
./run.sh sync --dry-run

echo ""
echo "All smoke tests passed. Cleaning up..."
