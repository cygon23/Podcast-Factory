"""Low-level WAV helpers: silence generation, duration reading, ffmpeg concatenation.

All audio in this pipeline is normalized to 24kHz mono 16-bit PCM WAV before
any assembly step, so these helpers assume that format throughout.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from dorosak_factory.exceptions import FFmpegError

SAMPLE_RATE_HZ = 24_000
SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM
CHANNELS = 1


def write_silence_wav(path: Path, duration_seconds: float) -> None:
    """Writes a silent 24kHz mono 16-bit PCM WAV of the given duration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(duration_seconds * SAMPLE_RATE_HZ)
    silence = b"\x00" * (frame_count * SAMPLE_WIDTH_BYTES)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(SAMPLE_RATE_HZ)
        wav_file.writeframes(silence)


def write_pcm16_wav(
    path: Path, pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE_HZ, channels: int = CHANNELS
) -> None:
    """Wraps raw 16-bit PCM bytes (e.g. from Polly/Azure) in a WAV header.

    Some cloud providers return headerless PCM rather than a WAV file;
    this makes their output a real WAV so it fits the rest of the pipeline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)


def convert_to_pipeline_wav(input_path: Path, output_path: Path) -> None:
    """Converts any ffmpeg-readable audio file to the pipeline's 24kHz mono 16-bit PCM WAV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ar",
            str(SAMPLE_RATE_HZ),
            "-ac",
            str(CHANNELS),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed converting {input_path} to pipeline WAV:\n{result.stderr}")


def read_wav_duration_seconds(path: Path) -> float:
    """Returns a WAV file's duration in seconds from its frame count and rate."""
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


def concat_wavs(input_paths: list[Path], output_path: Path) -> None:
    """Concatenates same-format WAV files into one, using ffmpeg's concat demuxer.

    Uses stream copy (no re-encoding) since all inputs share the pipeline's
    normalized 24kHz mono 16-bit PCM format.
    """
    if not input_paths:
        raise ValueError("concat_wavs requires at least one input file")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".concat_list.txt")
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in input_paths), encoding="utf-8")
    try:
        _run_ffmpeg(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(output_path),
            ]
        )
    finally:
        list_file.unlink(missing_ok=True)


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["ffmpeg", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result
