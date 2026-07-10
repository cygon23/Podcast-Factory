"""Dataclasses representing the parsed structure of a Dorosak lesson script."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VocabItem:
    """One Key Vocabulary entry. Not spoken in audio; rendered as a text screen."""

    term: str
    definition: str


@dataclass(frozen=True)
class DialogueTurn:
    """One spoken turn by a single character."""

    speaker: str
    raw_speaker_label: str
    paragraphs: tuple[str, ...]

    @property
    def text(self) -> str:
        """Full turn text, paragraphs joined for reading; use `paragraphs` for pause timing."""
        return "\n\n".join(self.paragraphs)


@dataclass(frozen=True)
class Lesson:
    """A single lesson parsed from a category Markdown file."""

    number: int
    title_en: str
    title_ar: str
    scenario: str
    host_intro: str
    turns: tuple[DialogueTurn, ...]
    vocabulary: tuple[VocabItem, ...]
    source_file: str
    raw_header: str


@dataclass(frozen=True)
class ParseError:
    """Records a lesson block that failed to parse, without aborting the run."""

    file: str
    lesson_header: str
    message: str


@dataclass
class Category:
    """A parsed category Markdown file: metadata plus all successfully parsed lessons."""

    number: int
    title_en: str
    title_ar: str
    level: str
    source_file: str
    lessons: list[Lesson] = field(default_factory=list)
    parse_errors: list[ParseError] = field(default_factory=list)
