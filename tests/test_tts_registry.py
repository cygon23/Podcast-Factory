"""Tests for the TTS engine registry: explicit selection and auto-detection chain."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine
from dorosak_factory.tts.engines.null_engine import NullEngine
from dorosak_factory.tts.registry import EngineResolutionError, Registry


class _FakeEngine(TTSEngine):
    """Minimal stub engine for exercising registry logic without real providers."""

    name = "fake"
    available = False
    hint = "set FAKE_API_KEY"

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return cls.available

    @classmethod
    def availability_hint(cls) -> str:
        return cls.hint

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        raise NotImplementedError


def make_fake(name: str, available: bool, hint: str = "configure me"):
    return type(
        name.capitalize() + "Engine",
        (_FakeEngine,),
        {"name": name, "available": available, "hint": hint},
    )


@pytest.fixture
def registry():
    reg = Registry(priority=["kokoro", "azure", "openai"])
    reg.register(NullEngine)
    return reg


def test_explicit_engine_selection_returns_requested_engine(registry):
    engine_cls = registry.resolve_engine_class(explicit="null")
    assert engine_cls is NullEngine


def test_explicit_unknown_engine_raises_clear_error(registry):
    with pytest.raises(EngineResolutionError, match="Unknown"):
        registry.resolve_engine_class(explicit="nonexistent")


def test_auto_chain_skips_unavailable_and_picks_first_available(registry):
    kokoro = make_fake("kokoro", available=False)
    azure = make_fake("azure", available=True)
    registry.register(kokoro)
    registry.register(azure)

    resolved = registry.resolve_engine_class(env={})

    assert resolved is azure


def test_auto_chain_respects_priority_order(registry):
    azure = make_fake("azure", available=True)
    openai = make_fake("openai", available=True)
    registry.register(azure)
    registry.register(openai)

    resolved = registry.resolve_engine_class(env={})

    assert resolved is azure  # azure precedes openai in priority list


def test_null_engine_is_never_auto_selected(registry):
    # NullEngine is registered but not part of the priority chain, and nothing
    # else is available -> resolution must fail rather than silently picking null.
    with pytest.raises(EngineResolutionError):
        registry.resolve_engine_class(env={})


def test_no_engine_available_raises_actionable_message(registry):
    kokoro = make_fake("kokoro", available=False, hint="install kokoro + download model")
    azure = make_fake("azure", available=False, hint="set AZURE_SPEECH_KEY")
    registry.register(kokoro)
    registry.register(azure)

    with pytest.raises(EngineResolutionError) as exc_info:
        registry.resolve_engine_class(env={})

    message = str(exc_info.value)
    assert "install kokoro + download model" in message
    assert "set AZURE_SPEECH_KEY" in message


def test_get_engine_class_by_name(registry):
    assert registry.get("null") is NullEngine


def test_get_unknown_engine_class_raises(registry):
    with pytest.raises(EngineResolutionError):
        registry.get("nonexistent")
