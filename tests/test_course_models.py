from __future__ import annotations

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


def _book_unit_lesson():
    book = Book(book_id=1, name="Mastering English with Dorosak (Beginner)")
    unit = Unit(unit_id=6, book_id=1, name="Unit 1: Basics")
    lesson = CourseLesson(lesson_id=20, unit_id=6, book_id=1, name="Lesson 1: Alphabet Basics")
    return book, unit, lesson


def test_dialogue_section_holds_ordered_lines():
    book, unit, lesson = _book_unit_lesson()
    lines = (
        DialogueLine(item_no=1, speaker="Teacher", text="Welcome."),
        DialogueLine(item_no=2, speaker="Student", text="Hello."),
    )
    section = DialogueSection(book=book, unit=unit, lesson=lesson, lines=lines)
    assert section.lines[0].speaker == "Teacher"
    assert section.lesson.name == "Lesson 1: Alphabet Basics"


def test_bilingual_section_holds_english_arabic_pairs():
    book, unit, lesson = _book_unit_lesson()
    items = (BilingualItem(item_no=1, english="Alphabet", arabic="الأبجدية"),)
    section = BilingualSection(book=book, unit=unit, lesson=lesson, items=items)
    assert section.items[0].english == "Alphabet"
    assert section.items[0].arabic == "الأبجدية"


def test_phrase_section_holds_plain_text_items():
    book, unit, lesson = _book_unit_lesson()
    items = (PhraseItem(item_no=1, text="How do you say this?"),)
    section = PhraseSection(book=book, unit=unit, lesson=lesson, items=items)
    assert section.items[0].text == "How do you say this?"


def test_article_section_holds_one_passage():
    book, unit, lesson = _book_unit_lesson()
    section = ArticleSection(book=book, unit=unit, lesson=lesson, text="The alphabet is...")
    assert section.text == "The alphabet is..."
