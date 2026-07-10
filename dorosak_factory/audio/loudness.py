"""Two-pass ffmpeg loudnorm: measure integrated loudness, then normalize to target.

Two passes are required for accuracy: pass one measures the input's actual
loudness/true-peak/range, pass two feeds those measured values back in with
`linear=true` so the correction is a single accurate gain change rather than
loudnorm's single-pass dynamic (and less accurate) estimate.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.exceptions import FFmpegError

_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\}")

# ffmpeg's loudnorm rejects measured_I values outside [-99, 0]; true (or
# near-true) digital silence measures as -inf, which is not a meaningful
# loudness to "correct" - there is no signal to amplify.
_SILENCE_FLOOR_LUFS = -70.0


@dataclass(frozen=True)
class LoudnessMeasurement:
    """Parsed output of an ffmpeg `loudnorm` measurement pass."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float


def measure_loudness(
    wav_path: Path, target_lufs: float = -16.0, target_tp: float = -1.5
) -> LoudnessMeasurement:
    """Runs an ffmpeg loudnorm analysis-only pass and parses the reported stats."""
    result = _run_ffmpeg(
        [
            "-i",
            str(wav_path),
            "-af",
            f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    data = _extract_loudnorm_json(result.stderr)
    return LoudnessMeasurement(
        input_i=float(data["input_i"]),
        input_tp=float(data["input_tp"]),
        input_lra=float(data["input_lra"]),
        input_thresh=float(data["input_thresh"]),
        target_offset=float(data["target_offset"]),
    )


def normalize_loudness(
    input_path: Path,
    output_path: Path,
    target_lufs: float = -16.0,
    target_tp: float = -1.5,
    target_lra: float = 11.0,
) -> LoudnessMeasurement:
    """Normalizes `input_path` to the target loudness/true-peak, writing a 24kHz mono WAV.

    Returns the pre-normalization measurement (what the input actually was),
    so callers/logs can record the correction that was applied.
    """
    measurement = measure_loudness(input_path, target_lufs, target_tp)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not math.isfinite(measurement.input_i) or measurement.input_i <= _SILENCE_FLOOR_LUFS:
        # Silence (or near-silence): no signal to correct - passthrough at
        # the pipeline's standard format instead of feeding ffmpeg an
        # out-of-range measured_I.
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(input_path),
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
        )
        return measurement

    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={measurement.input_i}:measured_TP={measurement.input_tp}:"
        f"measured_LRA={measurement.input_lra}:measured_thresh={measurement.input_thresh}:"
        f"offset={measurement.target_offset}:linear=true:print_format=summary"
    )
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-af",
            loudnorm_filter,
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return measurement


def _extract_loudnorm_json(stderr: str) -> dict:
    matches = _JSON_BLOCK_RE.findall(stderr)
    if not matches:
        raise FFmpegError(f"Could not find loudnorm JSON output in ffmpeg stderr:\n{stderr}")
    return json.loads(matches[-1])


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}")
    return result
