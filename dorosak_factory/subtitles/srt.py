"""Plain .srt generation from an assembly timeline (INSTRUCTIONS.md 4.6).

No speech-to-text anywhere: timestamps come directly from the known
per-line durations recorded during audio assembly.
"""

from __future__ import annotations

from pathlib import Path

from dorosak_factory.audio.assembly import LineTiming


def format_srt_timestamp(seconds: float) -> str:
    """Formats seconds as SRT's `HH:MM:SS,mmm` timestamp."""
    total_ms = round(seconds * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_srt(timeline: tuple[LineTiming, ...]) -> str:
    """Renders a timeline into SRT text: one cue per line, "Speaker: text"."""
    if not timeline:
        raise ValueError("Cannot generate SRT from an empty timeline")

    for earlier, later in zip(timeline, timeline[1:]):
        if later.start_seconds < earlier.end_seconds:
            raise ValueError(
                "Timeline is not monotonic: "
                f"{earlier.speaker!r} ends at {earlier.end_seconds}, "
                f"but {later.speaker!r} starts at {later.start_seconds}"
            )

    blocks = []
    for index, entry in enumerate(timeline, start=1):
        blocks.append(
            f"{index}\n"
            f"{format_srt_timestamp(entry.start_seconds)} --> {format_srt_timestamp(entry.end_seconds)}\n"
            f"{entry.speaker}: {entry.text}\n"
        )
    return "\n".join(blocks)


def write_srt(timeline: tuple[LineTiming, ...], path: Path) -> None:
    """Generates and writes the .srt file for `timeline`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_srt(timeline), encoding="utf-8")
