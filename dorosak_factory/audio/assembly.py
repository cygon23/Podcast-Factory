"""Orchestrates full lesson audio assembly: per-line synthesis (cached) with
configured pauses, optional intro/outro music, loudness normalization, and
MP3 export with ID3 tags.

Produces a `timeline` of exact start/end offsets per spoken line - the
source of truth a later subtitle-generation step reads from, per
INSTRUCTIONS.md 4.6 ("start time = running offset incl. pauses").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.audio.loudness import LoudnessMeasurement, normalize_loudness
from dorosak_factory.audio.mp3_export import build_id3_tags, export_mp3
from dorosak_factory.audio.music import append_audio, mix_intro_music
from dorosak_factory.audio.wav_utils import concat_wavs, read_wav_duration_seconds, write_silence_wav
from dorosak_factory.config import AudioConfig
from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.tts.base import TTSEngine
from dorosak_factory.tts.voice_roles import assign_voice_roles

_LESSON_LABEL_RE = re.compile(r"\bLesson\s+(\d+)\b")


def rename_lesson_to_podcast(text: str) -> str:
    """Rewrites "Lesson {N}" to "Podcast {N}" - client-facing labeling requirement.

    Source Markdown scripts say "Lesson N" in the spoken Host Intro (e.g.
    "Category 30 ... Lesson 1."); the client wants every episode to open
    with "Podcast N" instead, in the actual narration, not just filenames
    or metadata. Applied only to the Host Intro - "Lesson" never appears
    in dialogue turns or vocabulary in the real source files.
    """
    return _LESSON_LABEL_RE.sub(r"Podcast \1", text)


@dataclass(frozen=True)
class LineTiming:
    """One spoken line's exact position in the assembled audio."""

    speaker: str
    text: str
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class AssemblyResult:
    """Everything downstream steps (subtitles, video, validation, reports) need."""

    mp3_path: Path
    duration_seconds: float
    timeline: tuple[LineTiming, ...]
    characters_synthesized: int
    pre_normalization_loudness: LoudnessMeasurement
    voice_roles: dict[str, str]


def assemble_lesson_audio(
    category: Category,
    lesson: Lesson,
    engine: TTSEngine,
    cache: LineCache,
    config: AudioConfig,
    output_mp3_path: Path,
    model: str = "default",
    voice_id_map: dict[str, str] | None = None,
    voice_role_overrides: dict[str, str] | None = None,
    cover_art_path: Path | None = None,
    speed: float = 1.0,
) -> AssemblyResult:
    """Synthesizes, assembles, normalizes, and exports one lesson's MP3.

    Host Intro always speaks as the `host` role. Every other character is
    assigned a role via `assign_voice_roles` (deterministic, first-appearance
    order), cached per (engine, model, voice_id, speed, text) so reruns only
    resynthesize changed lines.
    """
    voice_roles = assign_voice_roles(lesson, overrides=voice_role_overrides)
    voice_id_map = voice_id_map or {}

    def voice_id_for(role: str) -> str:
        return voice_id_map.get(role, role)

    def synthesize_line(text: str, role: str):
        return cache.get_or_synthesize(
            engine, text, voice_role=role, model=model, voice_id=voice_id_for(role), speed=speed
        )

    work_dir = Path(config.work_dir) / f"cat{category.number}_lesson{lesson.number}"
    work_dir.mkdir(parents=True, exist_ok=True)

    segments: list[Path] = []
    timeline: list[LineTiming] = []
    running_offset = 0.0
    total_characters = 0
    pause_counter = 0

    def add_pause(duration_ms: int) -> None:
        nonlocal running_offset, pause_counter
        if duration_ms <= 0:
            return
        pause_path = work_dir / f"pause_{pause_counter}.wav"
        pause_counter += 1
        write_silence_wav(pause_path, duration_ms / 1000.0)
        segments.append(pause_path)
        running_offset += duration_ms / 1000.0

    # --- Host Intro (always role "host"; optionally has intro music mixed under it) ---
    host_intro_text = rename_lesson_to_podcast(lesson.host_intro)
    host_result = synthesize_line(host_intro_text, "host")
    total_characters += host_result.characters
    host_segment_path = host_result.wav_path
    if config.music.intro_path is not None:
        mixed_path = work_dir / "host_intro_with_music.wav"
        mix_intro_music(
            host_segment_path,
            config.music.intro_path,
            mixed_path,
            fade_in_ms=config.music.intro_fade_in_ms,
            fade_out_ms=config.music.intro_fade_out_ms,
            duck_db=config.music.intro_duck_db,
        )
        host_segment_path = mixed_path
    segments.append(host_segment_path)
    timeline.append(LineTiming("Host", host_intro_text, 0.0, host_result.duration_seconds))
    running_offset = host_result.duration_seconds

    add_pause(config.pauses.after_host_intro_ms)

    # --- Dialogue turns ---
    for turn_index, turn in enumerate(lesson.turns):
        role = voice_roles[turn.speaker]
        for paragraph_index, paragraph in enumerate(turn.paragraphs):
            result = synthesize_line(paragraph, role)
            total_characters += result.characters
            segments.append(result.wav_path)
            timeline.append(
                LineTiming(
                    turn.speaker, paragraph, running_offset, running_offset + result.duration_seconds
                )
            )
            running_offset += result.duration_seconds

            is_last_paragraph = paragraph_index == len(turn.paragraphs) - 1
            if not is_last_paragraph:
                add_pause(config.pauses.between_paragraphs_ms)

        is_last_turn = turn_index == len(lesson.turns) - 1
        if not is_last_turn:
            add_pause(config.pauses.between_turns_ms)

    # --- Concatenate, optionally append outro, normalize, export ---
    raw_path = work_dir / "dialogue_raw.wav"
    concat_wavs(segments, raw_path)

    pre_export_path = raw_path
    if config.music.outro_path is not None:
        with_outro_path = work_dir / "dialogue_with_outro.wav"
        append_audio(raw_path, config.music.outro_path, with_outro_path)
        pre_export_path = with_outro_path

    normalized_path = work_dir / "normalized.wav"
    measurement = normalize_loudness(
        pre_export_path,
        normalized_path,
        target_lufs=config.loudness.target_lufs,
        target_tp=config.loudness.true_peak_dbtp,
    )

    tags = build_id3_tags(category, lesson, cover_art_path=cover_art_path)
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=config.mp3.bitrate_kbps, tags=tags)

    return AssemblyResult(
        mp3_path=output_mp3_path,
        duration_seconds=read_wav_duration_seconds(normalized_path),
        timeline=tuple(timeline),
        characters_synthesized=total_characters,
        pre_normalization_loudness=measurement,
        voice_roles=voice_roles,
    )
