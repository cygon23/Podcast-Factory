"""Tests for the Piper (local) Arabic TTS adapter.

Mirrors tests/test_kokoro_engine.py's pattern: is_available/from_config are
tested for real (no model needed), synthesize() is tested with PiperVoice
mocked at the boundary (real voice weights are not committed to the repo -
that's the operator's job, same as Kokoro's model weights).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dorosak_factory.tts.engines.piper_engine import PiperEngine


def _make_voice_files(tmp_path):
    onnx_path = tmp_path / "ar_JO-kareem-medium.onnx"
    onnx_path.write_bytes(b"fake")
    (tmp_path / "ar_JO-kareem-medium.onnx.json").write_text("{}")
    return onnx_path


def test_is_available_false_without_configured_path():
    assert PiperEngine.is_available({}) is False


def test_is_available_false_when_onnx_file_missing(tmp_path):
    env = {"PIPER_AR_VOICE_PATH": str(tmp_path / "missing.onnx")}
    assert PiperEngine.is_available(env) is False


def test_is_available_false_when_config_json_missing(tmp_path):
    onnx_path = tmp_path / "voice.onnx"
    onnx_path.write_bytes(b"fake")
    # .onnx.json deliberately not created
    env = {"PIPER_AR_VOICE_PATH": str(onnx_path)}
    assert PiperEngine.is_available(env) is False


def test_is_available_true_when_package_importable_and_files_exist(tmp_path):
    onnx_path = _make_voice_files(tmp_path)
    env = {"PIPER_AR_VOICE_PATH": str(onnx_path)}
    assert PiperEngine.is_available(env) is True


@patch("piper.PiperVoice")
def test_synthesize_writes_a_24khz_wav(mock_piper_voice_cls, tmp_path):
    def fake_synthesize_wav(text, wav_file):
        # wav_file is already an open wave.Wave_write, matching the real
        # Piper API (see docs/API_PYTHON.md's `with wave.open(...) as
        # wav_file: voice.synthesize_wav(text, wav_file)` usage).
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 1000)

    mock_voice = MagicMock()
    mock_voice.synthesize_wav.side_effect = fake_synthesize_wav
    mock_piper_voice_cls.load.return_value = mock_voice

    onnx_path = _make_voice_files(tmp_path)
    engine = PiperEngine(voice_path=onnx_path, work_dir=tmp_path / "out")

    result = engine.synthesize("مرحبا", voice_role="arabic_narrator")

    assert result.wav_path.exists()
    assert result.engine == "piper"
    import wave

    with wave.open(str(result.wav_path), "rb") as w:
        assert w.getframerate() == 24000
