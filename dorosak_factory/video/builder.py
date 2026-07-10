"""Video assembly: pure FFmpeg, no MoviePy (INSTRUCTIONS.md 4.6).

Renders 16:9 or 9:16 (same function, parameterized by resolution) from the
already-exported episode MP3: a looped background image with three
sequentially-burned ASS layers (title card, dialogue captions, vocabulary
end card) and a matching audio track (episode audio + a held silent/music
tail for the vocab card).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.audio.wav_utils import concat_wavs, write_silence_wav
from dorosak_factory.exceptions import FFmpegError, MissingAssetError
from dorosak_factory.media_probe import probe_duration_seconds
from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.subtitles.title_card import DEFAULT_FONT_NAME, generate_title_card_ass
from dorosak_factory.subtitles.vocab_card import (
    DEFAULT_MIN_SECONDS,
    DEFAULT_SECONDS_PER_ITEM,
    compute_vocab_card_duration,
    generate_vocab_card_ass,
)

RESOLUTION_16_9 = (1920, 1080)
RESOLUTION_9_16 = (1080, 1920)


@dataclass(frozen=True)
class VideoBuildResult:
    """Metadata about one rendered video, for validation/reporting."""

    mp4_path: Path
    width: int
    height: int
    duration_seconds: float
    dialogue_duration_seconds: float
    vocab_card_duration_seconds: float


def build_video(
    category: Category,
    lesson: Lesson,
    episode_mp3_path: Path,
    dialogue_ass_path: Path,
    background_path: Path,
    output_mp4_path: Path,
    work_dir: Path,
    width: int,
    height: int,
    font_name: str = DEFAULT_FONT_NAME,
    title_card_seconds: float = 6.0,
    vocab_seconds_per_item: float = DEFAULT_SECONDS_PER_ITEM,
    vocab_min_seconds: float = DEFAULT_MIN_SECONDS,
) -> VideoBuildResult:
    """Builds one MP4 (either 16:9 or 9:16, per `width`/`height`) for `lesson`.

    `dialogue_ass_path` is the caption track already built from the audio
    assembly timeline (see `subtitles.ass.write_ass`) - this function only
    adds the title card and vocabulary end card around it.
    """
    if not background_path.exists():
        raise MissingAssetError(
            f"Background image not found: {background_path} — see docs/ASSETS.md "
            f"for the required assets/backgrounds/cat{category.number}.png (or default.png)"
        )
    if not episode_mp3_path.exists():
        raise MissingAssetError(f"Episode MP3 not found: {episode_mp3_path}")

    work_dir.mkdir(parents=True, exist_ok=True)

    dialogue_duration = probe_duration_seconds(episode_mp3_path)
    vocab_duration = compute_vocab_card_duration(
        lesson.vocabulary, vocab_seconds_per_item, vocab_min_seconds
    )
    total_duration = dialogue_duration + vocab_duration

    combined_audio_path = _build_combined_audio(episode_mp3_path, vocab_duration, work_dir)

    title_ass_path = work_dir / "title_card.ass"
    title_ass_path.write_text(
        generate_title_card_ass(
            category.number,
            lesson.number,
            lesson.title_en,
            lesson.title_ar,
            width,
            height,
            display_seconds=title_card_seconds,
            font_name=font_name,
        ),
        encoding="utf-8",
    )

    vocab_ass_path = work_dir / "vocab_card.ass"
    vocab_ass_path.write_text(
        generate_vocab_card_ass(
            lesson.vocabulary,
            start_seconds=dialogue_duration,
            duration_seconds=vocab_duration,
            video_width=width,
            video_height=height,
            font_name=font_name,
        ),
        encoding="utf-8",
    )

    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1[bg];"
        f"[bg]subtitles={_escape_filter_path(title_ass_path)}[v1];"
        f"[v1]subtitles={_escape_filter_path(dialogue_ass_path)}[v2];"
        f"[v2]subtitles={_escape_filter_path(vocab_ass_path)}[vout]"
    )
    _run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-i",
            str(background_path),
            "-i",
            str(combined_audio_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "1:a",
            "-t",
            f"{total_duration}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_mp4_path),
        ]
    )

    return VideoBuildResult(
        mp4_path=output_mp4_path,
        width=width,
        height=height,
        duration_seconds=total_duration,
        dialogue_duration_seconds=dialogue_duration,
        vocab_card_duration_seconds=vocab_duration,
    )


def _build_combined_audio(episode_mp3_path: Path, vocab_duration: float, work_dir: Path) -> Path:
    """Converts the episode MP3 to WAV and appends silence for the vocab card window.

    Note: section 4.6 asks for "gentle outro music underneath" the vocab
    card; this currently appends silence instead - a documented gap, not a
    silent shortcut (see docs/SELF_EVALUATION.md).
    """
    episode_wav = work_dir / "episode_audio.wav"
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(episode_mp3_path),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(episode_wav),
        ]
    )
    vocab_silence = work_dir / "vocab_card_silence.wav"
    write_silence_wav(vocab_silence, vocab_duration)

    combined = work_dir / "combined_audio.wav"
    concat_wavs([episode_wav, vocab_silence], combined)
    return combined


def _escape_filter_path(path: Path) -> str:
    """Escapes a filename for use as an ffmpeg filter argument (colons must be escaped)."""
    escaped = str(path.resolve()).replace("\\", "\\\\").replace(":", r"\:")
    return f"'{escaped}'"


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result
