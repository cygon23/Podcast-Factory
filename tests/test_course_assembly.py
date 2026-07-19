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
