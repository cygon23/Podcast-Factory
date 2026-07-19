"""Synthesizes and assembles course audio: bilingual item clips
(vocabulary, examples, useful phrases), multi-voice dialogue episodes, and
single-narrator article readings.

Reuses the same low-level building blocks as the cat*/Markdown pipeline
(LineCache, wav_utils, loudness normalization, MP3 export) but with its
own top-level functions, since course/models.py's shapes
(DialogueSection/BilingualSection/...) don't match parser.models.Lesson.
"""

from __future__ import annotations

from pathlib import Path

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.audio.loudness import normalize_loudness
from dorosak_factory.audio.mp3_export import ID3Tags, export_mp3
from dorosak_factory.audio.wav_utils import concat_wavs, write_silence_wav
from dorosak_factory.config import AudioConfig, CourseConfig
from dorosak_factory.course.models import BilingualItem, DialogueSection
from dorosak_factory.tts.base import TTSEngine


def synthesize_bilingual_item(
    item: BilingualItem,
    english_engine: TTSEngine,
    arabic_engine: TTSEngine,
    cache: LineCache,
    audio_config: AudioConfig,
    course_config: CourseConfig,
    output_mp3_path: Path,
    work_dir: Path,
    narrator_voice_role: str,
) -> Path:
    """English clip + silence gap + Arabic clip, concatenated into one MP3.

    Matches the measured real-recording pattern (see design spec): two
    speech segments separated by course_config.bilingual_gap_ms of silence.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    english_result = cache.get_or_synthesize(
        english_engine,
        item.english,
        voice_role=narrator_voice_role,
        model="default",
        voice_id=narrator_voice_role,
    )
    arabic_result = cache.get_or_synthesize(
        arabic_engine,
        item.arabic,
        voice_role=course_config.arabic_voice_role,
        model="default",
        voice_id=course_config.arabic_voice_role,
    )

    gap_path = work_dir / f"gap_{item.item_no}.wav"
    write_silence_wav(gap_path, course_config.bilingual_gap_ms / 1000.0)

    combined_path = work_dir / f"combined_{item.item_no}.wav"
    concat_wavs([english_result.wav_path, gap_path, arabic_result.wav_path], combined_path)

    normalized_path = work_dir / f"normalized_{item.item_no}.wav"
    normalize_loudness(
        combined_path,
        normalized_path,
        target_lufs=audio_config.loudness.target_lufs,
        target_tp=audio_config.loudness.true_peak_dbtp,
    )

    tags = ID3Tags(
        title=item.english,
        artist=audio_config.mp3.artist,
        album="Dorosak Course Audio",
        track_number=item.item_no,
    )
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=audio_config.mp3.bitrate_kbps, tags=tags)
    return output_mp3_path


def assemble_dialogue_lesson(
    section: DialogueSection,
    teacher_engine: TTSEngine,
    student_engine: TTSEngine,
    cache: LineCache,
    audio_config: AudioConfig,
    output_mp3_path: Path,
    work_dir: Path,
    teacher_voice_role: str,
    student_voice_role: str,
    between_lines_ms: int = 500,
) -> Path:
    """One combined multi-voice MP3 for a Teacher/Student dialogue lesson."""
    work_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []

    for index, line in enumerate(section.lines):
        is_teacher = line.speaker == "Teacher"
        engine = teacher_engine if is_teacher else student_engine
        role = teacher_voice_role if is_teacher else student_voice_role
        result = cache.get_or_synthesize(
            engine, line.text, voice_role=role, model="default", voice_id=role
        )
        segments.append(result.wav_path)
        if index < len(section.lines) - 1:
            gap_path = work_dir / f"gap_{index}.wav"
            write_silence_wav(gap_path, between_lines_ms / 1000.0)
            segments.append(gap_path)

    raw_path = work_dir / "dialogue_raw.wav"
    concat_wavs(segments, raw_path)

    normalized_path = work_dir / "normalized.wav"
    normalize_loudness(
        raw_path,
        normalized_path,
        target_lufs=audio_config.loudness.target_lufs,
        target_tp=audio_config.loudness.true_peak_dbtp,
    )

    tags = ID3Tags(
        title=f"{section.lesson.name} - Dialogue",
        artist=audio_config.mp3.artist,
        album=section.book.name,
        track_number=section.lesson.lesson_id,
    )
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=audio_config.mp3.bitrate_kbps, tags=tags)
    return output_mp3_path
