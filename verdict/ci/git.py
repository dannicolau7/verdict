"""Thin git helpers for `verdict diff`: resolve refs, list changed files, check out refs."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git command fails."""


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    return proc.stdout.strip()


def repo_root(path: Path) -> Path:
    return Path(_git(path, "rev-parse", "--show-toplevel"))


def resolve_ref(repo: Path, ref: str) -> str:
    """Return the full commit SHA for ``ref``."""
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except GitError as exc:
        raise GitError(
            f"cannot resolve ref {ref!r}. In CI, fetch full history "
            "(actions/checkout with fetch-depth: 0) or fetch the base branch first."
        ) from exc


def changed_files(repo: Path, base_sha: str, head_sha: str) -> list[str]:
    """Files changed on head since it diverged from base (``git diff base...head``)."""
    out = _git(repo, "diff", "--name-only", f"{base_sha}...{head_sha}")
    return [line for line in out.splitlines() if line]


@contextmanager
def worktree(repo: Path, sha: str) -> Iterator[Path]:
    """Check out ``sha`` into a temporary detached worktree; removed on exit."""
    tmp = Path(tempfile.mkdtemp(prefix="verdict-wt-"))
    path = tmp / sha[:12]
    _git(repo, "worktree", "add", "--detach", "--quiet", str(path), sha)
    try:
        yield path
    finally:
        try:
            _git(repo, "worktree", "remove", "--force", str(path))
        except GitError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            _git(repo, "worktree", "prune")
        except GitError:
            pass
