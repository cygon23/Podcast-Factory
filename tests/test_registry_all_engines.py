"""Verifies the real auto-detection chain across all 6 registered engines (mocked env vars).

Complements test_tts_registry.py (which tests the Registry mechanism in
isolation with fake engines) by proving the actual production registry
resolves correctly once every real adapter is wired in.
"""

from __future__ import annotations

import dorosak_factory.tts.engines as engines_pkg  # noqa: F401 - registers everything
from dorosak_factory.tts.engines.azure_engine import AzureEngine
from dorosak_factory.tts.engines.google_engine import GoogleEngine
from dorosak_factory.tts.engines.openai_engine import OpenAIEngine
from dorosak_factory.tts.registry import EngineResolutionError, default_registry


def test_all_six_engines_are_registered():
    for name in ("null", "kokoro", "azure", "openai", "google", "polly", "elevenlabs"):
        assert default_registry.get(name) is not None


def test_no_credentials_anywhere_raises_actionable_error():
    import pytest

    with pytest.raises(EngineResolutionError) as exc_info:
        default_registry.resolve_engine_class(env={})
    message = str(exc_info.value)
    assert "kokoro" in message
    assert "openai" in message or "OPENAI_API_KEY" in message


def test_only_openai_key_set_resolves_to_openai():
    resolved = default_registry.resolve_engine_class(env={"OPENAI_API_KEY": "sk-test"})
    assert resolved is OpenAIEngine


def test_azure_takes_priority_over_openai_when_both_configured():
    env = {
        "AZURE_SPEECH_KEY": "key",
        "AZURE_SPEECH_REGION": "eastus",
        "OPENAI_API_KEY": "sk-test",
    }
    resolved = default_registry.resolve_engine_class(env=env)
    assert resolved is AzureEngine


def test_google_resolves_when_only_google_credentials_present(tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    env = {"GOOGLE_APPLICATION_CREDENTIALS": str(creds)}
    resolved = default_registry.resolve_engine_class(env=env)
    assert resolved is GoogleEngine


def test_explicit_engine_wins_even_if_unavailable():
    # "null" is always available anyway, but explicit selection must bypass
    # the priority chain entirely - it's not even consulted.
    resolved = default_registry.resolve_engine_class(explicit="elevenlabs", env={})
    from dorosak_factory.tts.engines.elevenlabs_engine import ElevenLabsEngine

    assert resolved is ElevenLabsEngine
