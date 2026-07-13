"""Tests for the video renderer registry: explicit selection + auto-detection chain.

Mirrors tts/registry.py's tested pattern exactly, so a future local avatar
renderer or cloud API renderer (HeyGen, D-ID, Synthesia, ...) plugs in the
same way a new TTS engine does - one adapter file, one registration line,
nothing else changes.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from dorosak_factory.video.renderer_base import VideoBuildResult, VideoRenderer
from dorosak_factory.video.renderer_registry import RendererResolutionError, Registry
from dorosak_factory.video.renderers.static_background_renderer import StaticBackgroundRenderer


class _FakeRenderer(VideoRenderer):
    name = "fake"
    available = False
    hint = "set FAKE_MODEL_PATH"

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return cls.available

    @classmethod
    def availability_hint(cls) -> str:
        return cls.hint

    @classmethod
    def from_config(cls, config):
        return cls()

    def render(self, *args, **kwargs) -> VideoBuildResult:
        raise NotImplementedError


def make_fake(name: str, available: bool, hint: str = "configure me"):
    return type(
        name.capitalize() + "Renderer",
        (_FakeRenderer,),
        {"name": name, "available": available, "hint": hint},
    )


@pytest.fixture
def registry():
    reg = Registry(priority=["local_avatar", "static_background"])
    reg.register(StaticBackgroundRenderer)
    return reg


def test_explicit_renderer_selection_returns_requested_renderer(registry):
    renderer_cls = registry.resolve_renderer_class(explicit="static_background")
    assert renderer_cls is StaticBackgroundRenderer


def test_explicit_unknown_renderer_raises_clear_error(registry):
    with pytest.raises(RendererResolutionError, match="Unknown"):
        registry.resolve_renderer_class(explicit="nonexistent")


def test_static_background_is_always_available(registry):
    resolved = registry.resolve_renderer_class(env={})
    assert resolved is StaticBackgroundRenderer


def test_auto_chain_prefers_higher_priority_renderer_when_available(registry):
    avatar = make_fake("local_avatar", available=True)
    registry.register(avatar)

    resolved = registry.resolve_renderer_class(env={})

    assert resolved is avatar  # local_avatar precedes static_background in priority


def test_auto_chain_falls_back_when_higher_priority_unavailable(registry):
    avatar = make_fake("local_avatar", available=False)
    registry.register(avatar)

    resolved = registry.resolve_renderer_class(env={})

    assert resolved is StaticBackgroundRenderer


def test_get_renderer_class_by_name(registry):
    assert registry.get("static_background") is StaticBackgroundRenderer


def test_get_unknown_renderer_class_raises(registry):
    with pytest.raises(RendererResolutionError):
        registry.get("nonexistent")
