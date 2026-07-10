"""Tests for the Amazon Polly TTS adapter, with boto3 mocked at its boundary."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from dorosak_factory.tts.engines.polly_engine import PollyEngine


def _fake_pcm_bytes(duration_seconds=1.0, sample_rate=24000):
    sample_count = int(duration_seconds * sample_rate)
    return struct.pack(f"<{sample_count}h", *([0] * sample_count))


def test_is_available_requires_both_credentials():
    assert PollyEngine.is_available({"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b"}) is True
    assert PollyEngine.is_available({"AWS_ACCESS_KEY_ID": "a"}) is False
    assert PollyEngine.is_available({}) is False


@patch("boto3.client")
def test_synthesize_uses_resolved_voice_and_writes_wav(mock_boto_client, tmp_path):
    mock_polly = MagicMock()
    mock_boto_client.return_value = mock_polly
    mock_polly.synthesize_speech.return_value = {
        "AudioStream": MagicMock(read=lambda: _fake_pcm_bytes())
    }

    engine = PollyEngine(region_name="us-east-1", work_dir=tmp_path)
    result = engine.synthesize("Hello there.", voice_role="female_1", speed=1.0)

    call_kwargs = mock_polly.synthesize_speech.call_args.kwargs
    assert call_kwargs["VoiceId"] == "Joanna"  # DEFAULT_VOICE_MAP["female_1"]
    assert call_kwargs["Engine"] == "neural"
    assert call_kwargs["OutputFormat"] == "pcm"
    assert "Hello there." in call_kwargs["Text"]
    assert result.wav_path.exists()
    assert result.engine == "polly"


@patch("boto3.client")
def test_synthesize_unknown_role_raises(mock_boto_client, tmp_path):
    mock_boto_client.return_value = MagicMock()
    engine = PollyEngine(region_name="us-east-1", work_dir=tmp_path, voice_map={})
    engine._voice_map = {}

    with pytest.raises(ValueError, match="female_1"):
        engine.synthesize("Hi.", voice_role="female_1")


@patch("boto3.client")
def test_recovers_after_transient_client_error(mock_boto_client, tmp_path):
    mock_polly = MagicMock()
    mock_boto_client.return_value = mock_polly

    error = ClientError({"Error": {"Code": "Throttling", "Message": "slow down"}}, "SynthesizeSpeech")
    success = {"AudioStream": MagicMock(read=lambda: _fake_pcm_bytes())}
    mock_polly.synthesize_speech.side_effect = [error, success]

    engine = PollyEngine(region_name="us-east-1", work_dir=tmp_path)
    with patch("dorosak_factory.tts.retry.time.sleep"):
        result = engine.synthesize("Hi.", voice_role="host")

    assert result.wav_path.exists()
    assert mock_polly.synthesize_speech.call_count == 2
