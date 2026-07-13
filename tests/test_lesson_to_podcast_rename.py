"""Tests for the "Lesson N" -> "Podcast N" rewrite applied to spoken Host Intro text.

Client feedback (see docs/SELF_EVALUATION.md changelog): every episode must
open with "Podcast N" in the actual narration, not "Lesson N" - the real
source Markdown scripts say "Lesson N" verbatim in the Host Intro, so this
has to be a text transform applied before synthesis, not just a label/
filename change.
"""

from __future__ import annotations

from dorosak_factory.audio.assembly import rename_lesson_to_podcast


def test_renames_lesson_followed_by_period():
    text = "Category 30 — English for Weather, Lesson 1. Let's begin."
    assert rename_lesson_to_podcast(text) == "Category 30 — English for Weather, Podcast 1. Let's begin."


def test_renames_lesson_followed_by_dash():
    text = "Lesson 2 — Talking about the forecast."
    assert rename_lesson_to_podcast(text) == "Podcast 2 — Talking about the forecast."


def test_renames_multi_digit_lesson_number():
    text = "Welcome to Lesson 42 of this course."
    assert rename_lesson_to_podcast(text) == "Welcome to Podcast 42 of this course."


def test_leaves_text_without_lesson_mention_unchanged():
    text = "Welcome to the show. Let's begin."
    assert rename_lesson_to_podcast(text) == text


def test_does_not_touch_the_word_lesson_without_a_number():
    text = "This lesson plan covers many lessons."
    assert rename_lesson_to_podcast(text) == text


def test_does_not_touch_lowercase_lesson():
    # Real source files always capitalize "Lesson" when referring to the
    # episode number; a lowercase "lesson" immediately followed by a
    # number is incidental prose, not an episode reference.
    text = "He learned lesson 5 the hard way."
    assert rename_lesson_to_podcast(text) == text
