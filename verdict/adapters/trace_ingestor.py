"""Verdict-native agent trace ingestor.

Reads JSON files produced by agents instrumented to emit AgentTrace format,
validates them against the AgentTrace schema, and returns typed objects ready
for trace_judge evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from verdict.models.trace_schemas import AgentTrace


def load_trace(path: Path | str) -> AgentTrace:
    """Load and validate a single AgentTrace from a JSON file.

    Args:
        path: Path to a JSON file containing one AgentTrace object.

    Returns:
        Validated AgentTrace.

    Raises:
        ValueError: If the file cannot be parsed or fails schema validation.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(raw, list):
        if len(raw) != 1:
            raise ValueError(
                f"{path} contains a JSON array with {len(raw)} items; "
                "use load_traces() for multi-trace files."
            )
        raw = raw[0]

    try:
        return AgentTrace(**raw)
    except (ValidationError, TypeError) as exc:
        raise ValueError(f"Schema validation failed for {path}: {exc}") from exc


def load_traces(path: Path | str) -> list[AgentTrace]:
    """Load and validate AgentTrace objects from a file or directory.

    Args:
        path: Either:
              - A directory: all *.json files are loaded as individual traces.
              - A single JSON file: may contain one AgentTrace object or a JSON
                array of AgentTrace objects.

    Returns:
        List of validated AgentTrace objects.

    Raises:
        ValueError: If any file fails validation.
        FileNotFoundError: If path does not exist.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if path.is_dir():
        json_files = sorted(path.glob("*.json"))
        if not json_files:
            raise ValueError(f"No *.json files found in directory: {path}")
        return [load_trace(f) for f in json_files]

    # Single file — may be one object or an array
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(raw, list):
        traces = []
        for i, item in enumerate(raw):
            try:
                traces.append(AgentTrace(**item))
            except (ValidationError, TypeError) as exc:
                raise ValueError(
                    f"Schema validation failed for item {i} in {path}: {exc}"
                ) from exc
        return traces

    try:
        return [AgentTrace(**raw)]
    except (ValidationError, TypeError) as exc:
        raise ValueError(f"Schema validation failed for {path}: {exc}") from exc
