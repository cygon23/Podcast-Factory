"""CLI integration tests: dry-run, real run (NullEngine, audio-only), status, cost-report.

Uses the tiny 2-lesson fixture (tests/fixtures/cat99_tiny_fixture.md) end to
end, per INSTRUCTIONS.md section 6's integration test requirement.

Note: NullEngine produces pure silence, which always fails the loudness
check (section 5) regardless of duration - that's correct, not a test bug:
it proves validation is a real gate, not a rubber stamp. These tests assert
a "failed" outcome with a loudness-related reason, while confirming the
files were still produced and the manifest correctly recorded everything.
"""

from __future__ import annotations

import shutil

import pytest

from dorosak_factory.cli import build_arg_parser, discover_categories, main, parse_only
from dorosak_factory.manifest.store import Manifest

FIXTURE = "tests/fixtures/cat99_tiny_fixture.md"


@pytest.fixture
def project(tmp_path):
    """Sets up a self-contained project dir: input/ (copy of fixture) + config."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    shutil.copy(FIXTURE, input_dir / "cat99_tiny_fixture.md")
    return tmp_path


def test_parse_only_lesson_form():
    assert parse_only("cat31:5") == (31, 5)


def test_parse_only_category_form():
    assert parse_only("cat31") == (31, None)


def test_parse_only_none():
    assert parse_only(None) == (None, None)


def test_build_arg_parser_run_defaults():
    parser = build_arg_parser()
    args = parser.parse_args(["run"])
    assert args.command == "run"
    assert args.formats == "both"
    assert args.force is False
    assert args.dry_run is False


def test_discover_categories_parses_fixture(project):
    categories, errors = discover_categories(project / "input")
    assert len(categories) == 1
    assert len(categories[0].lessons) == 2
    assert errors == []


def test_dry_run_prints_plan_and_creates_no_output(project, capsys):
    exit_code = main(["--base-dir", str(project), "run", "--engine", "null", "--dry-run"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Engine resolved: null" in output
    assert "Lessons to process: 2" in output
    assert "cat99:1" in output
    assert "cat99:2" in output
    # dry-run initializes the manifest DB (needed to compute the plan) but
    # must synthesize nothing - no episode artifacts should exist.
    assert not (project / "output" / "cat99").exists()


def test_only_filters_to_a_single_lesson_in_dry_run(project, capsys):
    exit_code = main(
        ["--base-dir", str(project), "run", "--engine", "null", "--only", "cat99:1", "--dry-run"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "cat99:1" in output
    assert "cat99:2" not in output


def test_real_run_produces_files_and_records_manifest(project, capsys):
    exit_code = main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio"])
    output = capsys.readouterr().out

    # NullEngine's silence fails the loudness gate - see module docstring.
    assert exit_code == 1
    assert "Processed: 0" in output
    assert "Failed:    2" in output

    lesson1_dir = project / "output" / "cat99" / "lesson1"
    assert (lesson1_dir / "episode.mp3").exists()
    assert (lesson1_dir / "episode.srt").exists()
    assert (lesson1_dir / "metadata.json").exists()

    manifest = Manifest(db_path=project / "output" / "manifest.sqlite3")
    record = manifest.get_record(99, 1)
    assert record.status == "failed"
    assert "loudness" in record.failure_reason
    manifest.close()


def test_status_command_reports_after_a_run(project, capsys):
    main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio"])
    capsys.readouterr()  # discard run output

    exit_code = main(["--base-dir", str(project), "status"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Total recorded lessons: 2" in output
    assert "Failed:  2" in output


def test_cost_report_reflects_characters_synthesized(project, capsys):
    main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio"])
    capsys.readouterr()

    exit_code = main(["--base-dir", str(project), "cost-report"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "null:" in output
    assert "chars" in output


def test_validate_command_spot_checks_existing_outputs(project, capsys):
    main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio"])
    capsys.readouterr()

    exit_code = main(["--base-dir", str(project), "validate"])
    output = capsys.readouterr().out

    assert exit_code == 0  # files exist and are playable, even though validation gate failed earlier
    assert "0 problem(s) found" in output


def test_run_writes_a_timestamped_log_file(project, capsys):
    main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio"])
    capsys.readouterr()

    logs_dir = project / "output" / "logs"
    log_files = list(logs_dir.glob("run_*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "Engine resolved: null" in content
    assert "Failed:    2" in content


def test_dry_run_also_writes_a_log_file(project, capsys):
    main(["--base-dir", str(project), "run", "--engine", "null", "--dry-run"])
    capsys.readouterr()

    log_files = list((project / "output" / "logs").glob("run_*.log"))
    assert len(log_files) == 1
    assert "Lessons to process: 2" in log_files[0].read_text(encoding="utf-8")


def test_unknown_explicit_engine_fails_cleanly(project, capsys):
    exit_code = main(["--base-dir", str(project), "run", "--engine", "nonexistent", "--dry-run"])
    error_output = capsys.readouterr().err

    assert exit_code == 1
    assert "Unknown engine" in error_output


def test_live_status_outside_a_git_repo_does_not_crash_the_run(project, capsys):
    # project fixture is a plain tmp_path, not a git repo - proves the
    # opt-in flag degrades gracefully rather than breaking real work.
    exit_code = main(
        ["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio", "--live-status"]
    )
    output = capsys.readouterr().out

    assert exit_code == 1  # NullEngine silence still fails loudness, as always
    assert "Processed: 0" in output
    assert "Failed:    2" in output


@pytest.fixture
def git_project(project):
    """Turns the `project` fixture into a real git repo with a remote, for --live-status."""
    import subprocess

    bare = project.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project, check=True)
    (project / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD"], cwd=project, check=True, capture_output=True)
    return project, bare


def test_live_status_pushes_status_md_to_the_remote(git_project, capsys):
    import subprocess

    project, bare = git_project

    main(["--base-dir", str(project), "run", "--engine", "null", "--formats", "audio", "--live-status"])
    capsys.readouterr()

    assert (project / "STATUS.md").exists()
    remote_content = subprocess.run(
        ["git", "show", "HEAD:STATUS.md"], cwd=bare, capture_output=True, text=True, check=True
    ).stdout
    assert "cat99" in remote_content or "All categories" in remote_content
    assert "Processed: 0" in remote_content  # both lessons fail loudness, as always with NullEngine
    assert "Failed: 2" in remote_content
