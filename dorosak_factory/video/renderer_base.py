"""Abstract video renderer interface. Every rendering backend implements this contract.

Mirrors tts/base.py's TTSEngine pattern: a static-background ffmpeg renderer,
a future local avatar renderer, and future cloud API renderers (HeyGen, D-ID,
Synthesia, ...) all plug in here without the pipeline knowing which one is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.video.builder import VideoBuildResult

if TYPE_CHECKING:
    from dorosak_factory.config import Config

__all__ = ["VideoBuildResult", "VideoRenderer"]


class VideoRenderer(ABC):
    """Abstract interface every video renderer must implement.

    Output is always one MP4 at the requested width/height, so downstream
    manifest/validation logic is renderer-agnostic.
    """

    name: str

    @classmethod
    @abstractmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        """Whether this renderer can actually be used right now (model/package/keys present)."""

    @classmethod
    @abstractmethod
    def from_config(cls, config: "Config") -> "VideoRenderer":
        """Builds an instance from the loaded Config - the CLI's one uniform instantiation path."""

    @classmethod
    def availability_hint(cls) -> str:
        """Human-readable instructions for making this renderer available, for error messages."""
        return f"no availability hint provided for renderer '{cls.name}'"

    @abstractmethod
    def render(
        self,
        category: Category,
        lesson: Lesson,
        episode_mp3_path: Path,
        dialogue_ass_path: Path,
        output_mp4_path: Path,
        work_dir: Path,
        width: int,
        height: int,
    ) -> VideoBuildResult:
        """Renders one MP4 (either 16:9 or 9:16, per `width`/`height`) for `lesson`."""
