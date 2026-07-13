"""Orchestrates one lesson's full processing: audio -> subtitles -> video -> validate -> manifest.

This is the unit of work the CLI's `run` command parallelizes across
lessons (INSTRUCTIONS.md 4.7/4.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dorosak_factory.audio.assembly import AssemblyResult, assemble_lesson_audio
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import Config
from dorosak_factory.manifest.store import Manifest, ManifestRecord
from dorosak_factory.metadata import build_episode_metadata, write_metadata_json
from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.subtitles.ass import write_ass
from dorosak_factory.subtitles.srt import write_srt
from dorosak_factory.tts.base import TTSEngine
from dorosak_factory.validate.episode import EpisodeValidationResult, validate_episode
from dorosak_factory.video.renderer_base import VideoBuildResult, VideoRenderer

RESOLUTION_BY_LABEL = {"16:9": (1920, 1080), "9:16": (1080, 1920)}


def estimate_characters(lesson: Lesson) -> int:
    """Character count that would be synthesized for `lesson` (dry-run cost estimation)."""
    total = len(lesson.host_intro)
    for turn in lesson.turns:
        total += sum(len(paragraph) for paragraph in turn.paragraphs)
    return total


@dataclass
class LessonProcessResult:
    """Outcome of processing one lesson: what was built, and whether it validated."""

    success: bool
    failure_reason: str | None
    audio_result: AssemblyResult | None
    video_results: dict[str, VideoBuildResult]
    mp3_path: Path | None
    srt_path: Path | None
    metadata_path: Path | None
    validation: EpisodeValidationResult | None
    characters_synthesized: int


def process_lesson(
    category: Category,
    lesson: Lesson,
    engine: TTSEngine,
    engine_name: str,
    cache: LineCache,
    config: Config,
    renderer: VideoRenderer,
    formats: str = "both",
    min_duration_seconds: float = 30.0,
) -> LessonProcessResult:
    """Runs the full pipeline for one lesson. Never raises: failures are captured in the result."""
    lesson_dir = config.pipeline.output_dir / f"cat{category.number}" / f"lesson{lesson.number}"
    lesson_dir.mkdir(parents=True, exist_ok=True)

    try:
        mp3_path = lesson_dir / "episode.mp3"
        voice_id_map = config.tts.voice_map.get(engine_name, {})
        audio_result = assemble_lesson_audio(
            category,
            lesson,
            engine,
            cache,
            config.audio,
            mp3_path,
            model=config.tts.model,
            voice_id_map=voice_id_map,
            voice_role_overrides=config.tts.character_role_overrides,
            speed=config.tts.speed,
        )

        srt_path = lesson_dir / "episode.srt"
        write_srt(audio_result.timeline, srt_path)

        video_results: dict[str, VideoBuildResult] = {}
        if formats in ("video", "both"):
            for label in config.video.resolutions:
                width, height = RESOLUTION_BY_LABEL[label]
                dialogue_ass_path = lesson_dir / f"dialogue_{label.replace(':', 'x')}.ass"
                write_ass(
                    audio_result.timeline,
                    dialogue_ass_path,
                    video_width=width,
                    video_height=height,
                    font_name=config.video.font_name,
                )
                output_mp4 = lesson_dir / f"video_{label.replace(':', 'x')}.mp4"
                work_dir = (
                    config.audio.work_dir / f"video_cat{category.number}_lesson{lesson.number}_{label}"
                )
                video_results[label] = renderer.render(
                    category,
                    lesson,
                    mp3_path,
                    dialogue_ass_path,
                    output_mp4,
                    work_dir,
                    width,
                    height,
                )

        metadata_path = lesson_dir / "metadata.json"
        metadata = build_episode_metadata(category, lesson, engine_name, audio_result, video_results)
        write_metadata_json(metadata_path, metadata)

        validation = validate_episode(
            audio_result,
            mp3_path,
            srt_path,
            metadata_path,
            video_results=video_results,
            min_duration_seconds=min_duration_seconds,
        )

        return LessonProcessResult(
            success=validation.passed,
            failure_reason=None if validation.passed else validation.failure_summary,
            audio_result=audio_result,
            video_results=video_results,
            mp3_path=mp3_path,
            srt_path=srt_path,
            metadata_path=metadata_path,
            validation=validation,
            characters_synthesized=audio_result.characters_synthesized,
        )
    except Exception as exc:  # noqa: BLE001 - one lesson's failure must never crash the run
        return LessonProcessResult(
            success=False,
            failure_reason=str(exc),
            audio_result=None,
            video_results={},
            mp3_path=None,
            srt_path=None,
            metadata_path=None,
            validation=None,
            characters_synthesized=0,
        )


def record_result(
    manifest: Manifest,
    category_number: int,
    lesson: Lesson,
    engine_name: str,
    result: LessonProcessResult,
) -> None:
    """Writes one lesson's outcome into the manifest."""
    manifest.upsert_record(
        ManifestRecord(
            category_number=category_number,
            lesson_number=lesson.number,
            content_hash=Manifest.compute_content_hash(lesson),
            engine=engine_name,
            audio_path=str(result.mp3_path) if result.mp3_path else None,
            video_16x9_path=(
                str(result.video_results["16:9"].mp4_path) if "16:9" in result.video_results else None
            ),
            video_9x16_path=(
                str(result.video_results["9:16"].mp4_path) if "9:16" in result.video_results else None
            ),
            srt_path=str(result.srt_path) if result.srt_path else None,
            metadata_json_path=str(result.metadata_path) if result.metadata_path else None,
            status="success" if result.success else "failed",
            failure_reason=result.failure_reason,
            characters_synthesized=result.characters_synthesized,
        )
    )
