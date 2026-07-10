"""Tests for optional intro/outro music mixing (INSTRUCTIONS.md 4.5).

Uses ffmpeg lavfi-generated tones as synthetic fixtures standing in for
operator-supplied music beds - never real creative assets, just enough
signal to prove the mixing/ducking/concatenation logic works.
"""

from __future__ import annotations

import subprocess
import wave

import pytest

from dorosak_factory.audio.music import append_audio, mix_intro_music
from dorosak_factory.audio.wav_utils import read_wav_duration_seconds, write_silence_wav


def make_tone(path, duration_seconds, sample_rate=24000):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_seconds}",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_mix_intro_music_matches_speech_duration(tmp_path):
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    write_silence_wav(speech, duration_seconds=4.0)
    make_tone(music, duration_seconds=10.0)  # longer than speech, must be trimmed

    output = tmp_path / "mixed.wav"
    mix_intro_music(speech, music, output, fade_in_ms=500, fade_out_ms=500, duck_db=-18.0)

    assert output.exists()
    assert read_wav_duration_seconds(output) == pytest.approx(4.0, abs=0.05)


def test_mix_intro_music_output_is_24khz_mono(tmp_path):
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    write_silence_wav(speech, duration_seconds=2.0)
    make_tone(music, duration_seconds=2.0, sample_rate=44100)  # different rate, must be resampled

    output = tmp_path / "mixed.wav"
    mix_intro_music(speech, music, output, fade_in_ms=200, fade_out_ms=200, duck_db=-18.0)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1


def test_mix_intro_music_missing_file_raises_missing_asset_error(tmp_path):
    from dorosak_factory.exceptions import MissingAssetError

    speech = tmp_path / "speech.wav"
    write_silence_wav(speech, duration_seconds=2.0)
    missing_music = tmp_path / "does_not_exist.mp3"

    with pytest.raises(MissingAssetError, match="does_not_exist.mp3"):
        mix_intro_music(speech, missing_music, tmp_path / "out.wav", 500, 500, -18.0)


def test_append_audio_adds_tail_duration(tmp_path):
    main = tmp_path / "main.wav"
    tail = tmp_path / "tail.wav"
    write_silence_wav(main, duration_seconds=3.0)
    make_tone(tail, duration_seconds=1.5, sample_rate=44100)  # different rate, must be standardized

    output = tmp_path / "combined.wav"
    append_audio(main, tail, output)

    assert read_wav_duration_seconds(output) == pytest.approx(4.5, abs=0.05)


def test_append_audio_missing_tail_raises_missing_asset_error(tmp_path):
    from dorosak_factory.exceptions import MissingAssetError

    main = tmp_path / "main.wav"
    write_silence_wav(main, duration_seconds=2.0)
    missing_tail = tmp_path / "no_outro.mp3"

    with pytest.raises(MissingAssetError, match="no_outro.mp3"):
        append_audio(main, missing_tail, tmp_path / "out.wav")
