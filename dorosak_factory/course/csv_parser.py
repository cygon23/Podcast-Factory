"""Parses the 5 Dorosak course CSVs into course/models.py dataclasses.

Groups rows by section (book_id, unit_id, lesson_id, section_id all appear
duplicated on every row of a section, mirroring the real CSV export) and
skips rows that already have real recorded audio - see the "existing
audio" finding in docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md.

Dialogues skip at the whole-section level (section_audio_link marks one
combined recording for the whole conversation - individual lines are
never separately recorded). Vocabulary/Examples/Useful Phrases skip at
the individual-item level (item_audio_link marks one specific word/
sentence as already recorded, independent of its siblings in the section).
"""

from __future__ import annotations

import csv
from pathlib import Path

from dorosak_factory.course.models import (
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    Unit,
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _has_existing_audio(row: dict[str, str]) -> bool:
    return bool(row["item_audio_link"].strip()) or bool(row["section_audio_link"].strip())


def _book_unit_lesson(row: dict[str, str]) -> tuple[Book, Unit, CourseLesson]:
    book = Book(book_id=int(row["book_id"]), name=row["book_name"])
    unit = Unit(unit_id=int(row["unit_id"]), book_id=book.book_id, name=row["unit_name"])
    lesson = CourseLesson(
        lesson_id=int(row["lesson_id"]),
        unit_id=unit.unit_id,
        book_id=book.book_id,
        name=row["lesson_name"],
    )
    return book, unit, lesson


def _group_by_section(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["section_id"], []).append(row)
    return groups


def parse_dialogues_csv(path: Path) -> list[DialogueSection]:
    """Parses dialogues.csv: one DialogueSection per lesson's Teacher/Student conversation."""
    rows = _read_rows(path)
    sections: list[DialogueSection] = []
    for section_rows in _group_by_section(rows).values():
        if any(_has_existing_audio(r) for r in section_rows):
            continue
        book, unit, lesson = _book_unit_lesson(section_rows[0])
        ordered = sorted(section_rows, key=lambda r: int(r["item_no"]))
        lines = tuple(_parse_dialogue_line(r) for r in ordered)
        sections.append(DialogueSection(book=book, unit=unit, lesson=lesson, lines=lines))
    return sections


def _parse_dialogue_line(row: dict[str, str]) -> DialogueLine:
    speaker, _, text = row["item_text"].partition(":")
    return DialogueLine(item_no=int(row["item_no"]), speaker=speaker.strip(), text=text.strip())
