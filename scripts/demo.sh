#!/usr/bin/env bash
# Scripted demo for asciinema recording.
#
# Usage:
#   asciinema rec docs/demo.cast --command ./scripts/demo.sh
#
# Prerequisites:
#   pip install verdict-eval
#   export ANTHROPIC_API_KEY=sk-ant-...
#
# The script uses `pv` (pipe viewer) to simulate typing speed.
# Install: brew install pv  /  apt-get install pv

set -euo pipefail

DELAY=0.04          # seconds between typed characters
PAUSE_SHORT=1.5     # short pause after a command
PAUSE_LONG=2.5      # long pause before big results

# ── helpers ────────────────────────────────────────────────────────────────────

type_cmd() {
    # Print the PS1 prompt, then "type" the command character-by-character
    printf '\n\033[1;32m$\033[0m '
    echo -n "$1" | pv -qL 80  # ~80 chars/sec ≈ fast typist
    echo
}

pause() {
    sleep "${1:-$PAUSE_SHORT}"
}

run() {
    type_cmd "$1"
    pause 0.4
    eval "$1"
    pause "${2:-$PAUSE_SHORT}"
}

# ── demo body ──────────────────────────────────────────────────────────────────

clear

echo ""
echo "  Verdict — evaluation infrastructure for AI agents"
echo "  https://github.com/dannicolau7/verdict"
echo ""
pause 2

# 1. Show installed version
run "verdict --version" 1

# 2. Run a quick eval (2 prompts per category = 10 total)
run "verdict eval --target simple_rag --num-per-category 2 --output-dir /tmp/verdict-demo" $PAUSE_LONG

# 3. Show the generated report directory
run "ls /tmp/verdict-demo/" 1

# 4. Print pass-rate summary from the JSON report
run "python3 -c \"
import json, glob
report_file = sorted(glob.glob('/tmp/verdict-demo/*.json'))[-1]
r = json.load(open(report_file))
print(f\\\"Pass rate  : {r['pass_rate']:.1%}\\\")
print(f\\\"Tests run  : {r['total_tests']}\\\")
print(f\\\"Categories : {list(r['category_breakdown'].keys())}\\\")
\"" $PAUSE_SHORT

# 5. Show the markdown report header
run "head -30 \$(ls /tmp/verdict-demo/*.md | tail -1)" $PAUSE_SHORT

# 6. Run a diff between two configs (same adapter as both sides for demo)
run "verdict diff --target-a simple_rag --target-b simple_rag --num 4" $PAUSE_LONG

echo ""
echo "  Done!  Reports written to /tmp/verdict-demo/"
echo "  Install: pip install verdict-eval"
echo ""
pause 2
