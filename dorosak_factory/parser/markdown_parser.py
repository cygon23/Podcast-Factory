"""Parses Dorosak category Markdown files into Category/Lesson dataclasses.

Parsing is tolerant: a lesson block that fails to parse is recorded in
`Category.parse_errors` (file + lesson header + reason) and skipped; the
rest of the file is still processed. Nothing here ever raises for a single
bad lesson - only for structural problems that prevent finding the category
header/level line at all.
"""

from __future__ import annotations

import re
from pathlib import Path

from dorosak_factory.parser.models import Category, DialogueTurn, Lesson, ParseError, VocabItem

_CATEGORY_HEADER_RE = re.compile(r"^#\s*Category\s+(\d+):\s*(.+?)\s*—\s*(.+?)\s*$")
_LEVEL_RE = re.compile(r"Level:\s*(.+?)\s*$")
_LESSON_HEADER_RE = re.compile(r"^##\s*Lesson\s+(\d+):\s*(.+?)\s*\|\s*(.+?)\s*$")
_SPEAKER_LINE_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")
_VOCAB_LINE_RE = re.compile(r"^-\s*\*(.+?)\*\s*—\s*(.+?)\s*$")

_DOUBLE_EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*")
_SINGLE_EMPHASIS_RE = re.compile(r"\*(.+?)\*")
_DOUBLE_EM_DASH_RE = re.compile(r"\s*—\s*—\s*")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,!?;:])")


def strip_emphasis(text: str) -> str:
    """Removes Markdown bold/italic markers, keeping the enclosed plain text."""
    text = _DOUBLE_EMPHASIS_RE.sub(r"\1", text)
    text = _SINGLE_EMPHASIS_RE.sub(r"\1", text)
    return text.strip()


