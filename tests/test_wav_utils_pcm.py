"""Tests for the raw-PCM-to-WAV and format-conversion helpers used by cloud TTS adapters."""

from __future__ import annotations

import struct
import subprocess
import wave

import pytest

from dorosak_factory.audio.wav_utils import convert_to_pipeline_wav, write_pcm16_wav


def test_write_pcm16_wav_wraps_raw_bytes_correctly(tmp_path):
    samples = [100, -100, 200, -200]
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)
    path = tmp_path / "out.wav"

    write_pcm16_wav(path, pcm_bytes, sample_rate=24000, channels=1)

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        frames = wav_file.readframes(wav_file.getnframes())
    assert frames == pcm_bytes


def test_convert_to_pipeline_wav_resamples_to_24khz_mono(tmp_path):
    source = tmp_path / "source.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "converted.wav"

    convert_to_pipeline_wav(source, output)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1


def test_convert_to_pipeline_wav_raises_on_bad_input(tmp_path):
    from dorosak_factory.exceptions import FFmpegError

    bad_input = tmp_path / "not_audio.wav"
    bad_input.write_bytes(b"this is not audio data")

    with pytest.raises(FFmpegError):
        convert_to_pipeline_wav(bad_input, tmp_path / "out.wav")
