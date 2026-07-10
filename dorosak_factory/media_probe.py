"""ffprobe-based inspection helpers shared by video assembly and validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dorosak_factory.exceptions import FFmpegError


def probe_duration_seconds(path: Path) -> float:
    """Returns a media file's duration in seconds via ffprobe."""
    result = _run_ffprobe(["-show_entries", "format=duration", "-print_format", "json", str(path)])
    return float(json.loads(result.stdout)["format"]["duration"])


def probe_streams(path: Path) -> list[dict]:
    """Returns ffprobe's stream list (codec, resolution, etc.) for `path`."""
    result = _run_ffprobe(["-show_streams", "-print_format", "json", str(path)])
    return json.loads(result.stdout)["streams"]


def _run_ffprobe(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(["ffprobe", "-v", "quiet", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(
            f"ffprobe failed (exit {result.returncode}): {' '.join(args)}\n{result.stderr}"
        )
    return result
