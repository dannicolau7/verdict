#!/usr/bin/env bash
# Scripted demo for asciinema recording.
#
# Usage:
#   python -m asciinema rec docs/demo.cast --command ./scripts/demo.sh
#
# Prerequisites:
#   pip install verdict-eval
#   export ANTHROPIC_API_KEY=sk-ant-...

set -euo pipefail

PAUSE_SHORT=1.5
PAUSE_LONG=3.0

# ── helpers ────────────────────────────────────────────────────────────────────

type_cmd() {
    printf '\n\033[1;32m$\033[0m '
    local text="$1"
    for ((i=0; i<${#text}; i++)); do
        printf '%s' "${text:$i:1}"
        sleep 0.05
    done
    echo
}

pause() { sleep "${1:-$PAUSE_SHORT}"; }

run() {
    type_cmd "$1"
    pause 0.3
    eval "$1"
    pause "${2:-$PAUSE_SHORT}"
}

# ── demo ───────────────────────────────────────────────────────────────────────

clear
echo ""
echo "  Verdict — evaluation infrastructure for AI agents"
echo "  github.com/dannicolau7/verdict"
echo ""
pause 2

# 1. Help
run "verdict --help" 1

# 2. Run a quick eval (2 prompts per category = 10 total)
run "verdict eval --target simple_rag --num-per-category 2 --output-dir /tmp/verdict-demo" $PAUSE_LONG

# 3. Show report files
run "ls /tmp/verdict-demo/" 1

# 4. Summary from JSON report
run "python3 -c \"
import json, glob
f = sorted(glob.glob('/tmp/verdict-demo/*.json'))[-1]
r = json.load(open(f))
print(f\\\"Pass rate  : {r['pass_rate']:.1%}\\\")
print(f\\\"Tests run  : {r['total_tests']}\\\")
print(f\\\"Categories : {list(r['category_breakdown'].keys())}\\\")
\"" $PAUSE_SHORT

# 5. Markdown report header
run "head -25 \$(ls /tmp/verdict-demo/*.md | tail -1)" $PAUSE_SHORT

echo ""
echo "  Done!  pip install verdict-eval"
echo ""
pause 2
