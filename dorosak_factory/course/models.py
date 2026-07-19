"""Content models for the course CSV audio pipeline.

Deliberately separate from dorosak_factory.parser.models (Category/Lesson/
DialogueTurn/VocabItem) - those model the cat*/Markdown "English for X"
podcast pipeline. These model Dorosak's actual course catalog (book/unit/
lesson/section, 5 distinct content shapes per lesson), sourced from a CSV
export rather than Markdown. Kept separate rather than shared because
forcing one model to fit both would blur two genuinely different content
shapes into an awkward compromise.

Vocabulary and Examples share a shape (English/Arabic pairs) and so share
BilingualItem/BilingualSection; Useful Phrases (English-only) and Article
(one passage, no per-item list) each get their own shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    book_id: int
    name: str


@dataclass(frozen=True)
class Unit:
    unit_id: int
    book_id: int
    name: str


@dataclass(frozen=True)
class CourseLesson:
    lesson_id: int
    unit_id: int
    book_id: int
    name: str


@dataclass(frozen=True)
class DialogueLine:
    item_no: int
    speaker: str  # "Teacher" | "Student"
    text: str


@dataclass(frozen=True)
class DialogueSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    lines: tuple[DialogueLine, ...]


@dataclass(frozen=True)
class BilingualItem:
    """One vocabulary word or example sentence, paired with its Arabic translation."""

    item_no: int
    english: str
    arabic: str


@dataclass(frozen=True)
class BilingualSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    items: tuple[BilingualItem, ...]


@dataclass(frozen=True)
class PhraseItem:
    item_no: int
    text: str


@dataclass(frozen=True)
class PhraseSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    items: tuple[PhraseItem, ...]


@dataclass(frozen=True)
class ArticleSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    text: str
