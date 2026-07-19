"""Piper TTS adapter: local, free, Arabic voice for the course audio pipeline.

Piper (`pip install piper-tts`) is GPL-3.0 (fine here - we run it as a
tool, don't redistribute modified Piper source, and GPL doesn't restrict
the audio *output* it produces). The Arabic voice model itself
(`rhasspy/piper-voices` on Hugging Face, e.g. the `ar_JO` family) is
separately MIT-licensed - no commercial-use conflict, unlike
facebook/mms-tts-ara which is CC-BY-NC (rejected for this reason - see
docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md).

This adapter never downloads anything itself: the operator downloads a
voice's .onnx + .onnx.json pair and points PIPER_AR_VOICE_PATH at the
.onnx file - same pattern as Kokoro's KOKORO_MODEL_PATH.

Unlike Kokoro, Piper's native sample rate is not 24kHz, so synthesize()
always resamples its raw output through convert_to_pipeline_wav before
returning - every other engine in this pipeline assumes 24kHz mono
16-bit PCM WAV (see audio/wav_utils.py's module docstring); skipping this
step would corrupt concatenation with Kokoro-produced audio.
"""

from __future__ import annotations

import hashlib
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import convert_to_pipeline_wav, read_wav_duration_seconds
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine

if TYPE_CHECKING:
    from dorosak_factory.config import Config


class PiperEngine(TTSEngine):
    """Adapter for a local Piper voice model - used for the Arabic half of
    course vocabulary/examples/useful-phrases audio."""

    name = "piper"

    DEFAULT_VOICE_MAP = {
        "arabic_narrator": "ar_JO-kareem-medium",
    }

    def __init__(
        self,
        voice_path: Path,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
    ) -> None:
        from piper import PiperVoice

        self._voice = PiperVoice.load(str(voice_path))
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        import importlib.util

        if importlib.util.find_spec("piper") is None:
            return False
        voice_path = env.get("PIPER_AR_VOICE_PATH")
        if not voice_path:
            return False
        onnx_path = Path(voice_path)
        config_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
        return onnx_path.exists() and config_path.exists()

    @classmethod
    def availability_hint(cls) -> str:
        return (
            "Install piper-tts (`pip install piper-tts`), download an Arabic "
            "voice's .onnx + .onnx.json pair from rhasspy/piper-voices on "
            "Hugging Face (e.g. the ar_JO family), and set PIPER_AR_VOICE_PATH "
            "in .env to the .onnx file."
        )

    @classmethod
    def from_config(cls, config: "Config") -> "PiperEngine":
        import os

        return cls(
            voice_path=Path(os.environ["PIPER_AR_VOICE_PATH"]),
            work_dir=config.audio.work_dir / "piper_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=False, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        voice_id = self._voice_map.get(voice_role, voice_role)
        raw_path = self._path_for(text, voice_id, suffix="_raw")
        with wave.open(str(raw_path), "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file)

        output_path = self._path_for(text, voice_id, suffix="")
        convert_to_pipeline_wav(raw_path, output_path)

        return SynthesisResult(
            wav_path=output_path,
            duration_seconds=read_wav_duration_seconds(output_path),
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    def _path_for(self, key_text: str, voice_id: str, suffix: str) -> Path:
        cache_key = f"{self.name}|{voice_id}|{key_text}{suffix}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}{suffix}.wav"
