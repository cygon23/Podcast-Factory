"""OpenAI TTS adapter (INSTRUCTIONS.md 4.1/4.3). Requires OPENAI_API_KEY."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import concat_wavs, read_wav_duration_seconds
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine
from dorosak_factory.tts.chunking import chunk_text
from dorosak_factory.tts.retry import with_retries

if TYPE_CHECKING:
    from dorosak_factory.config import Config

MAX_CHARS = 4096  # OpenAI TTS input limit


class OpenAIEngine(TTSEngine):
    """Adapter for OpenAI's `audio.speech` TTS API."""

    name = "openai"

    DEFAULT_VOICE_MAP = {
        "host": "onyx",
        "female_1": "nova",
        "male_1": "echo",
        "female_2": "shimmer",
        "male_2": "fable",
        "neutral_1": "alloy",
    }

    def __init__(
        self,
        api_key: str,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
        model: str = "tts-1",
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._model = model

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return bool(env.get("OPENAI_API_KEY"))

    @classmethod
    def availability_hint(cls) -> str:
        return "Set OPENAI_API_KEY in .env (see https://platform.openai.com/api-keys)"

    @classmethod
    def from_config(cls, config: "Config") -> "OpenAIEngine":
        model = config.tts.model if config.tts.model != "default" else "tts-1"
        return cls(
            api_key=os.environ["OPENAI_API_KEY"],
            work_dir=config.audio.work_dir / "openai_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
            model=model,
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        import openai

        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No OpenAI voice configured for role '{voice_role}'. "
                f"Add it under tts.voice_map.openai in config.yaml."
            )

        chunks = chunk_text(text, MAX_CHARS) or [text]
        chunk_paths = []
        for index, chunk in enumerate(chunks):
            chunk_path = self._path_for(f"{text}|{index}", voice_id, speed)

            def call(chunk=chunk, chunk_path=chunk_path) -> None:
                response = self._client.audio.speech.create(
                    model=self._model,
                    voice=voice_id,
                    input=chunk,
                    response_format="wav",
                    speed=speed,
                )
                response.write_to_file(str(chunk_path))

            with_retries(
                call,
                retryable_exceptions=(
                    openai.APIConnectionError,
                    openai.RateLimitError,
                    openai.InternalServerError,
                    openai.APITimeoutError,
                ),
            )
            chunk_paths.append(chunk_path)

        final_path = chunk_paths[0] if len(chunk_paths) == 1 else self._path_for(text, voice_id, speed)
        if len(chunk_paths) > 1:
            concat_wavs(chunk_paths, final_path)

        return SynthesisResult(
            wav_path=final_path,
            duration_seconds=read_wav_duration_seconds(final_path),
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    def _path_for(self, key_text: str, voice_id: str, speed: float) -> Path:
        cache_key = f"{self.name}|{self._model}|{voice_id}|{speed}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
