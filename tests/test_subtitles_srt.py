"""Tests for SRT generation from an assembly timeline (INSTRUCTIONS.md 4.6)."""

from __future__ import annotations

import pytest

from dorosak_factory.audio.assembly import LineTiming
from dorosak_factory.subtitles.srt import format_srt_timestamp, generate_srt, write_srt


def test_format_srt_timestamp_basic():
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(65.5) == "00:01:05,500"
    assert format_srt_timestamp(3661.25) == "01:01:01,250"


def test_format_srt_timestamp_rounds_milliseconds():
    assert format_srt_timestamp(1.9999) == "00:00:02,000"


def test_generate_srt_has_one_cue_per_timeline_entry():
    timeline = (
        LineTiming("Host", "Welcome.", 0.0, 2.0),
        LineTiming("Tom", "Hello there.", 2.7, 4.5),
    )
    srt = generate_srt(timeline)
    assert srt.count("-->") == 2
    assert "1\n" in srt
    assert "2\n" in srt


def test_generate_srt_includes_speaker_prefix_and_text():
    timeline = (LineTiming("Priya", "Did you get caught in it?", 0.0, 2.0),)
    srt = generate_srt(timeline)
    assert "Priya: Did you get caught in it?" in srt


def test_generate_srt_timestamps_are_correct():
    timeline = (LineTiming("Host", "Welcome.", 1.5, 4.25),)
    srt = generate_srt(timeline)
    assert "00:00:01,500 --> 00:00:04,250" in srt


def test_generate_srt_rejects_non_monotonic_timeline():
    timeline = (
        LineTiming("Tom", "First.", 5.0, 6.0),
        LineTiming("Priya", "Second.", 3.0, 4.0),  # starts before previous ended
    )
    with pytest.raises(ValueError, match="monotonic"):
        generate_srt(timeline)


def test_generate_srt_rejects_empty_timeline():
    with pytest.raises(ValueError, match="empty"):
        generate_srt(())


def test_write_srt_creates_file(tmp_path):
    timeline = (LineTiming("Host", "Welcome.", 0.0, 2.0),)
    path = tmp_path / "episode.srt"
    write_srt(timeline, path)
    assert path.exists()
    assert "Welcome." in path.read_text(encoding="utf-8")


def test_generate_srt_preserves_arabic_text():
    timeline = (LineTiming("Host", "الحديث عن طقس اليوم", 0.0, 2.0),)
    srt = generate_srt(timeline)
    assert "الحديث عن طقس اليوم" in srt
