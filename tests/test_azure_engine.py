"""Tests for the Azure Speech TTS adapter, with the SDK mocked at its boundary."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import azure.cognitiveservices.speech as speechsdk
import pytest

from dorosak_factory.tts.engines.azure_engine import AzureEngine, AzureSynthesisError


def test_is_available_requires_both_key_and_region():
    assert AzureEngine.is_available({"AZURE_SPEECH_KEY": "k", "AZURE_SPEECH_REGION": "eastus"}) is True
    assert AzureEngine.is_available({"AZURE_SPEECH_KEY": "k"}) is False
    assert AzureEngine.is_available({}) is False


def _make_completed_result(pcm_bytes: bytes = b"\x00\x00" * 24000):
    result = MagicMock()
    result.reason = speechsdk.ResultReason.SynthesizingAudioCompleted
    result.audio_data = pcm_bytes
    return result


@patch("azure.cognitiveservices.speech.SpeechSynthesizer")
@patch("azure.cognitiveservices.speech.SpeechConfig")
def test_synthesize_uses_resolved_voice_and_writes_wav(mock_config_cls, mock_synth_cls, tmp_path):
    mock_synthesizer = MagicMock()
    mock_synth_cls.return_value = mock_synthesizer
    mock_synthesizer.speak_ssml_async.return_value.get.return_value = _make_completed_result()

    engine = AzureEngine(subscription_key="k", region="eastus", work_dir=tmp_path)
    result = engine.synthesize("Hello there.", voice_role="female_1", speed=1.0)

    ssml_arg = mock_synthesizer.speak_ssml_async.call_args.args[0]
    assert "en-US-JennyNeural" in ssml_arg  # DEFAULT_VOICE_MAP["female_1"]
    assert "Hello there." in ssml_arg
    assert result.wav_path.exists()
    assert result.engine == "azure"


@patch("azure.cognitiveservices.speech.SpeechSynthesizer")
@patch("azure.cognitiveservices.speech.SpeechConfig")
def test_synthesize_unknown_role_raises(mock_config_cls, mock_synth_cls, tmp_path):
    engine = AzureEngine(subscription_key="k", region="eastus", work_dir=tmp_path, voice_map={})
    engine._voice_map = {}

    with pytest.raises(ValueError, match="female_1"):
        engine.synthesize("Hi.", voice_role="female_1")


@patch("azure.cognitiveservices.speech.SpeechSynthesizer")
@patch("azure.cognitiveservices.speech.SpeechConfig")
def test_canceled_result_raises_after_retries_exhausted(mock_config_cls, mock_synth_cls, tmp_path):
    mock_synthesizer = MagicMock()
    mock_synth_cls.return_value = mock_synthesizer

    canceled_result = MagicMock()
    canceled_result.reason = speechsdk.ResultReason.Canceled
    canceled_result.cancellation_details = MagicMock(reason="Error", error_details="auth failed")
    mock_synthesizer.speak_ssml_async.return_value.get.return_value = canceled_result

    engine = AzureEngine(subscription_key="k", region="eastus", work_dir=tmp_path)

    with patch("dorosak_factory.tts.retry.time.sleep"):
        with pytest.raises(AzureSynthesisError, match="auth failed"):
            engine.synthesize("Hi.", voice_role="host")

    assert mock_synthesizer.speak_ssml_async.call_count == 3  # default max_attempts in with_retries


@patch("azure.cognitiveservices.speech.SpeechSynthesizer")
@patch("azure.cognitiveservices.speech.SpeechConfig")
def test_recovers_after_transient_cancellation(mock_config_cls, mock_synth_cls, tmp_path):
    mock_synthesizer = MagicMock()
    mock_synth_cls.return_value = mock_synthesizer

    canceled_result = MagicMock()
    canceled_result.reason = speechsdk.ResultReason.Canceled
    canceled_result.cancellation_details = MagicMock(reason="ConnectionFailure", error_details="timeout")

    mock_synthesizer.speak_ssml_async.return_value.get.side_effect = [
        canceled_result,
        _make_completed_result(),
    ]

    engine = AzureEngine(subscription_key="k", region="eastus", work_dir=tmp_path)
    with patch("dorosak_factory.tts.retry.time.sleep"):
        result = engine.synthesize("Hi.", voice_role="host")

    assert result.wav_path.exists()
    assert mock_synthesizer.speak_ssml_async.call_count == 2
