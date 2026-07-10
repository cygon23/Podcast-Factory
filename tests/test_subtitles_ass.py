"""Tests for ASS subtitle generation used for burned-in video subtitles.

Per INSTRUCTIONS.md 4.6: speaker name prefix rendered in a distinct color
from the dialogue text.
"""

from __future__ import annotations

from dorosak_factory.audio.assembly import LineTiming
from dorosak_factory.subtitles.ass import format_ass_timestamp, generate_ass


def test_format_ass_timestamp_basic():
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(65.5) == "0:01:05.50"
    assert format_ass_timestamp(3661.25) == "1:01:01.25"


def test_generate_ass_has_header_sections():
    timeline = (LineTiming("Tom", "Hello.", 0.0, 2.0),)
    ass = generate_ass(timeline, video_width=1920, video_height=1080)
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "PlayResX: 1920" in ass
    assert "PlayResY: 1080" in ass


def test_generate_ass_has_one_dialogue_line_per_timeline_entry():
    timeline = (
        LineTiming("Host", "Welcome.", 0.0, 2.0),
        LineTiming("Tom", "Hi.", 2.7, 3.5),
    )
    ass = generate_ass(timeline, video_width=1920, video_height=1080)
    assert ass.count("Dialogue:") == 2


def test_generate_ass_colors_speaker_prefix_distinctly_from_body():
    timeline = (LineTiming("Tom", "Hello there.", 0.0, 2.0),)
    ass = generate_ass(timeline, video_width=1920, video_height=1080)
    # speaker name wrapped in a color override tag, reset before the body text
    assert r"{\c&H0000FFFF&}Tom:{\r}" in ass
    assert "Hello there." in ass


def test_generate_ass_includes_arabic_text_without_corruption():
    timeline = (LineTiming("Host", "الحديث عن طقس اليوم", 0.0, 2.0),)
    ass = generate_ass(timeline, video_width=1920, video_height=1080)
    assert "الحديث عن طقس اليوم" in ass


def test_generate_ass_uses_configured_font_and_size():
    timeline = (LineTiming("Tom", "Hi.", 0.0, 1.0),)
    ass = generate_ass(
        timeline, video_width=1080, video_height=1920, font_name="Noto Sans Arabic", font_size=42
    )
    assert "Noto Sans Arabic" in ass
    assert ",42," in ass
