"""Tests for course audio assembly: real ffmpeg, real NullEngine (no
network, no cost) - same testing philosophy as tests/test_video_builder.py
and tests/test_audio_assembly.py for the cat*/Markdown pipeline.
"""

from __future__ import annotations

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import AudioConfig, CourseConfig
from dorosak_factory.course.models import BilingualItem
from dorosak_factory.media_probe import probe_duration_seconds
from dorosak_factory.tts.engines.null_engine import NullEngine


def test_synthesize_bilingual_item_produces_one_mp3_with_a_silence_gap(tmp_path):
    from dorosak_factory.course.assembly import synthesize_bilingual_item

    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "work")
    course_config = CourseConfig(bilingual_gap_ms=1000)
    cache = LineCache(cache_dir=audio_config.cache_dir)
    english_engine = NullEngine(output_dir=tmp_path / "en_raw")
    arabic_engine = NullEngine(output_dir=tmp_path / "ar_raw")

    item = BilingualItem(item_no=1, english="Alphabet", arabic="الأبجدية")
    output_path = tmp_path / "item.mp3"

    synthesize_bilingual_item(
        item,
        english_engine=english_engine,
        arabic_engine=arabic_engine,
        cache=cache,
        audio_config=audio_config,
        course_config=course_config,
        output_mp3_path=output_path,
        work_dir=tmp_path / "item_work",
        narrator_voice_role="host",
    )

    assert output_path.exists()
    english_only_duration = probe_duration_seconds(
        english_engine.synthesize("Alphabet", voice_role="host").wav_path
    )
    arabic_only_duration = probe_duration_seconds(
        arabic_engine.synthesize("الأبجدية", voice_role="arabic_narrator").wav_path
    )
    combined_duration = probe_duration_seconds(output_path)
    # combined >= english + gap + arabic (loudnorm/mp3 encoding can shift
    # duration slightly, so this checks the gap was really inserted rather
    # than asserting an exact value).
    assert combined_duration >= english_only_duration + arabic_only_duration + 0.9


def test_assemble_dialogue_lesson_produces_one_multi_voice_mp3(tmp_path):
    from dorosak_factory.course.assembly import assemble_dialogue_lesson
    from dorosak_factory.course.models import Book, CourseLesson, DialogueLine, DialogueSection, Unit

    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "work")
    cache = LineCache(cache_dir=audio_config.cache_dir)
    teacher_engine = NullEngine(output_dir=tmp_path / "teacher_raw")
    student_engine = NullEngine(output_dir=tmp_path / "student_raw")

    section = DialogueSection(
        book=Book(book_id=1, name="Mastering English with Dorosak (Beginner)"),
        unit=Unit(unit_id=6, book_id=1, name="Unit 1"),
        lesson=CourseLesson(lesson_id=20, unit_id=6, book_id=1, name="Lesson 1: Alphabet Basics"),
        lines=(
            DialogueLine(item_no=1, speaker="Teacher", text="Welcome to today's class."),
            DialogueLine(item_no=2, speaker="Student", text="Hello, teacher."),
        ),
    )
    output_path = tmp_path / "dialogue.mp3"

    assemble_dialogue_lesson(
        section,
        teacher_engine=teacher_engine,
        student_engine=student_engine,
        cache=cache,
        audio_config=audio_config,
        output_mp3_path=output_path,
        work_dir=tmp_path / "dialogue_work",
        teacher_voice_role="host",
        student_voice_role="female_1",
    )

    assert output_path.exists()
    assert probe_duration_seconds(output_path) > 0.5
