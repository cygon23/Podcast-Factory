"""Integration test for StaticBackgroundRenderer: the VideoRenderer wrapper
around the existing build_video() ffmpeg pipeline. Real ffmpeg output,
verified the same way test_video_builder.py verifies build_video() directly -
this just proves the adapter layer doesn't change behavior.
"""

from __future__ import annotations

import subprocess

import pytest

from dorosak_factory.audio.assembly import assemble_lesson_audio
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import AudioConfig, Config, VideoConfig
from dorosak_factory.media_probe import probe_streams
from dorosak_factory.parser.models import Category, DialogueTurn, Lesson, VocabItem
from dorosak_factory.subtitles.ass import write_ass
from dorosak_factory.tts.engines.null_engine import NullEngine
from dorosak_factory.video.renderers.static_background_renderer import StaticBackgroundRenderer


@pytest.fixture
def category():
    return Category(
        number=30, title_en="English for Weather & Nature", title_ar="ar", level="Beginner",
        source_file="f.md",
    )


@pytest.fixture
def lesson():
    return Lesson(
        number=1,
        title_en="Talking About Today's Weather",
        title_ar="الحديث عن طقس اليوم",
        scenario="s",
        host_intro="Welcome to the test lesson.",
        turns=(DialogueTurn(speaker="Tom", raw_speaker_label="Tom", paragraphs=("Morning, Priya.",)),),
        vocabulary=(VocabItem(term="Frost", definition="a thin layer of ice"),),
        source_file="f.md",
        raw_header="## Lesson 1",
    )


@pytest.fixture
def background(tmp_path):
    path = tmp_path / "assets" / "backgrounds" / "default.png"
    path.parent.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x2c3e50:s=640x360", "-frames:v", "1", str(path)],
        check=True, capture_output=True,
    )
    return path


@pytest.fixture
def episode_mp3_and_ass(tmp_path, category, lesson):
    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "audio_work")
    engine = NullEngine(output_dir=tmp_path / "engine_raw")
    cache = LineCache(cache_dir=audio_config.cache_dir)
    mp3_path = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, audio_config, mp3_path)

    ass_path = tmp_path / "dialogue.ass"
    write_ass(result.timeline, ass_path, video_width=1920, video_height=1080)
    return mp3_path, ass_path


def test_static_background_renderer_is_always_available():
    assert StaticBackgroundRenderer.is_available(env={}) is True


def test_from_config_reads_video_config_fields(tmp_path, background):
    config = Config(video=VideoConfig(default_background=background))
    renderer = StaticBackgroundRenderer.from_config(config)
    assert renderer is not None


def test_render_produces_a_real_playable_video(tmp_path, category, lesson, background, episode_mp3_and_ass):
    mp3_path, ass_path = episode_mp3_and_ass
    config = Config(video=VideoConfig(default_background=background))
    renderer = StaticBackgroundRenderer.from_config(config)
    output = tmp_path / "video.mp4"

    result = renderer.render(
        category, lesson, mp3_path, ass_path, output, tmp_path / "video_work", 1920, 1080
    )

    assert output.exists()
    streams = probe_streams(output)
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    assert video_stream["codec_name"] == "h264"
    assert int(video_stream["width"]) == 1920
    assert result.width == 1920
    assert result.height == 1080
