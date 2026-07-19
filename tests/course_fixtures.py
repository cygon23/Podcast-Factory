"""Builds one row of the 5 course CSVs' shared 34-column header from keyword
arguments, so tests never hand-count commas in raw CSV text.
"""

from __future__ import annotations

CSV_HEADER = (
    "book_id,book_name,unit_id,unit_name,unit_sort,lesson_id,lesson_name,lesson_sort,"
    "page_id,page_title,page_index,page_sort,section_id,section_title,section_type,"
    "section_sort,locale,item_no,item_text,item_audio_link,item_video_link,content_text,"
    "content_html,section_audio_link,section_video_link,image_link,reference_link,"
    "reference_text,quiz_id,page_created_at,page_updated_at,section_created_at,"
    "section_updated_at,content_missing"
)


def csv_row(
    book_id: int = 1,
    book_name: str = "Mastering English with Dorosak (Beginner)",
    unit_id: int = 6,
    unit_name: str = "Unit 1: Basics",
    unit_sort: int = 1,
    lesson_id: int = 20,
    lesson_name: str = "Lesson 1: Alphabet Basics",
    lesson_sort: int = 1,
    page_id: int = 60,
    page_title: str = "Dialogue",
    page_index: int = 7,
    page_sort: int = 7,
    section_id: str = "74",
    section_title: str = "Dialogue",
    section_type: str = "text",
    section_sort: int = 0,
    locale: str = "en",
    item_no: int = 1,
    item_text: str = "",
    item_audio_link: str = "",
    item_video_link: str = "",
    content_text: str = "",
    content_html: str = "",
    section_audio_link: str = "",
    section_video_link: str = "",
    image_link: str = "",
    reference_link: str = "",
    reference_text: str = "",
    quiz_id: str = "",
    page_created_at: str = "",
    page_updated_at: str = "",
    section_created_at: str = "",
    section_updated_at: str = "",
    content_missing: int = 0,
) -> str:
    """Returns one CSV data row (no trailing newline) matching CSV_HEADER's column order.

    No field used across this test suite contains a comma, so plain
    comma-joining is safe - no CSV quoting/escaping needed.
    """
    fields = [
        book_id, book_name, unit_id, unit_name, unit_sort, lesson_id, lesson_name,
        lesson_sort, page_id, page_title, page_index, page_sort, section_id,
        section_title, section_type, section_sort, locale, item_no, item_text,
        item_audio_link, item_video_link, content_text, content_html,
        section_audio_link, section_video_link, image_link, reference_link,
        reference_text, quiz_id, page_created_at, page_updated_at,
        section_created_at, section_updated_at, content_missing,
    ]
    return ",".join(str(f) for f in fields)
