"""Tests for live STATUS.md rendering and the git commit+push wrapper.

The push wrapper is tested against a real local git repo (a bare "remote"
+ a clone), not mocked - git plumbing is exactly the kind of thing that's
easy to get subtly wrong with a mock.
"""

from __future__ import annotations

import subprocess
import threading

import pytest

from dorosak_factory.report.run_report import LessonOutcome, RunReport
from dorosak_factory.report.status_sync import render_status_markdown, write_and_push_status


def test_render_includes_category_and_counts():
    report = RunReport(
        outcomes=[
            LessonOutcome(30, 1, "processed"),
            LessonOutcome(30, 2, "processed"),
            LessonOutcome(30, 3, "failed", failure_reason="boom"),
        ]
    )
    markdown = render_status_markdown(
        category_number=30,
        category_title="English for Weather & Nature Daily Life",
        engine_name="kokoro",
        total_lessons=50,
        report=report,
    )
    assert "Cat 30" in markdown
    assert "English for Weather & Nature Daily Life" in markdown
    assert "Processed: 2/50" in markdown
    assert "Failed: 1" in markdown
    assert "kokoro" in markdown


def test_render_includes_last_completed_when_given():
    report = RunReport(outcomes=[LessonOutcome(30, 5, "processed")])
    markdown = render_status_markdown(
        category_number=30,
        category_title="Weather",
        engine_name="kokoro",
        total_lessons=50,
        report=report,
        last_completed="cat30:5 — Talking About Winter Weather",
    )
    assert "Last completed: cat30:5 — Talking About Winter Weather" in markdown


def test_render_omits_failures_section_when_none():
    report = RunReport(outcomes=[LessonOutcome(30, 1, "processed")])
    markdown = render_status_markdown(
        category_number=30,
        category_title="Weather",
        engine_name="kokoro",
        total_lessons=50,
        report=report,
    )
    assert "Failures" not in markdown


def test_render_lists_failure_reasons_when_present():
    report = RunReport(outcomes=[LessonOutcome(30, 7, "failed", failure_reason="loudness out of range")])
    markdown = render_status_markdown(
        category_number=30,
        category_title="Weather",
        engine_name="kokoro",
        total_lessons=50,
        report=report,
    )
    assert "### Failures" in markdown
    assert "Lesson 7: loudness out of range" in markdown


@pytest.fixture
def git_repo_with_remote(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    working = tmp_path / "working"
    subprocess.run(["git", "clone", str(bare), str(working)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=working, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=working, check=True)
    (working / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=working, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=working, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD"], cwd=working, check=True, capture_output=True)
    return working, bare


def _remote_file_content(bare_dir, filename):
    result = subprocess.run(
        ["git", "show", f"HEAD:{filename}"], cwd=bare_dir, capture_output=True, text=True, check=True
    )
    return result.stdout


def test_write_and_push_status_reaches_the_remote(git_repo_with_remote):
    working, bare = git_repo_with_remote
    status_path = working / "STATUS.md"

    result = write_and_push_status(working, status_path, "# Status\nHello\n")

    assert result is True
    assert status_path.read_text(encoding="utf-8") == "# Status\nHello\n"
    assert _remote_file_content(bare, "STATUS.md") == "# Status\nHello\n"


def test_write_and_push_status_updates_on_second_call(git_repo_with_remote):
    working, bare = git_repo_with_remote
    status_path = working / "STATUS.md"

    write_and_push_status(working, status_path, "# Status\nFirst\n")
    result = write_and_push_status(working, status_path, "# Status\nSecond\n")

    assert result is True
    assert _remote_file_content(bare, "STATUS.md") == "# Status\nSecond\n"


def test_write_and_push_status_is_a_noop_when_content_unchanged(git_repo_with_remote):
    working, bare = git_repo_with_remote
    status_path = working / "STATUS.md"

    write_and_push_status(working, status_path, "# Status\nSame\n")
    result = write_and_push_status(working, status_path, "# Status\nSame\n")

    assert result is True  # still "successful" - just nothing to push


def test_write_and_push_status_fails_gracefully_outside_a_git_repo(tmp_path):
    not_a_repo = tmp_path / "plain_dir"
    not_a_repo.mkdir()
    status_path = not_a_repo / "STATUS.md"

    result = write_and_push_status(not_a_repo, status_path, "# Status\n")

    assert result is False  # never raises


def test_concurrent_calls_do_not_corrupt_the_repo(git_repo_with_remote):
    working, bare = git_repo_with_remote
    status_path = working / "STATUS.md"
    results = []

    def call(n):
        results.append(write_and_push_status(working, status_path, f"# Status\nRun {n}\n"))

    threads = [threading.Thread(target=call, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(results)
    # final remote content is one of the 5 writes - just must be valid, not corrupted
    final = _remote_file_content(bare, "STATUS.md")
    assert final.startswith("# Status\nRun ")