def strip_stage_directions(text: str) -> str:
    """Removes italicized stage directions from dialogue (e.g. "*laughs*", "*pause*").

    These are not spoken by TTS. Directions bracketed by em dashes (e.g.
    "Look at this — *crouches* — a fairy ring") collapse to a single em dash
    rather than leaving a dangling "— —".
    """
    text = _SINGLE_EMPHASIS_RE.sub(" ", text)
    text = _DOUBLE_EM_DASH_RE.sub(" — ", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text.strip()


def resolve_speaker_name(raw_label: str) -> str:
    """Resolves a raw speaker label to its display name.

    "Student 1 (Emma)" -> "Emma"; "Daughter (Emma, 16)" -> "Emma";
    "Mr. Hassan" -> "Mr. Hassan" (no parenthetical, used as-is).
    """
    match = re.search(r"\(([^)]+)\)", raw_label)
    if match:
        inner = match.group(1)
        return inner.split(",")[0].strip()
    return raw_label.strip()


def parse_category_file(path: str | Path) -> Category:
    """Parses one category Markdown file into a Category with its Lessons."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()

    category_number: int | None = None
    title_en: str | None = None
    title_ar: str | None = None
    level: str | None = None

    for line in lines[:10]:
        header_match = _CATEGORY_HEADER_RE.match(line.strip())
        if header_match:
            category_number = int(header_match.group(1))
            title_en = header_match.group(2).strip()
            title_ar = header_match.group(3).strip()
            continue
        level_match = _LEVEL_RE.search(line)
        if level_match:
            level = level_match.group(1).strip()

    if category_number is None or level is None:
        raise ValueError(f"Could not parse category header/level lines in {path}")

    category = Category(
        number=category_number,
        title_en=title_en or "",
        title_ar=title_ar or "",
        level=level,
        source_file=str(path),
    )

    lesson_starts = [i for i, line in enumerate(lines) if _LESSON_HEADER_RE.match(line.strip())]
    for position, start in enumerate(lesson_starts):
        end = lesson_starts[position + 1] if position + 1 < len(lesson_starts) else len(lines)
        block = lines[start:end]
        header_line = block[0].strip()
        try:
            lesson = _parse_lesson_block(block, source_file=str(path))
            category.lessons.append(lesson)
        except Exception as exc:  # noqa: BLE001 - tolerant parsing by design
            category.parse_errors.append(
                ParseError(file=str(path), lesson_header=header_line, message=str(exc))
            )

    return category


def _parse_lesson_block(block: list[str], source_file: str) -> Lesson:
    header_line = block[0].strip()
    header_match = _LESSON_HEADER_RE.match(header_line)
    if not header_match:
        raise ValueError(f"Invalid lesson header: {header_line!r}")
    number = int(header_match.group(1))
    title_en = header_match.group(2).strip()
    title_ar = header_match.group(3).strip()

    n = len(block)
    i = 1

    while i < n and not block[i].strip().startswith("**Scenario:**"):
        i += 1
    if i >= n:
        raise ValueError("Missing **Scenario:** section")
    scenario_text = block[i].strip()[len("**Scenario:**") :].strip()
    scenario = strip_emphasis(scenario_text)
    i += 1

    while i < n and not block[i].strip().startswith("**Host Intro:**"):
        i += 1
    if i >= n:
        raise ValueError("Missing **Host Intro:** section")
    i += 1
    host_intro_lines: list[str] = []
    while i < n and block[i].strip() != "---":
        line = block[i].strip()
        if line:
            host_intro_lines.append(line)
        i += 1
    if i >= n:
        raise ValueError("Missing '---' separator after Host Intro")
    if not host_intro_lines:
        raise ValueError("Empty Host Intro")
    host_intro = strip_emphasis(" ".join(host_intro_lines))
    i += 1  # skip the '---' separator

    turns: list[DialogueTurn] = []
    current_speaker: str | None = None
    current_raw_label: str | None = None
    current_paragraphs: list[list[str]] = []

    def flush_turn() -> None:
        if current_speaker is None:
            return
        paragraphs = tuple(
            strip_emphasis(strip_stage_directions(" ".join(p))) for p in current_paragraphs if p
        )
        paragraphs = tuple(p for p in paragraphs if p)
        if paragraphs:
            turns.append(
                DialogueTurn(
                    speaker=current_speaker,
                    raw_speaker_label=current_raw_label or current_speaker,
                    paragraphs=paragraphs,
                )
            )

    while i < n and not block[i].strip().startswith("**Key Vocabulary:**"):
        stripped = block[i].strip()
        if stripped == "---":
            i += 1
            continue
        speaker_match = _SPEAKER_LINE_RE.match(stripped)
        if speaker_match:
            flush_turn()
            raw_label = speaker_match.group(1).strip()
            current_speaker = resolve_speaker_name(raw_label)
            current_raw_label = raw_label
            first_text = speaker_match.group(2).strip()
            current_paragraphs = [[first_text]] if first_text else [[]]
        elif stripped == "":
            if current_paragraphs and current_paragraphs[-1]:
                current_paragraphs.append([])
        else:
            if current_speaker is None:
                raise ValueError(f"Dialogue text found before any speaker label: {stripped!r}")
            if not current_paragraphs:
                current_paragraphs = [[]]
            current_paragraphs[-1].append(stripped)
        i += 1
    flush_turn()

    if i >= n:
        raise ValueError("Missing **Key Vocabulary:** section")
    if not turns:
        raise ValueError("No dialogue turns found")

    i += 1  # skip the '**Key Vocabulary:**' heading line
    vocabulary: list[VocabItem] = []
    while i < n and block[i].strip() not in ("---", ""):
        vocab_match = _VOCAB_LINE_RE.match(block[i].strip())
        if vocab_match:
            term = strip_emphasis(vocab_match.group(1))
            definition = vocab_match.group(2).strip()
            vocabulary.append(VocabItem(term=term, definition=definition))
        i += 1
    if not vocabulary:
        raise ValueError("No vocabulary items found")

    return Lesson(
        number=number,
        title_en=title_en,
        title_ar=title_ar,
        scenario=scenario,
        host_intro=host_intro,
        turns=tuple(turns),
        vocabulary=tuple(vocabulary),
        source_file=source_file,
        raw_header=header_line,
    )
