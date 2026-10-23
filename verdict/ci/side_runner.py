"""Execute a suite N times against one checkout of the target. Runs in a subprocess.

`verdict diff` launches this once per side with the checkout as the working directory,
so the adapter (and anything it imports or reads, e.g. prompts/) comes from that ref
and the two sides never share a module cache:

    python -P -m verdict.ci.side_runner --target agent.py:Agent --suite /abs/core.jsonl \\
        --runs 10 --out /tmp/side.json

Output JSON: {"adapter": str, "version": str, "runs": [[ExecutionResult, ...], ...]}
with runs[r][i] the result of case i on run r. Judging happens in the parent process
so both sides are scored by the same judge.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verdict.ci.side_runner")
    parser.add_argument("--target", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    # Import verdict before exposing the checkout on sys.path, so a checkout that
    # happens to contain a `verdict/` directory cannot shadow the installed package.
    from verdict.agents.executor import execute_test_suite
    from verdict.ci.suite import load_suite
    from verdict.cli import _load_adapter

    sys.path.insert(0, os.getcwd())

    cases = load_suite(args.suite)
    adapter = _load_adapter(args.target)
    batch = [case for _ in range(args.runs) for case in cases]
    results = asyncio.run(execute_test_suite(batch, adapter))

    n = len(cases)
    runs = [
        [r.model_dump(mode="json") for r in results[i * n : (i + 1) * n]] for i in range(args.runs)
    ]
    Path(args.out).write_text(
        json.dumps({"adapter": adapter.name, "version": adapter.version, "runs": runs}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
