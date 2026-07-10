"""Splits long text into provider-safe chunks at sentence boundaries.

Each cloud engine owns its own character limit (INSTRUCTIONS.md 4.1); this
is the shared splitting logic they all call.
"""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Splits `text` into pieces no longer than `max_chars`, preferring sentence breaks.

    A single sentence longer than `max_chars` is hard-split at a word
    boundary as a last resort - it is never truncated or dropped.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    sentences = _SENTENCE_BOUNDARY_RE.split(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(sentence) <= max_chars:
            current = sentence
        else:
            chunks.extend(_split_long_sentence(sentence, max_chars))

    if current:
        chunks.append(current)

    return chunks


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    words = sentence.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks
