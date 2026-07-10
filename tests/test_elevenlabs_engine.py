"""Tests for the ElevenLabs TTS adapter, with the SDK mocked at its boundary."""

from __future__ import annotations

import wave
from unittest.mock import MagicMock, patch

import pytest
from elevenlabs.core.api_error import ApiError

from dorosak_factory.tts.engines.elevenlabs_engine import ElevenLabsEngine


def _fake_wav_bytes(duration_seconds=1.0, sample_rate=24000):
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * int(duration_seconds * sample_rate))
    return buffer.getvalue()


def test_is_available_requires_api_key():
    assert ElevenLabsEngine.is_available({"ELEVENLABS_API_KEY": "k"}) is True
    assert ElevenLabsEngine.is_available({}) is False


def test_default_voice_map_is_empty_by_design():
    assert ElevenLabsEngine.DEFAULT_VOICE_MAP == {}


@patch("elevenlabs.client.ElevenLabs")
def test_synthesize_requires_configured_voice_id(mock_eleven_cls, tmp_path):
    mock_eleven_cls.return_value = MagicMock()
    engine = ElevenLabsEngine(api_key="k", work_dir=tmp_path)  # no voice_map given

    with pytest.raises(ValueError, match="host"):
        engine.synthesize("Hi.", voice_role="host")


@patch("elevenlabs.client.ElevenLabs")
def test_synthesize_uses_configured_voice_and_writes_wav(mock_eleven_cls, tmp_path):
    mock_client = MagicMock()
    mock_eleven_cls.return_value = mock_client
    mock_client.text_to_speech.convert.return_value = iter([_fake_wav_bytes()])

    engine = ElevenLabsEngine(api_key="k", work_dir=tmp_path, voice_map={"host": "voice-abc-123"})
    result = engine.synthesize("Hello there.", voice_role="host")

    call_kwargs = mock_client.text_to_speech.convert.call_args.kwargs
    assert call_kwargs["voice_id"] == "voice-abc-123"
    assert call_kwargs["text"] == "Hello there."
    assert call_kwargs["output_format"] == "wav_24000"
    assert result.wav_path.exists()
    assert result.engine == "elevenlabs"


@patch("elevenlabs.client.ElevenLabs")
def test_recovers_after_transient_api_error(mock_eleven_cls, tmp_path):
    mock_client = MagicMock()
    mock_eleven_cls.return_value = mock_client
    mock_client.text_to_speech.convert.side_effect = [
        ApiError(status_code=503, body="try again"),
        iter([_fake_wav_bytes()]),
    ]

    engine = ElevenLabsEngine(api_key="k", work_dir=tmp_path, voice_map={"host": "voice-abc-123"})
    with patch("dorosak_factory.tts.retry.time.sleep"):
        result = engine.synthesize("Hi.", voice_role="host")

    assert result.wav_path.exists()
    assert mock_client.text_to_speech.convert.call_count == 2
