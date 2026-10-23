"""`verdict diff --base <ref> --head <ref>`: did this change make the agent worse?

Pipeline:
    1. Resolve refs; list files changed on head since base; skip if none match `watch`.
    2. For each side, check the ref out into a temporary git worktree and run the
       suite `runs` times in a subprocess (verdict.ci.side_runner).
    3. Judge every response in this process with one judge (same model for both sides).
    4. analyze(): per-suite and per-case pass rate, Wilson 95% CI, significance
       (Fisher's exact or bootstrap), cost and latency deltas, then the gate.

analyze() is pure and takes judged outcomes, so it is tested without git or an LLM.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from verdict.ci import git
from verdict.ci.config import DiffConfig, GateConfig, StatsConfig, match_watch
from verdict.ci.suite import load_suite
from verdict.models.schemas import ExecutionResult, FailureMode, Judgment, TestPrompt
from verdict.stats.proportions import bootstrap_diff, fisher_exact, wilson_interval

JudgeFn = Callable[[list[TestPrompt], list[ExecutionResult]], list[Judgment]]

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class Outcome(BaseModel):
    """One judged execution of one case."""

    case_id: str
    run: int
    passed: bool
    reasoning: str = ""
    failure_mode: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    cost_usd: float | None = None


class SideStats(BaseModel):
    n: int
    passed: int
    pass_rate: float
    ci_low: float
    ci_high: float
    errors: int = 0
    mean_latency_ms: float | None = None
    mean_cost_usd: float | None = None


class CaseDiff(BaseModel):
    case_id: str
    prompt: str
    category: str
    severity: str
    base: SideStats
    head: SideStats
    delta: float
    p_value: float
    status: Literal["regressed", "improved", "unchanged"]
    head_failures: list[str] = Field(
        default_factory=list, description="Up to 3 distinct judge reasons from failing head runs."
    )


class SuiteDiff(BaseModel):
    base: SideStats
    head: SideStats
    delta: float
    p_value: float
    delta_ci_low: float | None = None
    delta_ci_high: float | None = None
    cost_delta_pct: float | None = None
    latency_delta_pct: float | None = None


class GateCheck(BaseModel):
    name: str
    breached: bool
    detail: str


class GateResult(BaseModel):
    passed: bool
    checks: list[GateCheck] = Field(default_factory=list)

    @property
    def breaches(self) -> list[GateCheck]:
        return [c for c in self.checks if c.breached]


class DiffResult(BaseModel):
    status: Literal["completed", "skipped"]
    base_ref: str
    head_ref: str
    base_sha: str
    head_sha: str
    changed_files: list[str] = Field(default_factory=list)
    watched_changes: list[str] = Field(default_factory=list)
    runs: int
    stats_method: str
    n_cases: int = 0
    suite: SuiteDiff | None = None
    cases: list[CaseDiff] = Field(default_factory=list)
    gate: GateResult
    base_target: str | None = None
    head_target: str | None = None
    verdict_version: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def regressions(self) -> list[CaseDiff]:
        return [c for c in self.cases if c.status == "regressed"]

    @property
    def improvements(self) -> list[CaseDiff]:
        return [c for c in self.cases if c.status == "improved"]

    @property
    def failing_on_head(self) -> list[CaseDiff]:
        return [c for c in self.cases if c.head.passed < c.head.n]


# ---------------------------------------------------------------------------
# Analysis (pure)
# ---------------------------------------------------------------------------


def _side_stats(outcomes: list[Outcome]) -> SideStats:
    n = len(outcomes)
    k = sum(1 for o in outcomes if o.passed)
    lo, hi = wilson_interval(k, n)
    costs = [o.cost_usd for o in outcomes if o.cost_usd is not None]
    return SideStats(
        n=n,
        passed=k,
        pass_rate=k / n if n else 0.0,
        ci_low=lo,
        ci_high=hi,
        errors=sum(1 for o in outcomes if o.error),
        mean_latency_ms=sum(o.latency_ms for o in outcomes) / n if n else None,
        # Only report cost when every run reported it; a partial mean would mislead.
        mean_cost_usd=sum(costs) / n if n and len(costs) == n else None,
    )


def _compare(
    base: list[Outcome], head: list[Outcome], stats: StatsConfig
) -> tuple[float, float | None, float | None]:
    """Return (p_value, delta_ci_low, delta_ci_high) for head vs base pass rate."""
    if stats.method == "bootstrap":
        p, lo, hi = bootstrap_diff(
            [o.passed for o in base],
            [o.passed for o in head],
            iterations=stats.bootstrap_iterations,
            seed=stats.seed,
        )
        return p, lo, hi
    bp = sum(1 for o in base if o.passed)
    hp = sum(1 for o in head if o.passed)
    return fisher_exact(bp, len(base) - bp, hp, len(head) - hp), None, None


def _pct_change(base: float | None, head: float | None) -> float | None:
    if base is None or head is None or base <= 0:
        return None
    return (head - base) / base


def analyze(
    cases: list[TestPrompt],
    base: list[Outcome],
    head: list[Outcome],
    gate: GateConfig,
    stats: StatsConfig,
) -> tuple[SuiteDiff, list[CaseDiff], GateResult]:
    """Compute suite- and case-level comparisons and evaluate the gate."""
    alpha = gate.significance

    case_diffs: list[CaseDiff] = []
    for case in cases:
        b = [o for o in base if o.case_id == case.id]
        h = [o for o in head if o.case_id == case.id]
        bs, hs = _side_stats(b), _side_stats(h)
        p, _, _ = _compare(b, h, stats)
        delta = hs.pass_rate - bs.pass_rate
        status: Literal["regressed", "improved", "unchanged"] = "unchanged"
        if p < alpha and delta < 0:
            status = "regressed"
        elif p < alpha and delta > 0:
            status = "improved"
        reasons: list[str] = []
        for o in h:
            if not o.passed:
                why = o.error or o.reasoning
                if why and why not in reasons:
                    reasons.append(why)
            if len(reasons) == 3:
                break
        case_diffs.append(
            CaseDiff(
                case_id=case.id,
                prompt=case.prompt,
                category=case.category,
                severity=case.severity,
                base=bs,
                head=hs,
                delta=delta,
                p_value=p,
                status=status,
                head_failures=reasons,
            )
        )

    bs, hs = _side_stats(base), _side_stats(head)
    p, dlo, dhi = _compare(base, head, stats)
    suite = SuiteDiff(
        base=bs,
        head=hs,
        delta=hs.pass_rate - bs.pass_rate,
        p_value=p,
        delta_ci_low=dlo,
        delta_ci_high=dhi,
        cost_delta_pct=_pct_change(bs.mean_cost_usd, hs.mean_cost_usd),
        latency_delta_pct=_pct_change(bs.mean_latency_ms, hs.mean_latency_ms),
    )
    return suite, case_diffs, evaluate_gate(suite, case_diffs, gate)


def evaluate_gate(suite: SuiteDiff, cases: list[CaseDiff], gate: GateConfig) -> GateResult:
    checks: list[GateCheck] = []

    drop = -suite.delta
    significant = suite.p_value < gate.significance
    checks.append(
        GateCheck(
            name="pass_rate",
            breached=drop > gate.max_pass_rate_drop and significant,
            detail=(
                f"pass rate {_pts(suite.delta)} (max drop {gate.max_pass_rate_drop * 100:.1f} pts), "
                f"p={suite.p_value:.3g} ({'<' if significant else '≥'} {gate.significance:g})"
            ),
        )
    )

    if gate.cost_increase_max is not None:
        if suite.cost_delta_pct is None:
            checks.append(GateCheck(name="cost", breached=False, detail="cost not reported; skipped"))
        else:
            checks.append(
                GateCheck(
                    name="cost",
                    breached=suite.cost_delta_pct > gate.cost_increase_max,
                    detail=f"cost {suite.cost_delta_pct:+.1%} (max +{gate.cost_increase_max:.0%})",
                )
            )

    if gate.latency_increase_max is not None and suite.latency_delta_pct is not None:
        checks.append(
            GateCheck(
                name="latency",
                breached=suite.latency_delta_pct > gate.latency_increase_max,
                detail=(
                    f"latency {suite.latency_delta_pct:+.1%} "
                    f"(max +{gate.latency_increase_max:.0%})"
                ),
            )
        )

    if gate.fail_on_case_regression:
        n_reg = sum(1 for c in cases if c.status == "regressed")
        checks.append(
            GateCheck(
                name="case_regressions",
                breached=n_reg > 0,
                detail=f"{n_reg} case(s) significantly regressed",
            )
        )

    return GateResult(passed=not any(c.breached for c in checks), checks=checks)


def _pts(delta: float) -> str:
    return f"{delta * 100:+.1f} pts"


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------


def llm_judge(model: str | None) -> JudgeFn:
    """The standard Verdict LLM judge, optionally pinned to one model."""

    def _judge(prompts: list[TestPrompt], results: list[ExecutionResult]) -> list[Judgment]:
        from verdict.agents.judge import judge_results

        return judge_results(prompts, results, judge_models=[model] if model else None)

    return _judge


def judge_side(
    cases: list[TestPrompt],
    runs: list[list[ExecutionResult]],
    judge: JudgeFn,
    max_workers: int = 4,
) -> list[Outcome]:
    """Judge every run of one side, runs in parallel threads.

    Errored executions count as failures without a judge call.
    """
    def one_run(idx: int, results: list[ExecutionResult]) -> list[Outcome]:
        to_judge = [(c, r) for c, r in zip(cases, results) if r.error is None]
        judgments = judge([c for c, _ in to_judge], [r for _, r in to_judge]) if to_judge else []
        by_id = {j.prompt_id: j for j in judgments}
        out: list[Outcome] = []
        for case, res in zip(cases, results):
            j = by_id.get(case.id)
            out.append(
                Outcome(
                    case_id=case.id,
                    run=idx,
                    passed=bool(j and j.passed and res.error is None),
                    reasoning=j.reasoning if j else "",
                    failure_mode=(
                        j.failure_mode.value
                        if j and j.failure_mode
                        else (FailureMode.other.value if res.error else None)
                    ),
                    error=res.error,
                    latency_ms=res.latency_ms,
                    cost_usd=res.estimated_cost_usd,
                )
            )
        return out

    workers = max(1, min(len(runs), max_workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        per_run = list(pool.map(lambda args: one_run(*args), enumerate(runs)))
    return [o for run in per_run for o in run]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _verdict_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("verdict-eval")
    except Exception:
        return None


def _run_side(checkout: Path, config: DiffConfig, cases_path: Path) -> dict[str, Any]:
    """Run the suite against one checkout in a subprocess; return the side JSON."""
    with tempfile.TemporaryDirectory(prefix="verdict-side-") as tmp:
        out = Path(tmp) / "side.json"
        cmd = [
            sys.executable,
            "-P",  # don't put the checkout ahead of the installed verdict package
            "-m",
            "verdict.ci.side_runner",
            "--target",
            config.target,
            "--suite",
            str(cases_path),
            "--runs",
            str(config.runs),
            "--out",
            str(out),
        ]
        proc = subprocess.run(cmd, cwd=checkout, capture_output=True, text=True, env=os.environ)
        if proc.returncode != 0 or not out.exists():
            tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-15:])
            raise RuntimeError(f"target run failed in {checkout}:\n{tail}")
        data: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
        return data


def run_git_diff(
    config: DiffConfig,
    base_ref: str,
    head_ref: str = "HEAD",
    *,
    force: bool = False,
    judge: JudgeFn | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> DiffResult:
    """Run the suite on base and head and compare. See module docstring."""
    say = on_progress or (lambda _msg: None)
    root = git.repo_root(config.base_dir)
    base_sha = git.resolve_ref(root, base_ref)
    head_sha = git.resolve_ref(root, head_ref)

    # Watch globs are relative to the config directory, like every other path.
    rel = config.base_dir.resolve().relative_to(root.resolve())
    prefix = "" if str(rel) == "." else rel.as_posix() + "/"
    changed = git.changed_files(root, base_sha, head_sha)
    local = [p.removeprefix(prefix) for p in changed if p.startswith(prefix)]
    watched = match_watch(local, config.watch)

    common: dict[str, Any] = dict(
        base_ref=base_ref,
        head_ref=head_ref,
        base_sha=base_sha,
        head_sha=head_sha,
        changed_files=changed,
        watched_changes=watched,
        runs=config.runs,
        stats_method=config.stats.method,
        verdict_version=_verdict_version(),
    )
    if not watched and not force:
        say("No watched files changed; skipping.")
        return DiffResult(status="skipped", gate=GateResult(passed=True), **common)

    cases = load_suite(config.suite_path)
    say(f"{len(cases)} cases × {config.runs} runs per side")

    sides: dict[str, dict[str, Any]] = {}
    for label, sha in (("base", base_sha), ("head", head_sha)):
        say(f"Running {label} ({sha[:7]})…")
        with git.worktree(root, sha) as wt:
            sides[label] = _run_side(wt / rel, config, config.suite_path)

    judge_fn = judge or llm_judge(config.judge.model)
    outcomes: dict[str, list[Outcome]] = {}
    for label in ("base", "head"):
        say(f"Judging {label}…")
        runs = [[ExecutionResult(**r) for r in run] for run in sides[label]["runs"]]
        outcomes[label] = judge_side(cases, runs, judge_fn)

    suite, case_diffs, gate = analyze(
        cases, outcomes["base"], outcomes["head"], config.gate, config.stats
    )
    return DiffResult(
        status="completed",
        n_cases=len(cases),
        suite=suite,
        cases=case_diffs,
        gate=gate,
        base_target=f"{sides['base']['adapter']} {sides['base']['version']}",
        head_target=f"{sides['head']['adapter']} {sides['head']['version']}",
        **common,
    )
