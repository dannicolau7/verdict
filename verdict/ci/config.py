"""verdict.yaml — configuration for `verdict diff`.

Example::

    target: agent/verdict_adapter.py:SupportAgent   # adapter spec, relative to this file
    watch: ["prompts/**", "skills/**", "tools/*.json"]
    suite: evals/core.jsonl
    runs: 10
    judge: { model: claude-sonnet-5-5, calibration: evals/human_labels.jsonl, min_kappa: 0.7 }
    gate:
      max_pass_rate_drop: 0.05
      significance: 0.05
      cost_increase_max: 0.20

Paths are relative to the directory containing verdict.yaml. The target is loaded
from that directory inside each checkout (base and head); the suite is read once
from the current checkout so both sides run the same cases.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, description="Judge model; default from settings.")
    # Used by `verdict calibrate` (Milestone 3); parsed now so configs stay forward-compatible.
    calibration: str | None = None
    min_kappa: float | None = Field(default=None, ge=-1.0, le=1.0)


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_pass_rate_drop: float = Field(default=0.05, ge=0.0, le=1.0)
    significance: float = Field(default=0.05, gt=0.0, le=1.0)
    cost_increase_max: float | None = Field(default=None, ge=0.0)
    latency_increase_max: float | None = Field(default=None, ge=0.0)
    fail_on_case_regression: bool = False


class StatsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["fisher", "bootstrap"] = "fisher"
    bootstrap_iterations: int = Field(default=2000, ge=100)
    seed: int = 0
    k: list[int] = Field(
        default_factory=list,
        description="k values for pass@k and pass^k; empty = [runs]. Values above runs are skipped.",
    )
    power: float = Field(default=0.8, gt=0.0, lt=1.0, description="For the detectable-drop check.")

    @field_validator("k")
    @classmethod
    def _k_positive(cls, v: list[int]) -> list[int]:
        if any(k < 1 for k in v):
            raise ValueError("k values must be >= 1")
        return sorted(set(v))


class DiffConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Adapter spec: 'path/to/file.py:ClassName' or built-in.")
    suite: str
    watch: list[str] = Field(default_factory=list, description="Empty = always run.")
    runs: int = Field(default=10, ge=1, le=1000)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    gate: GateConfig = Field(default_factory=GateConfig)
    stats: StatsConfig = Field(default_factory=StatsConfig)

    # Directory of the config file; set by load_config, not read from YAML.
    base_dir: Path = Field(default=Path("."), exclude=True)

    @property
    def suite_path(self) -> Path:
        return (self.base_dir / self.suite).resolve()


class ConfigError(ValueError):
    """Raised when verdict.yaml is missing or invalid."""


def load_config(path: str | Path) -> DiffConfig:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{p} must contain a mapping at the top level")
    try:
        cfg = DiffConfig(**raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid config {p}:\n{exc}") from exc
    cfg.base_dir = p.resolve().parent
    return cfg


# ---------------------------------------------------------------------------
# Watch globs
# ---------------------------------------------------------------------------


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a gitignore-style glob to a regex over '/'-separated paths.

    ``**`` matches across directories, ``*`` and ``?`` stay within one segment.
    """
    i, out = 0, []
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def match_watch(paths: list[str], patterns: list[str]) -> list[str]:
    """Return the paths matching any watch pattern (all paths if no patterns)."""
    if not patterns:
        return list(paths)
    regexes = [_glob_to_regex(p.removeprefix("./")) for p in patterns]
    return [path for path in paths if any(r.match(path) for r in regexes)]
