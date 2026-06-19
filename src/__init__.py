"""Credito-Extratos: analise de renda a partir de extratos bancarios em PDF."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

__version__ = "1.0.0"

logger = logging.getLogger(__name__)


def _read_git_commit() -> str:
    """Best-effort: returns the short git commit hash, or "unknown".

    Looks at .git/HEAD without spawning ``git`` so it works on machines
    without git installed (typical analyst workstation running the
    standalone build).
    """
    try:
        repo_root = Path(__file__).resolve().parents[1]
        head_file = repo_root / ".git" / "HEAD"
        if not head_file.exists():
            return "unknown"

        head_content = head_file.read_text(encoding="utf-8").strip()
        if head_content.startswith("ref:"):
            ref_path = repo_root / ".git" / head_content.split(" ", 1)[1].strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()[:7]
        else:
            return head_content[:7]
    except Exception:
        logger.debug("Falha ao ler commit do git", exc_info=True)
    return "unknown"


def _read_git_commit_via_cli() -> str | None:
    """Fallback: try ``git rev-parse`` if .git/HEAD heuristic failed."""
    try:
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        logger.debug("git rev-parse falhou", exc_info=True)
    return None


_GIT_COMMIT_CACHE: str | None = None


def get_git_commit() -> str:
    global _GIT_COMMIT_CACHE
    if _GIT_COMMIT_CACHE is not None:
        return _GIT_COMMIT_CACHE

    commit = _read_git_commit()
    if commit == "unknown":
        cli_commit = _read_git_commit_via_cli()
        if cli_commit:
            commit = cli_commit
    _GIT_COMMIT_CACHE = commit
    return commit


def get_version_label() -> str:
    """Returns 'v{version} ({commit})' for stamping on exported artifacts."""
    return f"v{__version__} ({get_git_commit()})"


__all__ = ["__version__", "get_git_commit", "get_version_label"]
