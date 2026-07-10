"""Per-episode metadata JSON (INSTRUCTIONS.md 3, 4.2, 5)."""

from __future__ import annotations

import json
from pathlib import Path

from dorosak_factory.audio.assembly import AssemblyResult
from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.video.builder import VideoBuildResult


def build_episode_metadata(
    category: Category,
    lesson: Lesson,
    engine_name: str,
    audio_result: AssemblyResult,
    video_results: dict[str, VideoBuildResult] | None = None,
) -> dict:
    """Builds the metadata dict written alongside each episode's outputs."""
    video_results = video_results or {}
    return {
        "category": category.number,
        "category_title_en": category.title_en,
        "lesson": lesson.number,
        "title_en": lesson.title_en,
        "title_ar": lesson.title_ar,
        "engine": engine_name,
        "voice_roles": audio_result.voice_roles,
        "duration_seconds": audio_result.duration_seconds,
        "characters_synthesized": audio_result.characters_synthesized,
        "videos": {
            label: {
                "width": result.width,
                "height": result.height,
                "duration_seconds": result.duration_seconds,
            }
            for label, result in video_results.items()
        },
    }


def write_metadata_json(path: Path, metadata: dict) -> None:
    """Writes `metadata` as pretty-printed, Unicode-safe JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
