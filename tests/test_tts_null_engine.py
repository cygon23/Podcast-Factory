"""Tests for the NullEngine: a silent, zero-dependency TTS engine used for testing."""

from __future__ import annotations

import wave

import pytest

from dorosak_factory.tts.engines.null_engine import NullEngine


@pytest.fixture
def engine(tmp_path):
    return NullEngine(output_dir=tmp_path)


def test_is_always_available(engine):
    assert NullEngine.is_available(env={}) is True


def test_synthesize_writes_a_real_wav_file(engine):
    result = engine.synthesize("Hello there, how are you today?", voice_role="host", speed=1.0)
    assert result.wav_path.exists()
    with wave.open(str(result.wav_path), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2  # 16-bit PCM


def test_synthesize_duration_matches_wav_length(engine):
    result = engine.synthesize("Hello there, how are you today?", voice_role="host", speed=1.0)
    with wave.open(str(result.wav_path), "rb") as wav_file:
        frames = wav_file.getnframes()
        actual_duration = frames / wav_file.getframerate()
    assert actual_duration == pytest.approx(result.duration_seconds, abs=0.01)


def test_synthesize_reports_character_count(engine):
    text = "Hello there"
    result = engine.synthesize(text, voice_role="host", speed=1.0)
    assert result.characters == len(text)


def test_longer_text_produces_longer_duration(engine):
    short = engine.synthesize("Hi.", voice_role="host", speed=1.0)
    long = engine.synthesize(
        "This is a considerably longer sentence with many more words in it.",
        voice_role="host",
        speed=1.0,
    )
    assert long.duration_seconds > short.duration_seconds


def test_higher_speed_produces_shorter_duration(engine):
    normal = engine.synthesize(
        "A reasonably long sentence for timing purposes.", voice_role="host", speed=1.0
    )
    fast = engine.synthesize(
        "A reasonably long sentence for timing purposes.", voice_role="host", speed=2.0
    )
    assert fast.duration_seconds < normal.duration_seconds


def test_minimum_duration_floor(engine):
    result = engine.synthesize("Hi", voice_role="host", speed=1.0)
    assert result.duration_seconds >= 0.3


def test_capabilities(engine):
    caps = engine.capabilities
    assert caps.supports_speed is True
    assert caps.supports_ssml is False


def test_result_records_engine_and_voice_role(engine):
    result = engine.synthesize("Some text.", voice_role="female_1", speed=1.0)
    assert result.engine == "null"
    assert result.voice_role == "female_1"
