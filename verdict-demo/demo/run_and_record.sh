#!/usr/bin/env bash
# Run a real regression check and render it as a video for posting.
#
#   ANTHROPIC_API_KEY=... demo/run_and_record.sh [patch] [runs]
#
# Applies the patch (default: demo/subtle-skip-lookup.patch) on a throwaway branch,
# runs `verdict diff` against main, renders out/verdict-demo.mp4 from the result,
# then returns to the branch you were on. Costs real API calls: about
# cases x runs x 2 agent runs plus one judge call per response.
set -euo pipefail

patch="${1:-demo/subtle-skip-lookup.patch}"
runs="${2:-5}"  # 5 runs: a case going 5/5 -> 0/5 is significant on its own
out="out"
branch="verdict-demo-regression-$$"

[[ -n "${ANTHROPIC_API_KEY:-}" ]] || { echo "Set ANTHROPIC_API_KEY first." >&2; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Commit or stash your changes first." >&2; exit 1; }

start="$(git rev-parse --abbrev-ref HEAD)"
cleanup() { git switch -q "$start"; git branch -q -D "$branch" 2>/dev/null || true; }
trap cleanup EXIT

git switch -q -c "$branch" main
git apply "$patch"
git -c user.name="verdict-demo" -c user.email="demo@example.com" commit -qam "demo: $(basename "$patch" .patch)"

mkdir -p "$out"
export DEFAULT_TIMEOUT_SECONDS="${DEFAULT_TIMEOUT_SECONDS:-180}"
set +e
verdict diff --base main --head HEAD --runs "$runs" \
  --json-out "$out/verdict-diff.json" --md-out "$out/verdict-diff.md" 2>&1 | tee "$out/verdict-diff.log"
code=${PIPESTATUS[0]}
set -e
# 0 = gate passed, 2 = gate breached; anything else means the run itself failed.
if [[ "$code" != 0 && "$code" != 2 ]]; then
  echo "verdict diff failed (exit $code); see $out/verdict-diff.log" >&2
  exit "$code"
fi

python demo/make_video.py --diff "$out/verdict-diff.json" --patch "$patch" --out "$out/verdict-demo.mp4"
echo "Result: $out/verdict-diff.md   Video: $out/verdict-demo.mp4"
