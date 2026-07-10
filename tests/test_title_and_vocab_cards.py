"""Tests for the title card and vocabulary end card ASS generators."""

from __future__ import annotations

from dorosak_factory.parser.models import VocabItem
from dorosak_factory.subtitles.title_card import generate_title_card_ass
from dorosak_factory.subtitles.vocab_card import compute_vocab_card_duration, generate_vocab_card_ass


def test_title_card_contains_category_lesson_and_both_titles():
    ass = generate_title_card_ass(
        category_number=30,
        lesson_number=1,
        title_en="Talking About Today's Weather",
        title_ar="الحديث عن طقس اليوم",
        video_width=1920,
        video_height=1080,
    )
    assert "Cat 30 · Lesson 1" in ass
    assert "Talking About Today's Weather" in ass
    assert "الحديث عن طقس اليوم" in ass
    assert ass.count("Dialogue:") == 1


def test_title_card_spans_zero_to_display_seconds():
    ass = generate_title_card_ass(
        30, 1, "T", "ت", video_width=1920, video_height=1080, display_seconds=5.0
    )
    assert "0:00:00.00,0:00:05.00" in ass


def test_compute_vocab_card_duration_uses_per_item_default():
    vocab = tuple(VocabItem(term=f"t{i}", definition=f"d{i}") for i in range(5))
    assert compute_vocab_card_duration(vocab) == 10.0  # 5 * 2.0


def test_compute_vocab_card_duration_respects_minimum():
    vocab = (VocabItem(term="t", definition="d"),)  # 1 * 2.0 = 2.0 < min 8.0
    assert compute_vocab_card_duration(vocab) == 8.0


def test_vocab_card_ass_lists_every_term():
    vocab = (
        VocabItem(term="Miserable", definition="very unpleasant"),
        VocabItem(term="Frost", definition="a thin layer of ice"),
    )
    ass = generate_vocab_card_ass(
        vocab, start_seconds=100.0, duration_seconds=8.0, video_width=1920, video_height=1080
    )
    assert "Miserable — very unpleasant" in ass
    assert "Frost — a thin layer of ice" in ass
    assert "Key Vocabulary" in ass
    assert ass.count("Dialogue:") == 1


def test_vocab_card_ass_timing_window():
    vocab = (VocabItem(term="t", definition="d"),)
    ass = generate_vocab_card_ass(
        vocab, start_seconds=100.0, duration_seconds=8.0, video_width=1920, video_height=1080
    )
    assert "0:01:40.00,0:01:48.00" in ass
