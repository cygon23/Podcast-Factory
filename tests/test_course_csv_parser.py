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
