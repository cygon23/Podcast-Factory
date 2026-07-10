"""Tests for the Google Cloud TTS adapter, with the SDK mocked at its boundary."""

from __future__ import annotations

import wave
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import ServiceUnavailable

from dorosak_factory.tts.engines.google_engine import GoogleEngine


def _fake_wav_bytes(duration_seconds=1.0, sample_rate=24000):
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * int(duration_seconds * sample_rate))
    return buffer.getvalue()


def test_is_available_requires_existing_credentials_file(tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    assert GoogleEngine.is_available({"GOOGLE_APPLICATION_CREDENTIALS": str(creds)}) is True
    assert (
        GoogleEngine.is_available({"GOOGLE_APPLICATION_CREDENTIALS": str(tmp_path / "missing.json")})
        is False
    )
    assert GoogleEngine.is_available({}) is False


@patch("google.cloud.texttospeech.TextToSpeechClient")
def test_synthesize_uses_resolved_voice_and_writes_wav(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.audio_content = _fake_wav_bytes()
    mock_client.synthesize_speech.return_value = mock_response

    engine = GoogleEngine(work_dir=tmp_path)
    result = engine.synthesize("Hello there.", voice_role="female_1", speed=1.0)

    call_kwargs = mock_client.synthesize_speech.call_args.kwargs
    assert call_kwargs["voice"].name == "en-US-Neural2-F"  # DEFAULT_VOICE_MAP["female_1"]
    assert call_kwargs["input"].text == "Hello there."
    assert result.wav_path.exists()
    assert result.engine == "google"


@patch("google.cloud.texttospeech.TextToSpeechClient")
def test_synthesize_unknown_role_raises(mock_client_cls, tmp_path):
    mock_client_cls.return_value = MagicMock()
    engine = GoogleEngine(work_dir=tmp_path, voice_map={})
    engine._voice_map = {}

    with pytest.raises(ValueError, match="female_1"):
        engine.synthesize("Hi.", voice_role="female_1")


@patch("google.cloud.texttospeech.TextToSpeechClient")
def test_recovers_after_transient_api_error(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.audio_content = _fake_wav_bytes()
    mock_client.synthesize_speech.side_effect = [ServiceUnavailable("try again"), mock_response]

    engine = GoogleEngine(work_dir=tmp_path)
    with patch("dorosak_factory.tts.retry.time.sleep"):
        result = engine.synthesize("Hi.", voice_role="host")

    assert result.wav_path.exists()
    assert mock_client.synthesize_speech.call_count == 2
