"""Tests for the TTS/video/manifest/pipeline config sections (step 6+)."""

from __future__ import annotations

import os

from dorosak_factory.config import load_config


def test_tts_defaults(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.tts.engine is None
    assert config.tts.model == "default"
    assert config.tts.speed == 1.0
    assert config.tts.voice_map == {}
    assert config.tts.price_per_char == {}
    assert config.tts.character_role_overrides == {}


def test_tts_yaml_overrides(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        """
tts:
  engine: openai
  model: tts-1
  speed: 1.1
  voice_map:
    openai:
      host: alloy
      female_1: nova
  price_per_char:
    openai: 0.000015
  character_role_overrides:
    Rosa: female_2
""",
        encoding="utf-8",
    )
    config = load_config(yaml_path, base_dir=tmp_path)
    assert config.tts.engine == "openai"
    assert config.tts.model == "tts-1"
    assert config.tts.speed == 1.1
    assert config.tts.voice_map["openai"]["host"] == "alloy"
    assert config.tts.price_per_char["openai"] == 0.000015
    assert config.tts.character_role_overrides["Rosa"] == "female_2"


def test_video_defaults(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.video.resolutions == ("16:9", "9:16")
    assert config.video.font_name == "Noto Sans Arabic"
    assert config.video.title_card_seconds == 6.0
    assert config.video.vocab_seconds_per_item == 2.0
    assert config.video.vocab_min_seconds == 8.0
    assert config.video.backgrounds_dir == tmp_path / "assets" / "backgrounds"
    assert config.video.default_background == tmp_path / "assets" / "backgrounds" / "default.png"


def test_video_yaml_overrides(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("video:\n  resolutions: ['16:9']\n  title_card_seconds: 4\n", encoding="utf-8")
    config = load_config(yaml_path, base_dir=tmp_path)
    assert config.video.resolutions == ("16:9",)
    assert config.video.title_card_seconds == 4.0


def test_manifest_defaults(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.manifest.db_path == tmp_path / "output" / "manifest.sqlite3"


def test_pipeline_defaults(tmp_path):
    config = load_config(None, base_dir=tmp_path)
    assert config.pipeline.input_dir == tmp_path / "input"
    assert config.pipeline.output_dir == tmp_path / "output"
    assert config.pipeline.concurrency == min(4, os.cpu_count() or 1)


def test_pipeline_yaml_overrides(tmp_path):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("pipeline:\n  concurrency: 2\n", encoding="utf-8")
    config = load_config(yaml_path, base_dir=tmp_path)
    assert config.pipeline.concurrency == 2
