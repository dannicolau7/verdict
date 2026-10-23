#!/usr/bin/env bash
# Install verdict-eval and run `verdict diff`. Always exits 0 and reports through
# step outputs (status, passed, json-path, markdown-path); action.yml fails the job.
set -uo pipefail

out_dir="${RUNNER_TEMP:-/tmp}/verdict"
mkdir -p "$out_dir"
json="$out_dir/verdict-diff.json"
md="$out_dir/verdict-diff.md"
rm -f "$json" "$md"  # never report a previous run's result
gh_out="${GITHUB_OUTPUT:-/dev/null}"

finish() {  # status passed
  {
    echo "status=$1"
    echo "passed=$2"
    [[ -f "$json" ]] && echo "json-path=$json"
    [[ -f "$md" ]] && echo "markdown-path=$md"
  } >> "$gh_out"
  exit 0
}

if [[ -z "${VERDICT_BASE:-}" ]]; then
  echo "::error title=Verdict::No base ref. Run on pull_request events or set the 'base' input."
  finish error false
fi

if [[ "${VERDICT_VERSION:-latest}" == "latest" ]]; then
  pkg="verdict-eval"
elif [[ "$VERDICT_VERSION" == */* ]]; then
  pkg="$VERDICT_VERSION"  # a path or URL, e.g. git+https://github.com/dannicolau7/verdict@main
else
  pkg="verdict-eval==${VERDICT_VERSION}"
fi
echo "::group::Install $pkg"
python -m pip install --quiet --disable-pip-version-check "$pkg" || {
  echo "::endgroup::"
  echo "::error title=Verdict::pip install $pkg failed."
  finish error false
}
echo "::endgroup::"

# verdict diff needs history back to the merge base of base and head.
if [[ "$(git rev-parse --is-shallow-repository 2>/dev/null)" == "true" ]]; then
  echo "Shallow clone detected; fetching full history (or set fetch-depth: 0 on actions/checkout)."
  git fetch --no-tags --quiet --unshallow origin || true
fi
for ref in "$VERDICT_BASE" "$VERDICT_HEAD"; do
  if ! git cat-file -e "${ref}^{commit}" 2>/dev/null; then
    git fetch --no-tags --quiet origin "$ref" || true
  fi
done

if [[ -n "${INPUT_ANTHROPIC_API_KEY:-}" ]]; then
  export ANTHROPIC_API_KEY="$INPUT_ANTHROPIC_API_KEY"
fi

args=(diff --base "$VERDICT_BASE" --head "$VERDICT_HEAD" --config "$VERDICT_CONFIG"
      --json-out "$json" --md-out "$md")
[[ -n "${VERDICT_RUNS:-}" ]] && args+=(--runs "$VERDICT_RUNS")

verdict "${args[@]}"
code=$?

if [[ -f "$md" && -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat "$md" >> "$GITHUB_STEP_SUMMARY"
fi

case "$code" in
  0)
    status=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$json" 2>/dev/null || echo completed)
    finish "$status" true ;;
  2) finish completed false ;;
  *) finish error false ;;
esac
