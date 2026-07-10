"""Tests for the audio-relevant slice of config loading (pauses, loudness, mp3, music).

Defaults must match the values mandated in INSTRUCTIONS.md section 4.5:
700ms between turns, 1500ms after host intro, 400ms between paragraphs,
-16 LUFS integrated loudness, -1.5 dBTP true peak, 128kbps MP3.
"""

from __future__ import annotations


import pytest

from dorosak_factory.config import load_config


def test_defaults_when_no_file_given(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.audio.pauses.between_turns_ms == 700
    assert config.audio.pauses.after_host_intro_ms == 1500
    assert config.audio.pauses.between_paragraphs_ms == 400
    assert config.audio.loudness.target_lufs == -16.0
    assert config.audio.loudness.true_peak_dbtp == -1.5
    assert config.audio.mp3.bitrate_kbps == 128
    assert config.audio.mp3.artist == "Dorosak English Podcast"
    assert config.audio.music.intro_path is None
    assert config.audio.music.outro_path is None


def test_partial_yaml_overrides_only_specified_fields(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
audio:
  pauses:
    between_turns_ms: 900
  mp3:
    bitrate_kbps: 192
""",
        encoding="utf-8",
    )
    config = load_config(yaml_path, base_dir=tmp_path)
    assert config.audio.pauses.between_turns_ms == 900
    assert config.audio.pauses.after_host_intro_ms == 1500  # untouched default
    assert config.audio.mp3.bitrate_kbps == 192
    assert config.audio.mp3.artist == "Dorosak English Podcast"  # untouched default


def test_music_paths_resolved_relative_to_base_dir(tmp_path):
    (tmp_path / "assets" / "music").mkdir(parents=True)
    intro = tmp_path / "assets" / "music" / "intro.mp3"
    intro.write_bytes(b"fake")
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "audio:\n  music:\n    intro_path: assets/music/intro.mp3\n",
        encoding="utf-8",
    )
    config = load_config(yaml_path, base_dir=tmp_path)
    assert config.audio.music.intro_path == intro
    assert config.audio.music.intro_path.is_absolute()


def test_cache_and_work_dirs_default_under_base_dir(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.audio.cache_dir == tmp_path / "output" / "cache"
    assert config.audio.work_dir == tmp_path / "output" / "work"


def test_missing_config_file_raises_clear_error(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError, match="does_not_exist.yaml"):
        load_config(missing, base_dir=tmp_path)
