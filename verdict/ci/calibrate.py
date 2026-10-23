"""`verdict calibrate`: how well does the judge agree with human labels?

Runs the judge over human-labeled (prompt, response) pairs and reports Cohen's κ
(with a bootstrap CI), raw agreement, the pass/fail confusion matrix, precision and
recall of failure detection per rubric (category) and per failure mode, and every
disagreement. Fails (exit 2) when κ < min_kappa.

Label files — JSONL (one object per line) or a JSON array — in either shape:

    flat:   {"id": "refund-1", "prompt": "...", "response": "...",
             "expected_behavior": "...", "category": "correctness",
             "label": "fail", "failure_mode": "hallucination", "borderline": false}
            (`passed: true|false` may replace `label`; category, severity,
             failure_mode and borderline are optional)
    nested: {"id": ..., "test_prompt": {...}, "execution_result": {...},
             "ground_truth": {"passed": ..., "failure_mode": ...}}
            (the format of tests/qa/judge_calibration.json)

Borderline examples are judged and listed but excluded from κ and agreement.
Judge errors are excluded too, and counted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from verdict.ci.diff import JudgeFn, _verdict_version, llm_judge
from verdict.models.schemas import ExecutionResult, Judgment, TestPrompt
from verdict.stats.agreement import cohen_kappa, kappa_bootstrap_ci, precision_recall

PASS = "pass"
UNSPECIFIED = "unspecified"


class LabelError(ValueError):
    """Raised when the label file is missing or malformed."""


class LabeledExample(BaseModel):
    id: str
    prompt: TestPrompt
    result: ExecutionResult
    human_passed: bool
    human_failure_mode: str | None = None
    borderline: bool = False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _parse_passed(raw: dict[str, Any], where: str) -> bool:
    if "passed" in raw:
        if not isinstance(raw["passed"], bool):
            raise LabelError(f"{where}: 'passed' must be true or false")
        return raw["passed"]
    label = str(raw.get("label", "")).strip().lower()
    if label in ("pass", "passed", "true"):
        return True
    if label in ("fail", "failed", "false"):
        return False
    raise LabelError(f"{where}: needs 'label' (pass|fail) or 'passed' (true|false)")


def _example(raw: object, where: str) -> LabeledExample:
    if not isinstance(raw, dict):
        raise LabelError(f"{where}: each example must be a JSON object")
    try:
        if "test_prompt" in raw:
            gt = raw.get("ground_truth") or {}
            prompt = TestPrompt(**raw["test_prompt"])
            result = ExecutionResult(**{**raw["execution_result"], "prompt_id": prompt.id})
            passed = _parse_passed(gt, where)
            mode = gt.get("failure_mode")
            ex_id = str(raw.get("id") or prompt.id)
        else:
            ex_id = str(raw.get("id") or "")
            if not ex_id:
                raise LabelError(f"{where}: 'id' is required")
            for key in ("prompt", "response", "expected_behavior"):
                if not isinstance(raw.get(key), str) or not raw[key]:
                    raise LabelError(f"{where}: '{key}' is required")
            prompt = TestPrompt(
                id=ex_id,
                prompt=raw["prompt"],
                expected_behavior=raw["expected_behavior"],
                category=raw.get("category", "correctness"),
                severity=raw.get("severity", "medium"),
            )
            result = ExecutionResult(prompt_id=ex_id, response=raw["response"], latency_ms=0.0)
            passed = _parse_passed(raw, where)
            mode = raw.get("failure_mode")
    except ValidationError as exc:
        raise LabelError(f"{where}: {exc}") from exc
    return LabeledExample(
        id=ex_id,
        prompt=prompt,
        result=result,
        human_passed=passed,
        human_failure_mode=None if passed else mode,
        borderline=bool(raw.get("borderline", False)),
    )


def load_labels(path: str | Path) -> list[LabeledExample]:
    p = Path(path)
    if not p.is_file():
        raise LabelError(f"label file not found: {p}")
    text = p.read_text(encoding="utf-8")
    rows: list[tuple[object, str]] = []
    if text.lstrip().startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LabelError(f"{p}: invalid JSON: {exc}") from exc
        rows = [(raw, f"{p}[{i}]") for i, raw in enumerate(data)]
    else:
        for lineno, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                rows.append((json.loads(s), f"{p}:{lineno}"))
            except json.JSONDecodeError as exc:
                raise LabelError(f"{p}:{lineno}: invalid JSON: {exc}") from exc

    examples = [_example(raw, where) for raw, where in rows]
    if not examples:
        raise LabelError(f"label file {p} has no examples")
    seen: set[str] = set()
    for ex in examples:
        if ex.prompt.id in seen:
            raise LabelError(f"{p}: duplicate example id {ex.prompt.id!r}")
        seen.add(ex.prompt.id)
    return examples


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class ItemResult(BaseModel):
    id: str
    category: str
    human_passed: bool
    judge_passed: bool | None
    human_failure_mode: str | None = None
    judge_failure_mode: str | None = None
    borderline: bool = False
    judge_error: bool = False
    judge_reasoning: str = ""

    @property
    def scored(self) -> bool:
        return not self.borderline and not self.judge_error

    @property
    def agree(self) -> bool:
        return self.judge_passed == self.human_passed


class GroupStats(BaseModel):
    name: str
    n: int
    agreement: float
    kappa: float
    fail_precision: float | None
    fail_recall: float | None


class FailureModeStats(BaseModel):
    mode: str
    support: int
    precision: float | None
    recall: float | None


class CalibrationResult(BaseModel):
    labels_path: str
    judge_model: str | None
    n_total: int
    n_scored: int
    n_borderline: int
    n_judge_errors: int
    kappa: float
    kappa_ci_low: float
    kappa_ci_high: float
    agreement: float
    confusion: dict[str, int] = Field(
        description="Counts keyed human_judge: pass_pass, pass_fail, fail_pass, fail_fail."
    )
    fail_precision: float | None
    fail_recall: float | None
    by_category: list[GroupStats]
    by_failure_mode: list[FailureModeStats]
    items: list[ItemResult]
    min_kappa: float | None
    passed: bool
    verdict_version: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def disagreements(self) -> list[ItemResult]:
        return [i for i in self.items if i.scored and not i.agree]


# ---------------------------------------------------------------------------
# Analysis (pure)
# ---------------------------------------------------------------------------


def _pf(passed: bool) -> str:
    return PASS if passed else "fail"


def _group(name: str, items: list[ItemResult]) -> GroupStats:
    ref = [_pf(i.human_passed) for i in items]
    pred = [_pf(bool(i.judge_passed)) for i in items]
    precision, recall, _ = precision_recall(ref, pred, "fail")
    return GroupStats(
        name=name,
        n=len(items),
        agreement=sum(1 for i in items if i.agree) / len(items),
        kappa=cohen_kappa(ref, pred),
        fail_precision=precision,
        fail_recall=recall,
    )


def analyze_calibration(
    examples: list[LabeledExample],
    judgments: list[Judgment],
    *,
    labels_path: str = "",
    judge_model: str | None = None,
    min_kappa: float | None = None,
    seed: int = 0,
) -> CalibrationResult:
    by_id = {j.prompt_id: j for j in judgments}
    items: list[ItemResult] = []
    for ex in examples:
        j = by_id.get(ex.prompt.id)
        error = j is None or bool(j.metadata.get("judge_error"))
        items.append(
            ItemResult(
                id=ex.id,
                category=ex.prompt.category,
                human_passed=ex.human_passed,
                judge_passed=None if error or j is None else j.passed,
                human_failure_mode=ex.human_failure_mode,
                judge_failure_mode=(
                    j.failure_mode.value if j and j.failure_mode and not j.passed else None
                ),
                borderline=ex.borderline,
                judge_error=error,
                judge_reasoning=j.reasoning if j else "",
            )
        )

    scored = [i for i in items if i.scored]
    ref = [_pf(i.human_passed) for i in scored]
    pred = [_pf(bool(i.judge_passed)) for i in scored]
    confusion = {
        f"{h}_{p}": sum(1 for r, q in zip(ref, pred) if (r, q) == (h, p))
        for h in (PASS, "fail")
        for p in (PASS, "fail")
    }
    kappa = cohen_kappa(ref, pred) if scored else 0.0
    ci_low, ci_high = kappa_bootstrap_ci(ref, pred, seed=seed) if scored else (0.0, 0.0)
    fail_p, fail_r, _ = precision_recall(ref, pred, "fail")

    categories = sorted({i.category for i in scored})
    by_category = [_group(c, [i for i in scored if i.category == c]) for c in categories]

    # Failure-mode labels: "pass" for passing items, the mode (or "unspecified") otherwise.
    ref_modes = [PASS if i.human_passed else (i.human_failure_mode or UNSPECIFIED) for i in scored]
    pred_modes = [PASS if i.judge_passed else (i.judge_failure_mode or UNSPECIFIED) for i in scored]
    modes = sorted((set(ref_modes) | set(pred_modes)) - {PASS, UNSPECIFIED})
    by_mode: list[FailureModeStats] = []
    for mode in modes:
        precision, recall, support = precision_recall(ref_modes, pred_modes, mode)
        by_mode.append(
            FailureModeStats(mode=mode, support=support, precision=precision, recall=recall)
        )

    return CalibrationResult(
        labels_path=labels_path,
        judge_model=judge_model,
        n_total=len(items),
        n_scored=len(scored),
        n_borderline=sum(1 for i in items if i.borderline),
        n_judge_errors=sum(1 for i in items if i.judge_error and not i.borderline),
        kappa=kappa,
        kappa_ci_low=ci_low,
        kappa_ci_high=ci_high,
        agreement=sum(1 for i in scored if i.agree) / len(scored) if scored else 0.0,
        confusion=confusion,
        fail_precision=fail_p,
        fail_recall=fail_r,
        by_category=by_category,
        by_failure_mode=by_mode,
        items=items,
        min_kappa=min_kappa,
        passed=bool(scored) and (min_kappa is None or kappa >= min_kappa),
        verdict_version=_verdict_version(),
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_calibration(
    labels_path: str | Path,
    *,
    judge_model: str | None = None,
    min_kappa: float | None = None,
    judge: JudgeFn | None = None,
    max_workers: int = 4,
    on_progress: Callable[[str], None] | None = None,
) -> CalibrationResult:
    say = on_progress or (lambda _msg: None)
    examples = load_labels(labels_path)
    if judge is None and judge_model is None:
        from verdict.config.settings import get_settings

        judge_model = get_settings().default_judge_model
    say(f"Judging {len(examples)} labeled examples with {judge_model or 'custom judge'}…")
    judge_fn = judge or llm_judge(judge_model)

    size = max(1, -(-len(examples) // max_workers))  # ceil division
    chunks = [examples[i : i + size] for i in range(0, len(examples), size)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        parts = pool.map(
            lambda chunk: judge_fn([e.prompt for e in chunk], [e.result for e in chunk]), chunks
        )
        judgments = [j for part in parts for j in part]

    return analyze_calibration(
        examples,
        judgments,
        labels_path=str(labels_path),
        judge_model=judge_model,
        min_kappa=min_kappa,
    )
