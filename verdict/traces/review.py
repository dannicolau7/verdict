"""Drafts file I/O and moving approved drafts into a suite.

The drafts file is JSONL, one DraftCase per line, so it can also be reviewed by hand:
set "status" to "approved" (after filling in expected_behavior) and run
`verdict review drafts.jsonl --suite … --apply`.

Status flow: pending → approved | rejected; approved → added once written to the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from verdict.traces.drafting import DraftCase


class DraftsError(ValueError):
    """Raised when a drafts file or suite can't be read or updated."""


def load_drafts(path: str | Path) -> list[DraftCase]:
    p = Path(path)
    if not p.is_file():
        return []
    drafts = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            drafts.append(DraftCase(**json.loads(line)))
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise DraftsError(f"{p}:{lineno}: invalid draft: {exc}") from exc
    return drafts


def save_drafts(path: str | Path, drafts: list[DraftCase]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(d.model_dump_json() + "\n" for d in drafts), encoding="utf-8")


def merge_drafts(existing: list[DraftCase], new: list[DraftCase]) -> tuple[list[DraftCase], int]:
    """Add new drafts whose id isn't already present (re-imports are idempotent)."""
    seen = {d.id for d in existing}
    fresh = [d for d in new if d.id not in seen]
    return existing + fresh, len(fresh)


def _suite_ids(suite: Path) -> set[str]:
    ids: set[str] = set()
    if not suite.is_file():
        return ids
    for line in suite.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            try:
                case_id = json.loads(s).get("id")
            except (json.JSONDecodeError, AttributeError):
                continue
            if case_id:
                ids.add(str(case_id))
    return ids


def add_approved_to_suite(drafts: list[DraftCase], suite: str | Path) -> int:
    """Append approved drafts to the suite JSONL and mark them 'added'. Returns count."""
    p = Path(suite)
    existing = _suite_ids(p)
    lines: list[str] = []
    for d in drafts:
        if d.status != "approved":
            continue
        if d.needs_edit:
            raise DraftsError(f"draft {d.id} is approved but expected_behavior is still a TODO")
        if d.id not in existing:
            lines.append(json.dumps(d.to_suite_case(), ensure_ascii=False))
            existing.add(d.id)
        d.status = "added"
    if lines:
        p.parent.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            prefix = "" if not text or text.endswith("\n") else "\n"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(prefix + "\n".join(lines) + "\n")
    return len(lines)
