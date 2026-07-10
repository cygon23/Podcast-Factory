"""Tests for provider text-chunking logic."""

from __future__ import annotations

from dorosak_factory.tts.chunking import chunk_text


def test_short_text_is_not_chunked():
    assert chunk_text("Hello there.", max_chars=100) == ["Hello there."]


def test_empty_text_returns_no_chunks():
    assert chunk_text("", max_chars=100) == []


def test_splits_at_sentence_boundaries():
    text = "First sentence. Second sentence. Third sentence."
    chunks = chunk_text(text, max_chars=20)
    assert all(len(c) <= 20 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_never_drops_or_truncates_content():
    text = "Alpha beta gamma delta. Epsilon zeta eta theta. Iota kappa lambda mu."
    chunks = chunk_text(text, max_chars=25)
    rejoined_words = " ".join(chunks).split()
    original_words = text.split()
    assert rejoined_words == original_words


def test_hard_splits_a_single_sentence_longer_than_max_chars():
    # No sentence-ending punctuation, so this is one long "sentence" that
    # must be split at word boundaries - no single word here exceeds
    # max_chars, since a real provider limit is thousands of characters
    # and no English word is that long.
    text = "one two three four five six seven eight nine ten eleven twelve"
    chunks = chunk_text(text, max_chars=20)
    assert all(len(c) <= 20 for c in chunks)
    assert " ".join(chunks) == text


def test_chunks_respect_max_chars_strictly():
    text = " ".join(["word"] * 50) + "."
    chunks = chunk_text(text, max_chars=30)
    assert all(len(c) <= 30 for c in chunks)
