"""Tests for per-episode validation (INSTRUCTIONS.md section 5), using real files."""

from __future__ import annotations

import json
import subprocess


from dorosak_factory.audio.assembly import AssemblyResult, LineTiming
from dorosak_factory.audio.loudness import LoudnessMeasurement, normalize_loudness
from dorosak_factory.audio.mp3_export import ID3Tags, export_mp3
from dorosak_factory.audio.wav_utils import write_silence_wav
from dorosak_factory.subtitles.srt import write_srt
from dorosak_factory.validate.episode import validate_episode
from dorosak_factory.video.builder import VideoBuildResult


def make_tone_wav(path, duration_seconds=35.0, volume_db=-6):
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


def make_valid_mp3(tmp_path, duration_seconds=35.0):
    """Builds a real MP3, normalized to -16 LUFS, so the loudness check has a fair target."""
    tone = tmp_path / "tone.wav"
    make_tone_wav(tone, duration_seconds=duration_seconds)
    normalized = tmp_path / "normalized.wav"
    normalize_loudness(tone, normalized, target_lufs=-16.0, target_tp=-1.5)
    mp3_path = tmp_path / "episode.mp3"
    export_mp3(
        normalized,
        mp3_path,
        bitrate_kbps=128,
        tags=ID3Tags(title="t", artist="a", album="al", track_number=1),
    )
    return mp3_path


def make_assembly_result(mp3_duration, mp3_path):
    timeline = (LineTiming("Host", "Welcome.", 0.0, mp3_duration),)
    return AssemblyResult(
        mp3_path=mp3_path,
        duration_seconds=mp3_duration,
        timeline=timeline,
        characters_synthesized=100,
        pre_normalization_loudness=LoudnessMeasurement(-20.0, -10.0, 5.0, -30.0, 4.0),
        voice_roles={"Host": "host"},
    )


def make_valid_metadata(path):
    path.write_text(
        json.dumps(
            {
                "category": 30,
                "lesson": 1,
                "title_en": "T",
                "title_ar": "ت",
                "engine": "null",
                "voice_roles": {"Tom": "female_1"},
                "duration_seconds": 35.0,
            }
        ),
        encoding="utf-8",
    )


def test_golden_path_episode_passes_all_checks(tmp_path):
    mp3_path = make_valid_mp3(tmp_path)
    from dorosak_factory.media_probe import probe_duration_seconds

    actual_duration = probe_duration_seconds(mp3_path)
    audio_result = make_assembly_result(actual_duration, mp3_path)

    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)

    metadata_path = tmp_path / "metadata.json"
    make_valid_metadata(metadata_path)

    result = validate_episode(audio_result, mp3_path, srt_path, metadata_path, min_duration_seconds=30.0)

    assert result.passed, result.failure_summary


def test_missing_mp3_fails(tmp_path):
    audio_result = make_assembly_result(35.0, tmp_path / "missing.mp3")
    result = validate_episode(
        audio_result, tmp_path / "missing.mp3", tmp_path / "x.srt", tmp_path / "x.json"
    )
    assert not result.passed
    assert any(c.name == "mp3_exists" for c in result.checks if not c.passed)


def test_too_short_mp3_fails(tmp_path):
    mp3_path = make_valid_mp3(tmp_path, duration_seconds=5.0)  # below default 30s minimum
    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)
    metadata_path = tmp_path / "metadata.json"
    make_valid_metadata(metadata_path)

    result = validate_episode(audio_result, mp3_path, srt_path, metadata_path, min_duration_seconds=30.0)

    assert not result.passed
    assert any(c.name == "mp3_duration" and not c.passed for c in result.checks)


def test_missing_srt_fails(tmp_path):
    mp3_path = make_valid_mp3(tmp_path)
    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    metadata_path = tmp_path / "metadata.json"
    make_valid_metadata(metadata_path)

    result = validate_episode(
        audio_result, mp3_path, tmp_path / "missing.srt", metadata_path, min_duration_seconds=30.0
    )

    assert not result.passed
    assert any(c.name == "srt_exists" and not c.passed for c in result.checks)


def test_missing_metadata_json_fails(tmp_path):
    mp3_path = make_valid_mp3(tmp_path)
    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)

    result = validate_episode(
        audio_result, mp3_path, srt_path, tmp_path / "missing.json", min_duration_seconds=30.0
    )

    assert not result.passed
    assert any(c.name == "metadata_json_exists" and not c.passed for c in result.checks)


def test_incomplete_metadata_json_fails(tmp_path):
    mp3_path = make_valid_mp3(tmp_path)
    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"category": 30}), encoding="utf-8")

    result = validate_episode(audio_result, mp3_path, srt_path, metadata_path, min_duration_seconds=30.0)

    assert not result.passed
    assert any(c.name == "metadata_json_complete" and not c.passed for c in result.checks)


def test_silent_audio_fails_loudness_check(tmp_path):
    silent_wav = tmp_path / "silent.wav"
    write_silence_wav(silent_wav, duration_seconds=35.0)
    mp3_path = tmp_path / "silent.mp3"
    export_mp3(
        silent_wav,
        mp3_path,
        bitrate_kbps=128,
        tags=ID3Tags(title="t", artist="a", album="al", track_number=1),
    )

    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)
    metadata_path = tmp_path / "metadata.json"
    make_valid_metadata(metadata_path)

    result = validate_episode(audio_result, mp3_path, srt_path, metadata_path, min_duration_seconds=30.0)

    assert not result.passed
    assert any(c.name == "loudness" and not c.passed for c in result.checks)


def test_video_wrong_resolution_fails(tmp_path):
    mp3_path = make_valid_mp3(tmp_path)
    from dorosak_factory.media_probe import probe_duration_seconds

    audio_result = make_assembly_result(probe_duration_seconds(mp3_path), mp3_path)
    srt_path = tmp_path / "episode.srt"
    write_srt(audio_result.timeline, srt_path)
    metadata_path = tmp_path / "metadata.json"
    make_valid_metadata(metadata_path)

    fake_mp4 = tmp_path / "video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(fake_mp4),
        ],
        check=True,
        capture_output=True,
    )
    video_result = VideoBuildResult(
        mp4_path=fake_mp4,
        width=1920,
        height=1080,
        duration_seconds=1.0,
        dialogue_duration_seconds=1.0,
        vocab_card_duration_seconds=0.0,
    )

    result = validate_episode(
        audio_result,
        mp3_path,
        srt_path,
        metadata_path,
        video_results={"16:9": video_result},
        min_duration_seconds=30.0,
    )

    assert not result.passed
    assert any(c.name == "video_16:9_resolution" and not c.passed for c in result.checks)
