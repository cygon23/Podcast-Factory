"""Live STATUS.md updates pushed to git as lessons complete (opt-in, --live-status).

Code/status only - this never commits generated audio/video (those stay
gitignored; see docs/ASSETS.md and the operator's own Drive workflow for
actual episode delivery). A push failure (network blip, remote ahead,
no git repo at all) logs a warning and returns False rather than raising -
the pipeline's real job (producing episodes) always takes priority over
the status file staying current.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from dorosak_factory.report.run_report import RunReport

_push_lock = threading.Lock()


def render_status_markdown(
    category_number: int,
    category_title: str,
    engine_name: str,
    total_lessons: int,
    report: RunReport,
    last_completed: str | None = None,
) -> str:
    """Renders a small human-readable STATUS.md body for one category's in-progress run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Live Run Status",
        "",
        f"Last updated: {timestamp}",
        "",
        f"## Cat {category_number} — {category_title}",
        "",
        f"- Engine: {engine_name}",
        f"- Processed: {report.processed_count}/{total_lessons}",
        f"- Failed: {report.failed_count}",
        f"- Skipped: {report.skipped_count}",
    ]
    if last_completed:
        lines.append(f"- Last completed: {last_completed}")
    if report.failed_count:
        lines.append("")
        lines.append("### Failures")
        for outcome in report.failures():
            lines.append(
                f"- Cat {outcome.category_number} Lesson {outcome.lesson_number}: {outcome.failure_reason}"
            )
    return "\n".join(lines) + "\n"


def write_and_push_status(repo_dir: Path, status_path: Path, content: str) -> bool:
    """Writes `content` to `status_path` and commits+pushes just that file.

    Thread-safe: concurrent callers (parallel lesson completions) are
    serialized through a module-level lock so they never race on the same
    git working tree. Never raises.
    """
    with _push_lock:
        try:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(content, encoding="utf-8")
            relative_path = status_path.relative_to(repo_dir)

            _run_git(repo_dir, ["add", str(relative_path)])
            diff_check = subprocess.run(
                ["git", "diff", "--cached", "--quiet"], cwd=repo_dir, capture_output=True
            )
            if diff_check.returncode == 0:
                return True  # nothing changed - nothing to commit or push

            _run_git(repo_dir, ["commit", "-m", "chore: live status update"])
            _run_git(repo_dir, ["push", "origin", "HEAD"])
            return True
        except Exception as exc:  # noqa: BLE001 - status sync must never break a run
            print(f"WARNING: live status push failed: {exc}", file=sys.stderr)
            return False


def _run_git(repo_dir: Path, args: list[str]) -> None:
    result = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
