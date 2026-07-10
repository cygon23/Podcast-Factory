"""Tests for two-pass ffmpeg loudnorm: measure, then normalize to -16 LUFS / -1.5 dBTP.

Uses ffmpeg's `sine` test source (not any operator-supplied asset) purely as
a synthetic, non-silent fixture - true silence has no meaningful loudness to
correct, so a signal is needed to exercise the normalization math for real.
"""

from __future__ import annotations

import subprocess
import wave

import pytest

from dorosak_factory.audio.loudness import measure_loudness, normalize_loudness


def make_tone_wav(path, duration_seconds=3.0, volume_db=-6):
    """Generates a real 24kHz mono WAV tone at a known-ish level via ffmpeg lavfi."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_seconds}",
            "-af",
            f"volume={volume_db}dB",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def loud_tone(tmp_path):
    path = tmp_path / "tone.wav"
    make_tone_wav(path, volume_db=-6)  # loud, well above -16 LUFS target
    return path


@pytest.fixture
def quiet_tone(tmp_path):
    path = tmp_path / "quiet_tone.wav"
    make_tone_wav(path, volume_db=-35)  # quiet, well below -16 LUFS target
    return path


def test_measure_loudness_returns_plausible_values(loud_tone):
    measurement = measure_loudness(loud_tone)
    assert -60 < measurement.input_i < 0
    assert -60 < measurement.input_tp < 5


def test_normalize_loud_input_reaches_target_lufs(tmp_path, loud_tone):
    output = tmp_path / "normalized.wav"
    normalize_loudness(loud_tone, output, target_lufs=-16.0, target_tp=-1.5)

    result = measure_loudness(output)
    assert abs(result.input_i - (-16.0)) <= 1.5


def test_normalize_quiet_input_reaches_target_lufs(tmp_path, quiet_tone):
    output = tmp_path / "normalized.wav"
    normalize_loudness(quiet_tone, output, target_lufs=-16.0, target_tp=-1.5)

    result = measure_loudness(output)
    assert abs(result.input_i - (-16.0)) <= 1.5


def test_normalize_respects_true_peak_ceiling(tmp_path, loud_tone):
    output = tmp_path / "normalized.wav"
    normalize_loudness(loud_tone, output, target_lufs=-16.0, target_tp=-1.5)

    result = measure_loudness(output)
    assert result.input_tp <= -1.5 + 0.5  # small tolerance for measurement rounding


def test_normalize_output_is_24khz_mono(tmp_path, loud_tone):
    output = tmp_path / "normalized.wav"
    normalize_loudness(loud_tone, output, target_lufs=-16.0, target_tp=-1.5)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
