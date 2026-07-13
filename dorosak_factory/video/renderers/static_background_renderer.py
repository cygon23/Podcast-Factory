"""Static-background renderer: wraps the existing pure-FFmpeg build_video() pipeline.

This is the always-available default (registered under "static_background"),
analogous to how NullEngine is always available for TTS - except this one is
a fully real, production-quality renderer, not a test stub. It resolves the
per-category background image the same way pipeline.py used to inline.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.parser.models import Category, Lesson
from dorosak_factory.video.builder import VideoBuildResult, build_video
from dorosak_factory.video.renderer_base import VideoRenderer

if TYPE_CHECKING:
    from dorosak_factory.config import Config


class StaticBackgroundRenderer(VideoRenderer):
    """Looped background image + burned ASS subtitles (title, dialogue, vocab card)."""

    name = "static_background"

    def __init__(
        self,
        backgrounds_dir: Path,
        default_background: Path,
        font_name: str,
        title_card_seconds: float,
        vocab_seconds_per_item: float,
        vocab_min_seconds: float,
    ) -> None:
        self._backgrounds_dir = backgrounds_dir
        self._default_background = default_background
        self._font_name = font_name
        self._title_card_seconds = title_card_seconds
        self._vocab_seconds_per_item = vocab_seconds_per_item
        self._vocab_min_seconds = vocab_min_seconds

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return True

    @classmethod
    def availability_hint(cls) -> str:
        return "always available (no external model or API key required)"

    @classmethod
    def from_config(cls, config: "Config") -> "StaticBackgroundRenderer":
        video = config.video
        return cls(
            backgrounds_dir=video.backgrounds_dir,
            default_background=video.default_background,
            font_name=video.font_name,
            title_card_seconds=video.title_card_seconds,
            vocab_seconds_per_item=video.vocab_seconds_per_item,
            vocab_min_seconds=video.vocab_min_seconds,
        )

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
        background_path = self._backgrounds_dir / f"cat{category.number}.png"
        if not background_path.exists():
            background_path = self._default_background

        return build_video(
            category,
            lesson,
            episode_mp3_path,
            dialogue_ass_path,
            background_path,
            output_mp4_path,
            work_dir,
            width,
            height,
            font_name=self._font_name,
            title_card_seconds=self._title_card_seconds,
            vocab_seconds_per_item=self._vocab_seconds_per_item,
            vocab_min_seconds=self._vocab_min_seconds,
        )
