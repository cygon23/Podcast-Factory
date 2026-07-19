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
    ArticleSection,
    BilingualItem,
    BilingualSection,
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    PhraseItem,
    PhraseSection,
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


def split_bilingual_dash(text: str) -> tuple[str, str]:
    """Splits "English sentence — Arabic translation" on the em-dash separator."""
    english, _, arabic = text.partition(" — ")
    return english.strip(), arabic.strip()


def split_bilingual_tab(text: str) -> tuple[str, str]:
    """Splits "English word\\tArabic translation" on the tab separator."""
    english, _, arabic = text.partition("\t")
    return english.strip(), arabic.strip()


def _parse_bilingual_csv(path: Path, split_fn) -> list[BilingualSection]:
    rows = _read_rows(path)
    sections: list[BilingualSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        items = tuple(_parse_bilingual_item(r, split_fn) for r in ordered)
        sections.append(BilingualSection(book=book, unit=unit, lesson=lesson, items=items))
    return sections


def _parse_bilingual_item(row: dict[str, str], split_fn) -> BilingualItem:
    english, arabic = split_fn(row["item_text"])
    return BilingualItem(item_no=int(row["item_no"]), english=english, arabic=arabic)


def parse_examples_csv(path: Path) -> list[BilingualSection]:
    """Parses examples.csv: "English — Arabic" sentence pairs, grouped per lesson."""
    return _parse_bilingual_csv(path, split_bilingual_dash)


def parse_vocabulary_csv(path: Path) -> list[BilingualSection]:
    """Parses vocabulary.csv: "English\\tArabic" word pairs, grouped per lesson."""
    return _parse_bilingual_csv(path, split_bilingual_tab)


def parse_useful_phrases_csv(path: Path) -> list[PhraseSection]:
    """Parses useful_phrases.csv: plain English phrases, grouped per lesson."""
    rows = _read_rows(path)
    sections: list[PhraseSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        items = tuple(
            PhraseItem(item_no=int(r["item_no"]), text=r["item_text"].strip()) for r in ordered
        )
        sections.append(PhraseSection(book=book, unit=unit, lesson=lesson, items=items))
    return sections


def parse_articles_csv(path: Path) -> list[ArticleSection]:
    """Parses articles.csv: one reading passage per lesson.

    Unlike the other 4 CSVs, the spoken content lives in `content_text`
    (the article body), not `item_text` (just a short title like
    "Article (Alphabet Basics)").
    """
    rows = _read_rows(path)
    sections: list[ArticleSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        text = " ".join(r["content_text"].strip() for r in ordered if r["content_text"].strip())
        sections.append(ArticleSection(book=book, unit=unit, lesson=lesson, text=text))
    return sections
