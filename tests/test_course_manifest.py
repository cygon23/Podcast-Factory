from __future__ import annotations

from dorosak_factory.course.course_manifest import CourseItemRecord, CourseManifest


def test_new_item_needs_processing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is True
    finally:
        manifest.close()


def test_successful_item_does_not_need_reprocessing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary",
                book_id=1,
                unit_id=6,
                lesson_id=20,
                section_id="77",
                item_no=1,
                output_path="output/course/beginner/unit6/lesson20/vocabulary/1_alphabet.mp3",
                status="success",
                failure_reason=None,
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is False
    finally:
        manifest.close()


def test_force_reprocesses_even_successful_item(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary", book_id=1, unit_id=6, lesson_id=20, section_id="77",
                item_no=1, output_path="x.mp3", status="success", failure_reason=None,
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1, force=True) is True
    finally:
        manifest.close()


def test_failed_item_needs_reprocessing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary", book_id=1, unit_id=6, lesson_id=20, section_id="77",
                item_no=1, output_path=None, status="failed", failure_reason="synthesis error",
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is True
    finally:
        manifest.close()


def test_manifest_coexists_in_same_db_file_as_the_lessons_table(tmp_path):
    # Additive constraint: this new table must not collide with the
    # existing cat*/Markdown pipeline's manifest.Manifest, which uses the
    # same physical SQLite file (output/manifest.sqlite3) with a different
    # table ("lessons").
    from dorosak_factory.manifest.store import Manifest

    db_path = tmp_path / "manifest.sqlite3"
    lessons_manifest = Manifest(db_path=db_path)
    course_manifest = CourseManifest(db_path=db_path)
    try:
        assert lessons_manifest.all_records() == []
        assert course_manifest.all_records() == []
    finally:
        lessons_manifest.close()
        course_manifest.close()
