"""Tests for the OpenAI TTS adapter: availability, voice resolution, retries, chunking.

No real API calls are made - the OpenAI client is mocked at the SDK
boundary so we verify our request-building/response-handling logic without
network access or incurring cost.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import openai
import pytest

from dorosak_factory.audio.wav_utils import write_silence_wav
from dorosak_factory.tts.engines.openai_engine import OpenAIEngine


def test_is_available_true_with_key():
    assert OpenAIEngine.is_available({"OPENAI_API_KEY": "sk-test"}) is True


def test_is_available_false_without_key():
    assert OpenAIEngine.is_available({}) is False


@patch("openai.OpenAI")
def test_synthesize_calls_api_with_resolved_voice_and_writes_file(mock_openai_cls, tmp_path):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    def fake_write_to_file(path):
        write_silence_wav(__import__("pathlib").Path(path), duration_seconds=1.0)

    mock_response = MagicMock()
    mock_response.write_to_file.side_effect = fake_write_to_file
    mock_client.audio.speech.create.return_value = mock_response

    engine = OpenAIEngine(api_key="sk-test", work_dir=tmp_path)
    result = engine.synthesize("Hello there.", voice_role="female_1", speed=1.0)

    call_kwargs = mock_client.audio.speech.create.call_args.kwargs
    assert call_kwargs["voice"] == "nova"  # DEFAULT_VOICE_MAP["female_1"]
    assert call_kwargs["input"] == "Hello there."
    assert call_kwargs["response_format"] == "wav"
    assert result.wav_path.exists()
    assert result.characters == len("Hello there.")
    assert result.engine == "openai"


@patch("openai.OpenAI")
def test_synthesize_unknown_role_raises_clear_error(mock_openai_cls, tmp_path):
    mock_openai_cls.return_value = MagicMock()
    engine = OpenAIEngine(api_key="sk-test", work_dir=tmp_path, voice_map={})
    engine._voice_map = {}  # no roles configured at all

    with pytest.raises(ValueError, match="female_1"):
        engine.synthesize("Hi.", voice_role="female_1")


@patch("openai.OpenAI")
def test_synthesize_retries_on_rate_limit_then_succeeds(mock_openai_cls, tmp_path):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise openai.RateLimitError("rate limited", response=MagicMock(status_code=429), body=None)
        response = MagicMock()
        response.write_to_file.side_effect = lambda path: write_silence_wav(
            __import__("pathlib").Path(path), duration_seconds=1.0
        )
        return response

    mock_client.audio.speech.create.side_effect = fake_create

    with patch("dorosak_factory.tts.retry.time.sleep"):
        engine = OpenAIEngine(api_key="sk-test", work_dir=tmp_path)
        result = engine.synthesize("Retry me.", voice_role="host")

    assert call_count["n"] == 2
    assert result.wav_path.exists()


@patch("openai.OpenAI")
def test_synthesize_chunks_long_text_into_multiple_api_calls(mock_openai_cls, tmp_path):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    def fake_create(**kwargs):
        response = MagicMock()
        response.write_to_file.side_effect = lambda path: write_silence_wav(
            __import__("pathlib").Path(path), duration_seconds=0.5
        )
        return response

    mock_client.audio.speech.create.side_effect = fake_create

    long_text = ("This is a sentence that will be repeated many times. " * 200).strip()
    engine = OpenAIEngine(api_key="sk-test", work_dir=tmp_path)
    result = engine.synthesize(long_text, voice_role="host")

    assert mock_client.audio.speech.create.call_count > 1
    assert result.wav_path.exists()
    assert result.characters == len(long_text)
