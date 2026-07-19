from __future__ import annotations

from pathlib import Path

from tests.course_fixtures import CSV_HEADER, csv_row


def _write_csv(tmp_path: Path, name: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_parse_dialogues_csv_groups_lines_by_section_in_item_no_order(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(section_id="74", item_no=2, item_text="Student: Hello, teacher."),
        csv_row(section_id="74", item_no=1, item_text="Teacher: Welcome to class."),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert len(sections) == 1
    assert [line.item_no for line in sections[0].lines] == [1, 2]
    assert sections[0].lines[0].speaker == "Teacher"
    assert sections[0].lines[0].text == "Welcome to class."
    assert sections[0].lines[1].speaker == "Student"
    assert sections[0].book.name == "Mastering English with Dorosak (Beginner)"
    assert sections[0].lesson.lesson_id == 20


def test_parse_dialogues_csv_separates_multiple_lessons(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(section_id="74", lesson_id=20, item_no=1, item_text="Teacher: Hi."),
        csv_row(section_id="80", lesson_id=21, item_no=1, item_text="Teacher: Bye."),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert {s.lesson.lesson_id for s in sections} == {20, 21}


def test_parse_dialogues_csv_skips_section_with_existing_section_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(
            section_id="74",
            item_no=1,
            item_text="Teacher: Hi.",
            section_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert sections == []


def test_split_bilingual_dash_separates_english_and_arabic():
    from dorosak_factory.course.csv_parser import split_bilingual_dash

    english, arabic = split_bilingual_dash("This is the letter A. — هذا هو الحرف A.")
    assert english == "This is the letter A."
    assert arabic == "هذا هو الحرف A."


def test_split_bilingual_tab_separates_english_and_arabic():
    from dorosak_factory.course.csv_parser import split_bilingual_tab

    english, arabic = split_bilingual_tab("Alphabet\tالأبجدية")
    assert english == "Alphabet"
    assert arabic == "الأبجدية"


def test_parse_examples_csv_splits_dash_separated_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_examples_csv

    rows = [
        csv_row(
            section_id="75",
            item_no=1,
            item_text="This is the letter A. — هذا هو الحرف A.",
        ),
    ]
    path = _write_csv(tmp_path, "examples.csv", rows)

    sections = parse_examples_csv(path)

    assert len(sections) == 1
    assert sections[0].items[0].english == "This is the letter A."
    assert sections[0].items[0].arabic == "هذا هو الحرف A."


def test_parse_vocabulary_csv_splits_tab_separated_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_vocabulary_csv

    rows = [csv_row(section_id="77", item_no=1, item_text="Alphabet\tالأبجدية")]
    path = _write_csv(tmp_path, "vocabulary.csv", rows)

    sections = parse_vocabulary_csv(path)

    assert sections[0].items[0].english == "Alphabet"
    assert sections[0].items[0].arabic == "الأبجدية"


def test_parse_vocabulary_csv_skips_only_items_with_existing_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_vocabulary_csv

    rows = [
        csv_row(
            section_id="77",
            item_no=1,
            item_text="Alphabet\tالأبجدية",
            item_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
        csv_row(section_id="77", item_no=2, item_text="Letter\tحرف"),
    ]
    path = _write_csv(tmp_path, "vocabulary.csv", rows)

    sections = parse_vocabulary_csv(path)

    assert len(sections) == 1
    assert len(sections[0].items) == 1
    assert sections[0].items[0].english == "Letter"


def test_parse_useful_phrases_csv_keeps_plain_text_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_useful_phrases_csv

    rows = [
        csv_row(section_id="76", item_no=1, item_text="This is a letter."),
        csv_row(section_id="76", item_no=2, item_text="These are letters."),
    ]
    path = _write_csv(tmp_path, "useful_phrases.csv", rows)

    sections = parse_useful_phrases_csv(path)

    assert len(sections[0].items) == 2
    assert sections[0].items[0].text == "This is a letter."


def test_parse_articles_csv_uses_content_text_not_item_text(tmp_path):
    from dorosak_factory.course.csv_parser import parse_articles_csv

    rows = [
        csv_row(
            section_id="78",
            item_no=1,
            item_text="Article (Alphabet Basics)",
            content_text="The English alphabet is the foundation of the language.",
        ),
    ]
    path = _write_csv(tmp_path, "articles.csv", rows)

    sections = parse_articles_csv(path)

    assert len(sections) == 1
    assert sections[0].text == "The English alphabet is the foundation of the language."


def test_parse_articles_csv_skips_rows_with_existing_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_articles_csv

    rows = [
        csv_row(
            section_id="78",
            item_no=1,
            content_text="Already recorded article.",
            item_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
    ]
    path = _write_csv(tmp_path, "articles.csv", rows)

    sections = parse_articles_csv(path)

    assert sections == []
