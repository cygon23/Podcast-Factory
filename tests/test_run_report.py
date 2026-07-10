"""Tests for run report aggregation: counts, cost estimation, rendering."""

from __future__ import annotations

import json

from dorosak_factory.report.run_report import LessonOutcome, RunReport


def make_report():
    return RunReport(
        outcomes=[
            LessonOutcome(30, 1, "processed", engine="openai", characters_synthesized=500),
            LessonOutcome(30, 2, "processed", engine="openai", characters_synthesized=300),
            LessonOutcome(30, 3, "skipped"),
            LessonOutcome(30, 4, "failed", failure_reason="ffmpeg crashed"),
        ],
        wall_time_seconds=12.5,
    )


def test_counts():
    report = make_report()
    assert report.processed_count == 2
    assert report.skipped_count == 1
    assert report.failed_count == 1


def test_characters_by_engine():
    report = make_report()
    assert report.characters_by_engine() == {"openai": 800}


def test_estimated_cost_by_engine():
    report = make_report()
    cost = report.estimated_cost_by_engine({"openai": 0.00002})
    assert cost["openai"] == 800 * 0.00002


def test_failures_lists_only_failed():
    report = make_report()
    failures = report.failures()
    assert len(failures) == 1
    assert failures[0].lesson_number == 4
    assert failures[0].failure_reason == "ffmpeg crashed"


def test_render_text_contains_key_figures():
    report = make_report()
    text = report.render_text(price_per_char={"openai": 0.00002})
    assert "Processed: 2" in text
    assert "Skipped:   1" in text
    assert "Failed:    1" in text
    assert "openai: 800 chars" in text
    assert "ffmpeg crashed" in text


def test_render_json_round_trips():
    report = make_report()
    data = json.loads(report.render_json())
    assert data["processed"] == 2
    assert data["failed"] == 1
    assert data["characters_by_engine"] == {"openai": 800}
    assert data["failures"][0]["reason"] == "ffmpeg crashed"
