"""Flakiness detection across historical Verdict evaluation runs.

Reads all EvalReport JSON files in a directory for a given target_system,
then computes:

1. Judge flakiness: prompts where the pass/fail verdict differs across runs.
   A prompt is "flaky" if its disagreement_rate > FLAKY_THRESHOLD (0.10).

2. Target flakiness: prompts where the response changes across runs.
   v0.1 uses exact-match comparison (same prompt_text → same response?).
   v0.2 (future): semantic similarity via embeddings.

Schema tolerance:
    Older reports that fail to deserialize are skipped with a warning, so
    schema drift between Verdict versions doesn't crash the analysis.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Prompts with judge disagreement above this rate are flagged as flaky
FLAKY_THRESHOLD = 0.10


def analyze_flakiness(
    report_dir: Path,
    target_system: str,
    min_runs: int = 3,
) -> dict | None:
    """Analyze historical run variance for a target system.

    Args:
        report_dir:    Directory containing {run_id}.json report files.
        target_system: EvalReport.target_system value to filter on.
        min_runs:      Minimum number of matching reports required.
                       Returns None if fewer are found.

    Returns:
        Flakiness report dict matching EvalReport.flakiness_report schema,
        or None if not enough historical data.
    """
    reports = _load_reports(report_dir, target_system)
    if len(reports) < min_runs:
        logger.info(
            "Flakiness analysis skipped: only %d runs found for %r (need %d).",
            len(reports), target_system, min_runs,
        )
        return None

    logger.info("Analyzing flakiness across %d runs for %r.", len(reports), target_system)

    # ------------------------------------------------------------------ #
    # Build per-prompt history: {prompt_id: [{"passed": bool, "response": str}, ...]}
    # ------------------------------------------------------------------ #
    # We key on prompt_id across runs.  Same prompt_id across runs means
    # it was the same generated test prompt (reproducible generation or reuse).
    pass_history: dict[str, list[bool]] = {}
    response_history: dict[str, list[str]] = {}
    prompt_categories: dict[str, str] = {}

    for report in reports:
        judgments = report.get("judgments", [])
        cat_breakdown = report.get("category_breakdown", {})

        for j in judgments:
            pid = j.get("prompt_id", "")
            passed = bool(j.get("passed", False))
            if pid not in pass_history:
                pass_history[pid] = []
                response_history[pid] = []
            pass_history[pid].append(passed)
            # Response is not in Judgment — note it as unavailable
            response_history[pid].append(j.get("metadata", {}).get("response_excerpt", ""))

        # Try to get category from breakdown keys (approximate)
        for cat in cat_breakdown:
            for pid in pass_history:
                if pid not in prompt_categories:
                    prompt_categories[pid] = cat

    # ------------------------------------------------------------------ #
    # Judge flakiness                                                      #
    # ------------------------------------------------------------------ #
    flaky_judge_prompts = []
    consistency_scores = []

    for pid, history in pass_history.items():
        if len(history) < 2:
            continue
        n = len(history)
        n_pass = sum(history)
        # Disagreement = fraction of minority votes
        majority_count = max(n_pass, n - n_pass)
        disagree_rate = round(1.0 - majority_count / n, 4)
        consistency_scores.append(1.0 - disagree_rate)

        if disagree_rate > FLAKY_THRESHOLD:
            flaky_judge_prompts.append({
                "prompt_id": pid,
                "category": prompt_categories.get(pid, "unknown"),
                "disagreement_rate": disagree_rate,
                "n_runs": n,
                "pass_count": n_pass,
                "fail_count": n - n_pass,
            })

    flaky_judge_prompts.sort(key=lambda x: x["disagreement_rate"], reverse=True)
    overall_judge_consistency = (
        round(sum(consistency_scores) / len(consistency_scores), 4)
        if consistency_scores else 1.0
    )

    # ------------------------------------------------------------------ #
    # Target flakiness (v0.1: exact-match on response_excerpt)            #
    # ------------------------------------------------------------------ #
    flaky_target_prompts = []

    for pid, responses in response_history.items():
        non_empty = [r for r in responses if r]
        if len(non_empty) < 2:
            continue
        unique_responses = len(set(non_empty))
        has_variance = unique_responses > 1
        if has_variance:
            flaky_target_prompts.append({
                "prompt_id": pid,
                "response_variance": "high" if unique_responses / len(non_empty) > 0.5 else "low",
                "n_runs": len(non_empty),
                "unique_responses": unique_responses,
            })

    overall_target_consistency = (
        round(1.0 - len(flaky_target_prompts) / max(len(pass_history), 1), 4)
    )

    return {
        "min_runs_analyzed": len(reports),
        "judge_flakiness": {
            "flaky_prompts": flaky_judge_prompts,
            "overall_judge_consistency": overall_judge_consistency,
        },
        "target_flakiness": {
            "flaky_prompts": flaky_target_prompts,
            "overall_target_consistency": overall_target_consistency,
        },
    }


def _load_reports(report_dir: Path, target_system: str) -> list[dict]:
    """Load all EvalReport JSONs for target_system, skipping malformed files."""
    reports = []
    report_dir = Path(report_dir)
    if not report_dir.exists():
        return reports

    for f in sorted(report_dir.glob("*.json")):
        if f.name.startswith("diff_"):
            continue  # skip DiffReport files
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("target_system") == target_system:
                reports.append(data)
        except Exception as exc:
            logger.warning("Skipping %s: %s", f.name, exc)

    return reports
