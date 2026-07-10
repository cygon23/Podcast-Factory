"""MP3 export with ID3 tags and optional cover art, via ffmpeg (libmp3lame)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.exceptions import FFmpegError, MissingAssetError
from dorosak_factory.parser.models import Category, Lesson

DEFAULT_ARTIST = "Dorosak English Podcast"


@dataclass(frozen=True)
class ID3Tags:
    """ID3 tags applied to an exported episode MP3."""

    title: str
    artist: str
    album: str
    track_number: int
    cover_art_path: Path | None = None


def build_id3_tags(category: Category, lesson: Lesson, cover_art_path: Path | None = None) -> ID3Tags:
    """Builds ID3Tags per INSTRUCTIONS.md 4.5: title "Cat {N} · Lesson {M} — {title}"."""
    return ID3Tags(
        title=f"Cat {category.number} · Lesson {lesson.number} — {lesson.title_en}",
        artist=DEFAULT_ARTIST,
        album=category.title_en,
        track_number=lesson.number,
        cover_art_path=cover_art_path,
    )


def export_mp3(wav_path: Path, mp3_path: Path, bitrate_kbps: int, tags: ID3Tags) -> None:
    """Encodes `wav_path` to MP3 at `mp3_path` with the given bitrate and ID3 tags.

    Raises MissingAssetError (not a silent skip) if cover art was configured
    but the file doesn't exist - the operator asked for it, so its absence
    is a configuration error, not an optional feature to drop quietly.
    """
    if tags.cover_art_path is not None and not tags.cover_art_path.exists():
        raise MissingAssetError(
            f"Cover art not found: {tags.cover_art_path} — see docs/ASSETS.md for cover art requirements"
        )

    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-i", str(wav_path)]

    if tags.cover_art_path is not None:
        args += [
            "-i",
            str(tags.cover_art_path),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:v",
            "mjpeg",
            "-disposition:v",
            "attached_pic",
        ]

    args += [
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        "-id3v2_version",
        "3",
        "-metadata",
        f"title={tags.title}",
        "-metadata",
        f"artist={tags.artist}",
        "-metadata",
        f"album={tags.album}",
        "-metadata",
        f"track={tags.track_number}",
        str(mp3_path),
    ]
    _run_ffmpeg(args)


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result
