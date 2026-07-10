"""Tests for the Kokoro (local) TTS adapter.

The `kokoro` package itself is installed (pure-Python wrapper), but real
model weights are not - and must not be downloaded here (that's the
operator's job). So `is_available` and device detection are tested for
real; `synthesize` is tested with KModel/KPipeline mocked at the boundary.

Also verifies the fix for a real bug: kokoro's own pipeline calls
`hf_hub_download` (a network fetch) if given a bare voice name instead of a
path ending in ".pt" - this adapter must always resolve to a local file
path so it never reaches the network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from dorosak_factory.tts.engines.kokoro_engine import KokoroEngine


def _make_env(tmp_path, with_voices_dir=True):
    model_path = tmp_path / "model.pth"
    config_path = tmp_path / "config.json"
    model_path.write_bytes(b"fake")
    config_path.write_text("{}")
    env = {"KOKORO_MODEL_PATH": str(model_path), "KOKORO_CONFIG_PATH": str(config_path)}
    if with_voices_dir:
        voices_dir = tmp_path / "voices"
        voices_dir.mkdir()
        env["KOKORO_VOICES_DIR"] = str(voices_dir)
    return env


def test_is_available_false_without_configured_paths():
    assert KokoroEngine.is_available({}) is False


def test_is_available_false_when_configured_paths_do_not_exist(tmp_path):
    env = {
        "KOKORO_MODEL_PATH": str(tmp_path / "missing_model.pth"),
        "KOKORO_CONFIG_PATH": str(tmp_path / "missing_config.json"),
        "KOKORO_VOICES_DIR": str(tmp_path / "missing_voices"),
    }
    assert KokoroEngine.is_available(env) is False


def test_is_available_false_when_voices_dir_missing(tmp_path):
    env = _make_env(tmp_path, with_voices_dir=False)
    assert KokoroEngine.is_available(env) is False


def test_is_available_true_when_package_importable_and_files_exist(tmp_path):
    env = _make_env(tmp_path)
    assert KokoroEngine.is_available(env) is True


def test_device_detection_falls_back_to_cpu_without_gpu():
    # This sandbox has no CUDA/MPS - confirms the real fallback path, not a mock.
    assert KokoroEngine._detect_device() == "cpu"


def _make_fake_segment(num_samples=2400):
    segment = MagicMock()
    segment.audio = torch.zeros(num_samples)
    return segment


def _make_engine(tmp_path, voice_map=None):
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir(exist_ok=True)
    return (
        KokoroEngine(
            model_path=tmp_path / "model.pth",
            config_path=tmp_path / "config.json",
            voices_dir=voices_dir,
            work_dir=tmp_path / "out",
            voice_map=voice_map,
        ),
        voices_dir,
    )


@patch("kokoro.KPipeline")
@patch("kokoro.KModel")
def test_synthesize_resolves_voice_to_a_local_pt_path_not_a_bare_name(
    mock_kmodel_cls, mock_kpipeline_cls, tmp_path
):
    mock_model_instance = MagicMock()
    mock_model_instance.to.return_value = mock_model_instance
    mock_model_instance.eval.return_value = mock_model_instance
    mock_kmodel_cls.return_value = mock_model_instance

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = iter([_make_fake_segment()])
    mock_kpipeline_cls.return_value = mock_pipeline

    engine, voices_dir = _make_engine(tmp_path)
    (voices_dir / "af_bella.pt").write_bytes(b"fake voice pack")

    result = engine.synthesize("Hello there.", voice_role="female_1", speed=1.0)

    call_kwargs = mock_pipeline.call_args.kwargs
    # Must be a real local path ending in .pt (never a bare name like
    # "af_bella"), or kokoro would try to download it from the hub.
    assert call_kwargs["voice"] == str(voices_dir / "af_bella.pt")
    assert call_kwargs["voice"].endswith(".pt")
    assert result.wav_path.exists()
    assert result.engine == "kokoro"


@patch("kokoro.KPipeline")
@patch("kokoro.KModel")
def test_synthesize_missing_voice_file_raises_clear_error_instead_of_downloading(
    mock_kmodel_cls, mock_kpipeline_cls, tmp_path
):
    mock_model_instance = MagicMock()
    mock_model_instance.to.return_value = mock_model_instance
    mock_model_instance.eval.return_value = mock_model_instance
    mock_kmodel_cls.return_value = mock_model_instance
    mock_kpipeline_cls.return_value = MagicMock()

    engine, voices_dir = _make_engine(tmp_path)
    # af_bella.pt deliberately not created in voices_dir.

    with pytest.raises(ValueError, match="af_bella.pt"):
        engine.synthesize("Hi.", voice_role="female_1")

    # The pipeline must never be invoked - no chance of a network fetch.
    mock_kpipeline_cls.return_value.assert_not_called()


@patch("kokoro.KPipeline")
@patch("kokoro.KModel")
def test_synthesize_unknown_role_raises(mock_kmodel_cls, mock_kpipeline_cls, tmp_path):
    mock_model_instance = MagicMock()
    mock_model_instance.to.return_value = mock_model_instance
    mock_model_instance.eval.return_value = mock_model_instance
    mock_kmodel_cls.return_value = mock_model_instance
    mock_kpipeline_cls.return_value = MagicMock()

    engine, _ = _make_engine(tmp_path, voice_map={})
    engine._voice_map = {}

    with pytest.raises(ValueError, match="female_1"):
        engine.synthesize("Hi.", voice_role="female_1")


@patch("kokoro.KPipeline")
@patch("kokoro.KModel")
def test_synthesize_concatenates_multiple_pipeline_segments(
    mock_kmodel_cls, mock_kpipeline_cls, tmp_path
):
    mock_model_instance = MagicMock()
    mock_model_instance.to.return_value = mock_model_instance
    mock_model_instance.eval.return_value = mock_model_instance
    mock_kmodel_cls.return_value = mock_model_instance

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = iter([_make_fake_segment(2400), _make_fake_segment(2400)])
    mock_kpipeline_cls.return_value = mock_pipeline

    engine, voices_dir = _make_engine(tmp_path)
    (voices_dir / "am_michael.pt").write_bytes(b"fake voice pack")

    result = engine.synthesize("Two segments.", voice_role="host")

    from dorosak_factory.media_probe import probe_duration_seconds

    assert probe_duration_seconds(result.wav_path) == pytest.approx(
        0.2, abs=0.01
    )  # 4800 samples @ 24kHz
