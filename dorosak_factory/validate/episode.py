"""Per-episode validation checks (INSTRUCTIONS.md section 5).

Runs after each episode is produced. An episode failing any check is marked
FAILED in the manifest with the reason - never silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.audio.assembly import AssemblyResult
from dorosak_factory.audio.loudness import measure_loudness
from dorosak_factory.exceptions import FFmpegError
from dorosak_factory.media_probe import probe_duration_seconds, probe_streams
from dorosak_factory.video.builder import VideoBuildResult


@dataclass(frozen=True)
class CheckResult:
    """One named pass/fail check with a human-readable detail."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EpisodeValidationResult:
    """Aggregate result of all checks for one episode."""

    passed: bool
    checks: tuple[CheckResult, ...]

    @property
    def failure_summary(self) -> str:
        failed = [c for c in self.checks if not c.passed]
        return "; ".join(f"{c.name}: {c.detail}" for c in failed)


def validate_episode(
    audio_result: AssemblyResult,
    mp3_path: Path,
    srt_path: Path,
    metadata_json_path: Path,
    video_results: dict[str, VideoBuildResult] | None = None,
    min_duration_seconds: float = 30.0,
    loudness_target: float = -16.0,
    loudness_tolerance: float = 1.5,
) -> EpisodeValidationResult:
    """Runs every applicable check for one episode and returns the aggregate result."""
    checks: list[CheckResult] = []
    video_results = video_results or {}

    checks.append(_check_mp3(mp3_path, audio_result, min_duration_seconds))
    checks.append(_check_srt(srt_path, audio_result, mp3_path))
    checks.append(_check_metadata_json(metadata_json_path))
    checks.append(_check_loudness(mp3_path, loudness_target, loudness_tolerance))

    for label, video_result in video_results.items():
        checks.append(_check_video(label, video_result, audio_result))

    return EpisodeValidationResult(passed=all(c.passed for c in checks), checks=tuple(checks))


def _check_mp3(mp3_path: Path, audio_result: AssemblyResult, min_duration_seconds: float) -> CheckResult:
    if not mp3_path.exists():
        return CheckResult("mp3_exists", False, f"MP3 not found: {mp3_path}")
    try:
        duration = probe_duration_seconds(mp3_path)
    except FFmpegError as exc:
        return CheckResult("mp3_exists", False, f"ffprobe failed: {exc}")

    if duration <= min_duration_seconds:
        return CheckResult(
            "mp3_duration", False, f"duration {duration:.1f}s <= minimum {min_duration_seconds}s"
        )
    if abs(duration - audio_result.duration_seconds) > 3.0:
        return CheckResult(
            "mp3_duration",
            False,
            f"MP3 duration {duration:.1f}s differs from assembled {audio_result.duration_seconds:.1f}s by >3s",
        )
    return CheckResult("mp3_duration", True, f"{duration:.1f}s")


def _check_srt(srt_path: Path, audio_result: AssemblyResult, mp3_path: Path) -> CheckResult:
    if not srt_path.exists():
        return CheckResult("srt_exists", False, f"SRT not found: {srt_path}")

    timeline = audio_result.timeline
    for earlier, later in zip(timeline, timeline[1:]):
        if later.start_seconds < earlier.end_seconds:
            return CheckResult("srt_monotonic", False, "timeline is not monotonic")

    srt_text = srt_path.read_text(encoding="utf-8")
    cue_count = srt_text.count("-->")
    if cue_count != len(timeline):
        return CheckResult(
            "srt_completeness", False, f"{cue_count} SRT cues but {len(timeline)} timeline entries"
        )

    try:
        mp3_duration = probe_duration_seconds(mp3_path)
    except FFmpegError as exc:
        return CheckResult("srt_within_audio_duration", False, f"ffprobe failed: {exc}")

    last_end = timeline[-1].end_seconds if timeline else 0.0
    if last_end > mp3_duration + 0.5:
        return CheckResult(
            "srt_within_audio_duration",
            False,
            f"last subtitle ends at {last_end:.1f}s, audio is only {mp3_duration:.1f}s",
        )
    return CheckResult("srt_valid", True, f"{cue_count} cues, monotonic, within audio duration")


def _check_metadata_json(metadata_json_path: Path) -> CheckResult:
    import json

    if not metadata_json_path.exists():
        return CheckResult("metadata_json_exists", False, f"not found: {metadata_json_path}")
    try:
        data = json.loads(metadata_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("metadata_json_valid", False, f"invalid JSON: {exc}")

    required_keys = {
        "category",
        "lesson",
        "title_en",
        "title_ar",
        "engine",
        "voice_roles",
        "duration_seconds",
    }
    missing = required_keys - data.keys()
    if missing:
        return CheckResult("metadata_json_complete", False, f"missing keys: {sorted(missing)}")
    return CheckResult("metadata_json", True, "present and complete")


def _check_loudness(mp3_path: Path, target: float, tolerance: float) -> CheckResult:
    try:
        measurement = measure_loudness(mp3_path, target_lufs=target)
    except FFmpegError as exc:
        return CheckResult("loudness", False, f"measurement failed: {exc}")

    import math

    if not math.isfinite(measurement.input_i):
        return CheckResult("loudness", False, "measured loudness is -inf (silent/near-silent audio)")
    if abs(measurement.input_i - target) > tolerance:
        return CheckResult(
            "loudness",
            False,
            f"{measurement.input_i:.1f} LUFS outside {target} ±{tolerance}",
        )
    return CheckResult("loudness", True, f"{measurement.input_i:.1f} LUFS")


def _check_video(
    label: str, video_result: VideoBuildResult, audio_result: AssemblyResult
) -> CheckResult:
    if not video_result.mp4_path.exists():
        return CheckResult(f"video_{label}_exists", False, f"not found: {video_result.mp4_path}")

    try:
        streams = probe_streams(video_result.mp4_path)
    except FFmpegError as exc:
        return CheckResult(f"video_{label}_playable", False, f"ffprobe failed: {exc}")

    video_streams = [s for s in streams if s["codec_type"] == "video"]
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    if not video_streams or not audio_streams:
        return CheckResult(f"video_{label}_playable", False, "missing video or audio stream")

    stream = video_streams[0]
    if int(stream["width"]) != video_result.width or int(stream["height"]) != video_result.height:
        return CheckResult(
            f"video_{label}_resolution",
            False,
            f"got {stream['width']}x{stream['height']}, expected {video_result.width}x{video_result.height}",
        )

    try:
        actual_duration = probe_duration_seconds(video_result.mp4_path)
    except FFmpegError as exc:
        return CheckResult(f"video_{label}_duration", False, f"ffprobe failed: {exc}")

    if abs(actual_duration - video_result.duration_seconds) > 2.0:
        return CheckResult(
            f"video_{label}_duration",
            False,
            f"{actual_duration:.1f}s differs from expected {video_result.duration_seconds:.1f}s by >2s",
        )

    return CheckResult(
        f"video_{label}", True, f"{video_result.width}x{video_result.height}, {actual_duration:.1f}s"
    )
