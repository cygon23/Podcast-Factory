"""Tests for the Markdown -> Lesson parser, run against the two real sample files."""

from __future__ import annotations

from pathlib import Path

import pytest

from dorosak_factory.parser.markdown_parser import parse_category_file

INPUT_DIR = Path(__file__).resolve().parent.parent / "input"
CAT30_PATH = INPUT_DIR / "cat30_weather_nature_all50_scripts.md"
CAT31_PATH = INPUT_DIR / "cat31_science_technology_all50_scripts.md"


@pytest.fixture(scope="module")
def cat30():
    return parse_category_file(CAT30_PATH)


@pytest.fixture(scope="module")
def cat31():
    return parse_category_file(CAT31_PATH)


# --- Category-level metadata ---------------------------------------------


def test_cat30_metadata(cat30):
    assert cat30.number == 30
    assert cat30.title_en == "English for Weather & Nature Daily Life"
    assert cat30.title_ar == "الإنجليزية للطقس والطبيعة في الحياة اليومية"
    assert cat30.level == "Beginner & Intermediate"


def test_cat31_metadata(cat31):
    assert cat31.number == 31
    assert cat31.title_en == "English for Science & Technology"
    assert cat31.title_ar == "الإنجليزية للعلوم والتكنولوجيا"
    assert cat31.level == "Beginner & Intermediate"


# --- Lesson counts ----------------------------------------------------------


def test_cat30_has_fifty_lessons(cat30):
    assert len(cat30.lessons) == 50


def test_cat31_has_fifty_lessons(cat31):
    assert len(cat31.lessons) == 50


def test_cat30_lesson_numbers_are_sequential(cat30):
    assert [lesson.number for lesson in cat30.lessons] == list(range(1, 51))


def test_cat31_lesson_numbers_are_sequential(cat31):
    assert [lesson.number for lesson in cat31.lessons] == list(range(1, 51))


def test_no_parse_errors_on_real_files(cat30, cat31):
    assert cat30.parse_errors == []
    assert cat31.parse_errors == []


# --- Lesson 1 spot checks: cat30 --------------------------------------------


def test_cat30_lesson1_titles(cat30):
    lesson = cat30.lessons[0]
    assert lesson.number == 1
    assert lesson.title_en == "Talking About Today's Weather"
    assert lesson.title_ar == "الحديث عن طقس اليوم"


def test_cat30_lesson1_scenario(cat30):
    lesson = cat30.lessons[0]
    assert lesson.scenario == (
        "Two colleagues greet each other on a rainy Monday morning " "and talk about the weather."
    )


def test_cat30_lesson1_host_intro(cat30):
    lesson = cat30.lessons[0]
    assert lesson.host_intro.startswith("Welcome to Dorosak English Podcast!")
    assert "Category 30" in lesson.host_intro
    assert "*" not in lesson.host_intro


def test_cat30_lesson1_first_and_last_turn(cat30):
    lesson = cat30.lessons[0]
    assert lesson.turns[0].speaker == "Tom"
    assert lesson.turns[0].text.startswith("Morning, Priya.")
    assert lesson.turns[-1].speaker == "Tom"
    assert lesson.turns[-1].text == "Desperately needed. Yes please."


def test_cat30_lesson1_turn_count(cat30):
    lesson = cat30.lessons[0]
    assert len(lesson.turns) == 15


def test_cat30_lesson1_vocabulary(cat30):
    lesson = cat30.lessons[0]
    assert len(lesson.vocabulary) == 7
    first = lesson.vocabulary[0]
    assert first.term == "Miserable"
    assert first.definition == ("very unpleasant, used frequently for bad weather in Britain")
    last = lesson.vocabulary[-1]
    assert last.term == "Waterproof"


def test_cat30_lesson1_stage_direction_removed(cat30):
    # "*sympathetically* Oh no. ..." -> stage direction dropped entirely, not spoken.
    lesson = cat30.lessons[0]
    turn = lesson.turns[5]
    assert turn.speaker == "Priya"
    assert "*" not in turn.text
    assert "sympathetically" not in turn.text
    assert turn.text == "Oh no. There's nothing worse than wet trousers at the start of the day."


def test_stage_direction_between_em_dashes_removed_cleanly(cat30):
    # Lesson 13, Rosa: 'Look at this — *crouches* — a fairy ring of mushrooms.'
    lesson = next(lsn for lsn in cat30.lessons if lsn.number == 13)
    turn = next(t for t in lesson.turns if "fairy ring" in t.text)
    assert "*" not in turn.text
    assert "crouches" not in turn.text
    assert "— —" not in turn.text
    assert "Look at this — a fairy ring of mushrooms." in turn.text


