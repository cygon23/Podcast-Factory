"""CLI integration test for `course-run`, using NullEngine (no network,
no cost) - same philosophy as tests/test_cli.py's `run` command tests.
"""

from __future__ import annotations

import pytest

from dorosak_factory.cli import main
from tests.course_fixtures import CSV_HEADER, csv_row


@pytest.fixture
def project(tmp_path):
    (tmp_path / "input" / "course_csv").mkdir(parents=True)
    vocab_path = tmp_path / "input" / "course_csv" / "vocabulary.csv"
    rows = [
        csv_row(section_id="77", item_no=1, item_text="Alphabet\tالأبجدية"),
        csv_row(section_id="77", item_no=2, item_text="Letter\tحرف"),
    ]
    vocab_path.write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


def test_course_run_dry_run_prints_plan_without_producing_output(project, capsys):
    exit_code = main(
        [
            "--base-dir", str(project),
            "course-run",
            "--content", "vocabulary",
            "--english-engine", "null",
            "--arabic-engine", "null",
            "--dry-run",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "vocabulary" in captured.out
    assert not (project / "output" / "course").exists()


def test_course_run_produces_one_mp3_per_vocabulary_item(project):
    exit_code = main(
        [
            "--base-dir", str(project),
            "course-run",
            "--content", "vocabulary",
            "--english-engine", "null",
            "--arabic-engine", "null",
        ]
    )
    assert exit_code == 0
    output_dir = project / "output" / "course"
    mp3s = list(output_dir.rglob("*.mp3"))
    assert len(mp3s) == 2


def test_course_run_is_idempotent_on_rerun(project):
    main(
        [
            "--base-dir", str(project), "course-run", "--content", "vocabulary",
            "--english-engine", "null", "--arabic-engine", "null",
        ]
    )
    output_dir = project / "output" / "course"
    first_run_mtimes = {p: p.stat().st_mtime for p in output_dir.rglob("*.mp3")}

    main(
        [
            "--base-dir", str(project), "course-run", "--content", "vocabulary",
            "--english-engine", "null", "--arabic-engine", "null",
        ]
    )
    second_run_mtimes = {p: p.stat().st_mtime for p in output_dir.rglob("*.mp3")}

    assert first_run_mtimes == second_run_mtimes  # nothing re-rendered
