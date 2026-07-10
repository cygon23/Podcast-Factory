"""Kokoro TTS adapter: local, $0, no API key (INSTRUCTIONS.md section 4.3/docs/OPERATOR_TODO.md).

The operator downloads the model (hexgrad/Kokoro-82M) and points
KOKORO_MODEL_PATH / KOKORO_CONFIG_PATH / KOKORO_VOICES_DIR at the local
weight/config/voices files - this adapter never downloads anything itself.

IMPORTANT: kokoro's own `KPipeline` will silently call `hf_hub_download`
(a network fetch) if you pass it a bare voice name like "af_bella" instead
of a path ending in ".pt" - that would violate this project's "never
download anything" rule. To guarantee zero network access, this adapter
always resolves voice roles to a full local file path
(`KOKORO_VOICES_DIR/{voice}.pt`) before calling the pipeline, and fails
loudly (MissingAssetError-style ValueError) if that file isn't present
rather than letting kokoro reach out to the network.

GPU is used automatically when available (CUDA, then Apple MPS), falling
back to CPU, with the resolved device logged so a slow run is explainable.

Unlike the cloud adapters, retries/rate-limiting don't apply here - this is
local inference, not a network call, so a failure is deterministic and
retrying it would just fail the same way again.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import read_wav_duration_seconds, write_pcm16_wav
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine

if TYPE_CHECKING:
    from dorosak_factory.config import Config

logger = logging.getLogger(__name__)

KOKORO_REPO_ID = "hexgrad/Kokoro-82M"


class KokoroEngine(TTSEngine):
    """Adapter for the local Kokoro-82M model."""

    name = "kokoro"

    # Kokoro's published voicepack names (American/British x female/male);
    # verify against the operator's actual downloaded model - voice
    # availability can change between model releases.
    DEFAULT_VOICE_MAP = {
        "host": "am_michael",
        "female_1": "af_bella",
        "male_1": "am_adam",
        "female_2": "af_sarah",
        "male_2": "bm_george",
        "neutral_1": "af_nicole",
    }

    def __init__(
        self,
        model_path: Path,
        config_path: Path,
        voices_dir: Path,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
        device: str | None = None,
    ) -> None:
        from kokoro import KModel, KPipeline

        resolved_device = device or self._detect_device()
        logger.info("Kokoro engine using device: %s", resolved_device)

        model = KModel(config=str(config_path), model=str(model_path)).to(resolved_device).eval()
        self._pipeline = KPipeline(
            lang_code="a", repo_id=KOKORO_REPO_ID, model=model, device=resolved_device
        )
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._voices_dir = Path(voices_dir)
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._device = resolved_device

    @staticmethod
    def _detect_device() -> str:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        import importlib.util

        if importlib.util.find_spec("kokoro") is None:
            return False
        model_path = env.get("KOKORO_MODEL_PATH")
        config_path = env.get("KOKORO_CONFIG_PATH")
        voices_dir = env.get("KOKORO_VOICES_DIR")
        if not model_path or not config_path or not voices_dir:
            return False
        return Path(model_path).exists() and Path(config_path).exists() and Path(voices_dir).is_dir()

    @classmethod
    def availability_hint(cls) -> str:
        return (
            "Install the kokoro package, download hexgrad/Kokoro-82M, and set "
            "KOKORO_MODEL_PATH + KOKORO_CONFIG_PATH + KOKORO_VOICES_DIR in .env "
            "to the local weight/config/voices files (see docs/OPERATOR_TODO.md step 4)"
        )

    @classmethod
    def from_config(cls, config: "Config") -> "KokoroEngine":
        return cls(
            model_path=Path(os.environ["KOKORO_MODEL_PATH"]),
            config_path=Path(os.environ["KOKORO_CONFIG_PATH"]),
            voices_dir=Path(os.environ["KOKORO_VOICES_DIR"]),
            work_dir=config.audio.work_dir / "kokoro_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        import torch

        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No Kokoro voice configured for role '{voice_role}'. "
                f"Add it under tts.voice_map.kokoro in config.yaml."
            )

        voice_path = self._voices_dir / f"{voice_id}.pt"
        if not voice_path.exists():
            raise ValueError(
                f"Kokoro voice file not found: {voice_path}. Download it from "
                f"https://huggingface.co/{KOKORO_REPO_ID}/tree/main/voices "
                f"(see docs/OPERATOR_TODO.md step 4)."
            )

        output_path = self._path_for(text, voice_id, speed)
        # Pass the resolved local .pt path (not the bare name) so kokoro's
        # pipeline loads it directly and never calls hf_hub_download.
        segments = list(self._pipeline(text, voice=str(voice_path), speed=speed))
        audio_tensors = [segment.audio for segment in segments if segment.audio is not None]
        if not audio_tensors:
            raise RuntimeError(f"Kokoro produced no audio for voice '{voice_id}'")

        full_audio = torch.cat(audio_tensors, dim=-1) if len(audio_tensors) > 1 else audio_tensors[0]
        self._write_audio_tensor(full_audio, output_path)

        return SynthesisResult(
            wav_path=output_path,
            duration_seconds=read_wav_duration_seconds(output_path),
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    @staticmethod
    def _write_audio_tensor(audio_tensor, output_path: Path) -> None:
        import numpy as np

        audio_np = audio_tensor.detach().cpu().numpy()
        audio_np = np.clip(audio_np, -1.0, 1.0)
        pcm_bytes = (audio_np * 32767.0).astype(np.int16).tobytes()
        write_pcm16_wav(output_path, pcm_bytes, sample_rate=24000)

    def _path_for(self, key_text: str, voice_id: str, speed: float) -> Path:
        cache_key = f"{self.name}|{self._device}|{voice_id}|{speed}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