def test_mid_sentence_stage_direction_removed(cat30):
    # Lesson 10, Dad (Tom): 'That means the drive is icy...' preceded by '*groans*'
    lesson = next(lsn for lsn in cat30.lessons if lsn.number == 10)
    turn = next(t for t in lesson.turns if "icy" in t.text)
    assert "*" not in turn.text
    assert "groans" not in turn.text
    assert turn.text.startswith("That means the drive is icy")


# --- Lesson 1 spot checks: cat31 --------------------------------------------


def test_cat31_lesson1_titles(cat31):
    lesson = cat31.lessons[0]
    assert lesson.title_en == "Talking About Science in Daily Life"
    assert lesson.title_ar == "الحديث عن العلوم في الحياة اليومية"


def test_cat31_lesson1_turns(cat31):
    lesson = cat31.lessons[0]
    assert lesson.turns[0].speaker == "Priya"
    assert lesson.turns[-1].speaker == "Priya"
    assert lesson.turns[-1].text == "He is. Science is very polite like that — doing the work invisibly."


def test_cat31_lesson1_vocabulary_count(cat31):
    lesson = cat31.lessons[0]
    assert len(lesson.vocabulary) == 7
    assert lesson.vocabulary[-1].term == "GPS"


# --- Speaker display-name resolution (parenthetical forms) ------------------


def test_speaker_with_simple_parenthetical_name(cat30):
    # "Mum (Sara):" -> display name "Sara"
    lesson = cat30.lessons[1]  # Lesson 2
    speakers = {t.speaker for t in lesson.turns}
    assert "Sara" in speakers
    assert not any(s.startswith("Mum") for s in speakers)


def test_speaker_with_age_in_parenthetical(cat30):
    # Lesson 39 has "Daughter (Emma, 16):" -> display name "Emma", not "Emma, 16"
    lesson = cat30.lessons[38]
    assert lesson.number == 39
    speakers = {t.speaker for t in lesson.turns}
    assert "Emma" in speakers
    assert not any("16" in s for s in speakers)


def test_speaker_reintroduced_without_parenthetical_matches_same_name(cat31):
    # Lesson 2: "Student 1 (Emma):" then later plain "Emma:" - same display name.
    lesson = cat31.lessons[1]
    speakers = [t.speaker for t in lesson.turns]
    assert "Emma" in speakers
    assert speakers.count("Emma") >= 2


def test_speaker_with_role_and_descriptor_in_parenthetical():
    # "Speaker 1 (Rosa, gardener):" -> display name "Rosa"
    category = parse_category_file(CAT30_PATH)
    all_speakers = {t.speaker for lesson in category.lessons for t in lesson.turns}
    assert "Rosa" in all_speakers
    assert not any("gardener" in s for s in all_speakers)


# --- Multi-paragraph turns ---------------------------------------------------


def test_multi_paragraph_turn_is_captured(cat31):
    # Lesson 2, Mr. Hassan's first turn spans two paragraphs separated by a blank line.
    lesson = cat31.lessons[1]
    turn = lesson.turns[0]
    assert turn.speaker == "Mr. Hassan"
    assert len(turn.paragraphs) == 2
    assert turn.paragraphs[0].endswith("I want to challenge that today.")
    assert turn.paragraphs[1].startswith("Science is not a collection of facts.")
    assert "\n\n" in turn.text


# --- Tolerant parsing: malformed lesson should not crash the whole file -----


def test_tolerant_parsing_logs_bad_lesson_and_continues(tmp_path):
    content = """# Category 99: Test Category — عنوان تجريبي
## Dorosak English Podcast | Level: Beginner
## All 2 Podcast Dialogue Scripts

---

## Lesson 1: Good Lesson | عنوان جيد

**Scenario:** A working lesson.

**Host Intro:**
Intro text.

---
**Tom:** Hello there.

**Key Vocabulary:**
- *Word* — a definition

---

## Lesson 2: Broken Lesson | عنوان معطل

This lesson is missing all required sections and should fail to parse.

---
"""
    bad_file = tmp_path / "cat99_test.md"
    bad_file.write_text(content, encoding="utf-8")

    category = parse_category_file(bad_file)

    assert len(category.lessons) == 1
    assert category.lessons[0].number == 1
    assert len(category.parse_errors) == 1
    assert category.parse_errors[0].file == str(bad_file)
    assert "Lesson 2" in category.parse_errors[0].lesson_header
