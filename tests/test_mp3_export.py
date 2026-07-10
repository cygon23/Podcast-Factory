"""Tests for MP3 export with ID3 tags and optional cover art, verified via ffprobe."""

from __future__ import annotations

import json
import subprocess

import pytest

from dorosak_factory.audio.mp3_export import ID3Tags, build_id3_tags, export_mp3
from dorosak_factory.audio.wav_utils import write_silence_wav
from dorosak_factory.exceptions import MissingAssetError
from dorosak_factory.parser.models import Category, Lesson


def ffprobe_format(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["format"]


def ffprobe_streams(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["streams"]


@pytest.fixture
def source_wav(tmp_path):
    path = tmp_path / "source.wav"
    write_silence_wav(path, duration_seconds=1.0)
    return path


def test_export_mp3_produces_playable_file_with_tags(tmp_path, source_wav):
    mp3_path = tmp_path / "episode.mp3"
    tags = ID3Tags(
        title="Cat 30 · Lesson 1 — Talking About Today's Weather",
        artist="Dorosak English Podcast",
        album="English for Weather & Nature Daily Life",
        track_number=1,
    )

    export_mp3(source_wav, mp3_path, bitrate_kbps=128, tags=tags)

    assert mp3_path.exists()
    fmt = ffprobe_format(mp3_path)
    assert fmt["format_name"] == "mp3"
    assert fmt["tags"]["title"] == tags.title
    assert fmt["tags"]["artist"] == tags.artist
    assert fmt["tags"]["album"] == tags.album
    assert fmt["tags"]["track"] == "1"


def test_export_mp3_with_cover_art_attaches_image(tmp_path, source_wav):
    cover = tmp_path / "cover.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=50x50", "-frames:v", "1", str(cover)],
        check=True,
        capture_output=True,
    )
    mp3_path = tmp_path / "episode.mp3"
    tags = ID3Tags(title="Title", artist="Artist", album="Album", track_number=1, cover_art_path=cover)

    export_mp3(source_wav, mp3_path, bitrate_kbps=128, tags=tags)

    streams = ffprobe_streams(mp3_path)
    video_streams = [s for s in streams if s["codec_type"] == "video"]
    assert len(video_streams) == 1
    assert video_streams[0]["disposition"]["attached_pic"] == 1


def test_export_mp3_missing_cover_art_fails_loudly(tmp_path, source_wav):
    missing_cover = tmp_path / "does_not_exist.jpg"
    tags = ID3Tags(
        title="Title", artist="Artist", album="Album", track_number=1, cover_art_path=missing_cover
    )

    with pytest.raises(MissingAssetError, match="does_not_exist.jpg"):
        export_mp3(source_wav, tmp_path / "out.mp3", bitrate_kbps=128, tags=tags)


def test_export_mp3_respects_bitrate(tmp_path, source_wav):
    mp3_path = tmp_path / "episode.mp3"
    tags = ID3Tags(title="T", artist="A", album="Al", track_number=1)

    export_mp3(source_wav, mp3_path, bitrate_kbps=64, tags=tags)

    fmt = ffprobe_format(mp3_path)
    # allow some encoder overhead/rounding around the nominal bitrate
    assert 55_000 < int(fmt["bit_rate"]) < 75_000


def test_build_id3_tags_formats_title_per_spec():
    category = Category(
        number=30,
        title_en="English for Weather & Nature Daily Life",
        title_ar="ar",
        level="Beginner & Intermediate",
        source_file="x.md",
    )
    lesson = Lesson(
        number=1,
        title_en="Talking About Today's Weather",
        title_ar="ar",
        scenario="s",
        host_intro="h",
        turns=(),
        vocabulary=(),
        source_file="x.md",
        raw_header="## Lesson 1",
    )

    tags = build_id3_tags(category, lesson)

    assert tags.title == "Cat 30 · Lesson 1 — Talking About Today's Weather"
    assert tags.album == "English for Weather & Nature Daily Life"
    assert tags.track_number == 1
    assert tags.artist == "Dorosak English Podcast"
    assert tags.cover_art_path is None
