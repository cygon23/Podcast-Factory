"""Tests for the SQLite manifest: content hashing, diff/skip logic, persistence."""

from __future__ import annotations

import pytest

from dorosak_factory.manifest.store import Manifest, ManifestRecord
from dorosak_factory.parser.models import Category, DialogueTurn, Lesson, VocabItem


def make_lesson(number=1, host_intro="Welcome."):
    return Lesson(
        number=number,
        title_en="T",
        title_ar="ت",
        scenario="s",
        host_intro=host_intro,
        turns=(DialogueTurn(speaker="Tom", raw_speaker_label="Tom", paragraphs=("Hi.",)),),
        vocabulary=(VocabItem(term="t", definition="d"),),
        source_file="f.md",
        raw_header="## Lesson 1",
    )


@pytest.fixture
def manifest(tmp_path):
    m = Manifest(db_path=tmp_path / "manifest.sqlite3")
    yield m
    m.close()


def test_unknown_lesson_needs_processing(manifest):
    lesson = make_lesson()
    assert manifest.needs_processing(category_number=30, lesson=lesson, engine="null") is True


def test_lesson_with_matching_hash_and_success_does_not_need_processing(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )
    assert (
        manifest.needs_processing(category_number=30, lesson=lesson, engine="null", formats="audio")
        is False
    )


def test_changed_lesson_content_needs_reprocessing(manifest):
    lesson = make_lesson(host_intro="Welcome.")
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )
    changed_lesson = make_lesson(host_intro="Welcome, everybody!")
    assert manifest.needs_processing(category_number=30, lesson=changed_lesson, engine="null") is True


def test_failed_lesson_needs_reprocessing(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path=None,
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="failed",
            failure_reason="ffmpeg crashed",
        )
    )
    assert manifest.needs_processing(category_number=30, lesson=lesson, engine="null") is True


def test_force_always_needs_processing(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )
    assert (
        manifest.needs_processing(category_number=30, lesson=lesson, engine="null", force=True) is True
    )


def test_different_engine_needs_reprocessing(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )
    assert manifest.needs_processing(category_number=30, lesson=lesson, engine="openai") is True


def test_manifest_persists_across_instances(tmp_path):
    lesson = make_lesson()
    db_path = tmp_path / "manifest.sqlite3"

    m1 = Manifest(db_path=db_path)
    content_hash = m1.compute_content_hash(lesson)
    m1.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=content_hash,
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )
    m1.close()

    m2 = Manifest(db_path=db_path)
    assert (
        m2.needs_processing(category_number=30, lesson=lesson, engine="null", formats="audio") is False
    )
    record = m2.get_record(category_number=30, lesson_number=1)
    assert record.audio_path == "a.mp3"
    m2.close()


def test_plan_run_reports_new_changed_and_skipped(manifest):
    category = Category(number=30, title_en="C", title_ar="c", level="Beginner", source_file="f.md")
    lesson1 = make_lesson(number=1)
    lesson2 = make_lesson(number=2)
    category.lessons.extend([lesson1, lesson2])

    # pre-mark lesson1 as already successfully processed
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=1,
            content_hash=manifest.compute_content_hash(lesson1),
            engine="null",
            audio_path="a.mp3",
            video_16x9_path=None,
            video_9x16_path=None,
            srt_path=None,
            metadata_json_path=None,
            status="success",
            failure_reason=None,
        )
    )

    plan = manifest.plan_run([category], engine="null", formats="audio")

    to_process_numbers = {item.lesson.number for item in plan if item.needs_processing}
    skipped_numbers = {item.lesson.number for item in plan if not item.needs_processing}
    assert to_process_numbers == {2}
    assert skipped_numbers == {1}


def test_compute_content_hash_is_stable_and_sensitive_to_vocab():
    lesson_a = make_lesson()
    lesson_b = Lesson(
        number=1,
        title_en="T",
        title_ar="ت",
        scenario="s",
        host_intro="Welcome.",
        turns=(DialogueTurn(speaker="Tom", raw_speaker_label="Tom", paragraphs=("Hi.",)),),
        vocabulary=(VocabItem(term="t", definition="DIFFERENT definition"),),
        source_file="f.md",
        raw_header="## Lesson 1",
    )
    m = Manifest(db_path=None)
    hash_a1 = m.compute_content_hash(lesson_a)
    hash_a2 = m.compute_content_hash(lesson_a)
    hash_b = m.compute_content_hash(lesson_b)
    assert hash_a1 == hash_a2
    assert hash_a1 != hash_b
    m.close()


def _audio_only_success_record(lesson, content_hash):
    return ManifestRecord(
        category_number=30,
        lesson_number=lesson.number,
        content_hash=content_hash,
        engine="kokoro",
        audio_path="a.mp3",
        video_16x9_path=None,
        video_9x16_path=None,
        srt_path="a.srt",
        metadata_json_path="m.json",
        status="success",
        failure_reason=None,
    )


def test_audio_only_success_does_not_need_reprocessing_for_audio_format(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(_audio_only_success_record(lesson, content_hash))

    needs = manifest.needs_processing(
        category_number=30, lesson=lesson, engine="kokoro", formats="audio"
    )

    assert needs is False


def test_audio_only_success_needs_reprocessing_when_video_requested(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(_audio_only_success_record(lesson, content_hash))

    needs_video = manifest.needs_processing(
        category_number=30, lesson=lesson, engine="kokoro", formats="video"
    )
    needs_both = manifest.needs_processing(
        category_number=30, lesson=lesson, engine="kokoro", formats="both"
    )

    assert needs_video is True
    assert needs_both is True


def test_lesson_with_both_formats_already_done_does_not_need_reprocessing(manifest):
    lesson = make_lesson()
    content_hash = manifest.compute_content_hash(lesson)
    manifest.upsert_record(
        ManifestRecord(
            category_number=30,
            lesson_number=lesson.number,
            content_hash=content_hash,
            engine="kokoro",
            audio_path="a.mp3",
            video_16x9_path="v1.mp4",
            video_9x16_path="v2.mp4",
            srt_path="a.srt",
            metadata_json_path="m.json",
            status="success",
            failure_reason=None,
        )
    )

    assert (
        manifest.needs_processing(category_number=30, lesson=lesson, engine="kokoro", formats="both")
        is False
    )


def test_plan_run_passes_formats_through_to_needs_processing(manifest):
    category = Category(number=30, title_en="C", title_ar="c", level="Beginner", source_file="f.md")
    lesson = make_lesson(number=1)
    category.lessons.append(lesson)
    manifest.upsert_record(_audio_only_success_record(lesson, manifest.compute_content_hash(lesson)))

    plan_audio = manifest.plan_run([category], engine="kokoro", formats="audio")
    plan_video = manifest.plan_run([category], engine="kokoro", formats="video")

    assert plan_audio[0].needs_processing is False
    assert plan_video[0].needs_processing is True
    assert plan_video[0].reason == "video_missing"
