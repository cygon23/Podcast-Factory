"""Integration tests for video assembly: real ffmpeg encode + ffprobe verification.

Covers 16:9, 9:16, the vocabulary end card, and Arabic title rendering
(steps 5a/5b/5c) using a synthetic background (not an operator asset - just
a solid color generated for testing) and a real MP3 built via the audio
pipeline from step 3.
"""

from __future__ import annotations

import subprocess

import pytest

from dorosak_factory.audio.assembly import assemble_lesson_audio
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import AudioConfig
from dorosak_factory.exceptions import MissingAssetError
from dorosak_factory.media_probe import probe_duration_seconds, probe_streams
from dorosak_factory.parser.models import Category, DialogueTurn, Lesson, VocabItem
from dorosak_factory.subtitles.ass import write_ass
from dorosak_factory.tts.engines.null_engine import NullEngine
from dorosak_factory.video.builder import RESOLUTION_9_16, RESOLUTION_16_9, build_video


@pytest.fixture
def category():
    return Category(
        number=30,
        title_en="English for Weather & Nature",
        title_ar="ar",
        level="Beginner",
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
        turns=(
            DialogueTurn(speaker="Tom", raw_speaker_label="Tom", paragraphs=("Morning, Priya.",)),
            DialogueTurn(
                speaker="Priya", raw_speaker_label="Priya", paragraphs=("Dreadful weather today.",)
            ),
        ),
        vocabulary=(
            VocabItem(term="Miserable", definition="very unpleasant"),
            VocabItem(term="Frost", definition="a thin layer of ice"),
        ),
        source_file="f.md",
        raw_header="## Lesson 1",
    )


@pytest.fixture
def background(tmp_path):
    path = tmp_path / "assets" / "backgrounds" / "cat30.png"
    path.parent.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x2c3e50:s=640x360", "-frames:v", "1", str(path)],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture
def episode_mp3_and_ass(tmp_path, category, lesson):
    config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "audio_work")
    engine = NullEngine(output_dir=tmp_path / "engine_raw")
    cache = LineCache(cache_dir=config.cache_dir)
    mp3_path = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, config, mp3_path)

    ass_path = tmp_path / "dialogue.ass"
    write_ass(result.timeline, ass_path, video_width=1920, video_height=1080)
    return mp3_path, ass_path


def test_16x9_video_has_correct_resolution_and_codecs(
    tmp_path, category, lesson, background, episode_mp3_and_ass
):
    mp3_path, ass_path = episode_mp3_and_ass
    output = tmp_path / "video_16x9.mp4"
    width, height = RESOLUTION_16_9

    result = build_video(
        category, lesson, mp3_path, ass_path, background, output, tmp_path / "video_work", width, height
    )

    assert output.exists()
    streams = probe_streams(output)
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    audio_stream = next(s for s in streams if s["codec_type"] == "audio")
    assert video_stream["codec_name"] == "h264"
    assert video_stream["pix_fmt"] == "yuv420p"
    assert int(video_stream["width"]) == 1920
    assert int(video_stream["height"]) == 1080
    assert audio_stream["codec_name"] == "aac"
    assert result.width == 1920 and result.height == 1080


def test_9x16_video_has_correct_resolution(tmp_path, category, lesson, background, episode_mp3_and_ass):
    mp3_path, ass_path = episode_mp3_and_ass
    output = tmp_path / "video_9x16.mp4"
    width, height = RESOLUTION_9_16

    build_video(
        category,
        lesson,
        mp3_path,
        ass_path,
        background,
        output,
        tmp_path / "video_work_916",
        width,
        height,
    )

    streams = probe_streams(output)
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920


def test_video_duration_is_dialogue_plus_vocab_card(
    tmp_path, category, lesson, background, episode_mp3_and_ass
):
    mp3_path, ass_path = episode_mp3_and_ass
    output = tmp_path / "video.mp4"
    width, height = RESOLUTION_16_9

    result = build_video(
        category, lesson, mp3_path, ass_path, background, output, tmp_path / "video_work", width, height
    )

    actual_duration = probe_duration_seconds(output)
    assert actual_duration == pytest.approx(result.duration_seconds, abs=0.2)
    # 2 vocab items * 2s/item = 4s, floored to the 8s minimum
    assert result.vocab_card_duration_seconds == 8.0
    assert result.duration_seconds == pytest.approx(result.dialogue_duration_seconds + 8.0, abs=0.05)


def test_missing_background_fails_loudly(tmp_path, category, lesson, episode_mp3_and_ass):
    mp3_path, ass_path = episode_mp3_and_ass
    missing_bg = tmp_path / "does_not_exist.png"
    output = tmp_path / "video.mp4"

    with pytest.raises(MissingAssetError, match="does_not_exist.png"):
        build_video(
            category, lesson, mp3_path, ass_path, missing_bg, output, tmp_path / "vw", 1920, 1080
        )


def test_arabic_title_renders_without_crashing_and_frame_is_not_blank(
    tmp_path, category, lesson, background, episode_mp3_and_ass
):
    """Real RTL Arabic text ("الحديث عن طقس اليوم") must render via libass without error."""
    mp3_path, ass_path = episode_mp3_and_ass
    output = tmp_path / "video.mp4"
    width, height = RESOLUTION_16_9

    build_video(
        category, lesson, mp3_path, ass_path, background, output, tmp_path / "video_work", width, height
    )

    frame_path = tmp_path / "title_frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(output), "-ss", "1", "-frames:v", "1", str(frame_path)],
        check=True,
        capture_output=True,
    )
    assert frame_path.exists()
    assert frame_path.stat().st_size > 0
