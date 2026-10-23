"""Load an eval suite from JSONL.

One case per line::

    {"id": "refund-policy", "prompt": "Can I get a refund after 40 days?",
     "expected_behavior": "Says refunds are only available within 30 days.",
     "category": "correctness", "severity": "high"}

``prompt`` and ``expected_behavior`` are required. ``id`` defaults to ``case-<line>``,
``category`` to ``correctness`` and ``severity`` to ``medium``. Any other keys go into
``metadata``. Blank lines and lines starting with ``#`` are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from verdict.models.schemas import TestPrompt

_FIELDS = {"id", "prompt", "expected_behavior", "category", "severity", "metadata"}


class SuiteError(ValueError):
    """Raised when the suite file is missing or malformed."""


def load_suite(path: str | Path) -> list[TestPrompt]:
    p = Path(path)
    if not p.is_file():
        raise SuiteError(f"suite file not found: {p}")

    cases: list[TestPrompt] = []
    seen: set[str] = set()
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SuiteError(f"{p}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise SuiteError(f"{p}:{lineno}: each line must be a JSON object")

        metadata = dict(raw.get("metadata") or {})
        metadata.update({k: v for k, v in raw.items() if k not in _FIELDS})
        case_id = str(raw.get("id") or f"case-{lineno:03d}")
        if case_id in seen:
            raise SuiteError(f"{p}:{lineno}: duplicate case id {case_id!r}")
        seen.add(case_id)
        try:
            cases.append(
                TestPrompt(
                    id=case_id,
                    prompt=raw.get("prompt", ""),
                    expected_behavior=raw.get("expected_behavior", ""),
                    category=raw.get("category", "correctness"),
                    severity=raw.get("severity", "medium"),
                    metadata=metadata,
                )
            )
        except ValidationError as exc:
            raise SuiteError(f"{p}:{lineno}: {exc}") from exc
        if not cases[-1].prompt or not cases[-1].expected_behavior:
            raise SuiteError(f"{p}:{lineno}: 'prompt' and 'expected_behavior' are required")

    if not cases:
        raise SuiteError(f"suite {p} has no cases")
    return cases
