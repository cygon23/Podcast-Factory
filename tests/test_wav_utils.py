"""Tests for low-level WAV helpers: silence generation, duration reading, ffmpeg concat."""

from __future__ import annotations

import wave

import pytest

from dorosak_factory.audio.wav_utils import (
    concat_wavs,
    read_wav_duration_seconds,
    write_silence_wav,
)


def test_write_silence_wav_has_correct_format(tmp_path):
    path = tmp_path / "silence.wav"
    write_silence_wav(path, duration_seconds=0.5)
    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2


def test_write_silence_wav_duration_is_accurate(tmp_path):
    path = tmp_path / "silence.wav"
    write_silence_wav(path, duration_seconds=1.25)
    assert read_wav_duration_seconds(path) == pytest.approx(1.25, abs=0.01)


def test_write_silence_wav_samples_are_zero(tmp_path):
    path = tmp_path / "silence.wav"
    write_silence_wav(path, duration_seconds=0.1)
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    assert frames == b"\x00" * len(frames)


def test_read_wav_duration_seconds(tmp_path):
    path = tmp_path / "a.wav"
    write_silence_wav(path, duration_seconds=2.0)
    assert read_wav_duration_seconds(path) == pytest.approx(2.0, abs=0.01)


def test_concat_wavs_produces_sum_of_durations(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    write_silence_wav(a, duration_seconds=1.0)
    write_silence_wav(b, duration_seconds=2.0)
    output = tmp_path / "out.wav"

    concat_wavs([a, b], output)

    assert output.exists()
    assert read_wav_duration_seconds(output) == pytest.approx(3.0, abs=0.05)


def test_concat_wavs_preserves_format(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    write_silence_wav(a, duration_seconds=0.3)
    write_silence_wav(b, duration_seconds=0.3)
    output = tmp_path / "out.wav"

    concat_wavs([a, b], output)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1


def test_concat_wavs_requires_at_least_one_input(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        concat_wavs([], tmp_path / "out.wav")
