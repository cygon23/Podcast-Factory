"""Optional intro/outro music mixing (INSTRUCTIONS.md 4.5).

Only invoked when an operator has configured a music path; a missing
configured file fails loudly (MissingAssetError) rather than silently
producing music-less audio, per the project's anti-fabrication rule.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from dorosak_factory.audio.wav_utils import read_wav_duration_seconds
from dorosak_factory.exceptions import FFmpegError, MissingAssetError


def mix_intro_music(
    speech_path: Path,
    music_path: Path,
    output_path: Path,
    fade_in_ms: int,
    fade_out_ms: int,
    duck_db: float,
) -> None:
    """Mixes `music_path` under `speech_path`: fades in, holds at `duck_db`, fades out.

    The music track is trimmed to the speech's exact duration - it only
    plays under the host intro, never beyond it.
    """
    _require_exists(music_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = read_wav_duration_seconds(speech_path)
    fade_in_s = fade_in_ms / 1000.0
    fade_out_s = fade_out_ms / 1000.0
    fade_out_start = max(duration - fade_out_s, 0.0)

    music_filter = (
        f"[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS,"
        f"volume={duck_db}dB,"
        f"afade=t=in:d={fade_in_s},"
        f"afade=t=out:st={fade_out_start}:d={fade_out_s}[music]"
    )
    mix_filter = "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0,volume=2[out]"

    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(speech_path),
            "-i",
            str(music_path),
            "-filter_complex",
            f"{music_filter};{mix_filter}",
            "-map",
            "[out]",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def append_audio(main_path: Path, tail_path: Path, output_path: Path) -> None:
    """Appends `tail_path` (e.g. an outro sting) after `main_path`, standardizing format first."""
    _require_exists(tail_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    standardized_tail = output_path.with_suffix(".tail_standardized.wav")
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(tail_path),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(standardized_tail),
        ]
    )
    try:
        from dorosak_factory.audio.wav_utils import concat_wavs

        concat_wavs([main_path, standardized_tail], output_path)
    finally:
        standardized_tail.unlink(missing_ok=True)


def _require_exists(path: Path) -> None:
    if not path.exists():
        raise MissingAssetError(f"Missing music asset: {path} — see docs/ASSETS.md")


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result
