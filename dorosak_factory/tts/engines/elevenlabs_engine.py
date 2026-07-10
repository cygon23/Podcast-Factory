"""ElevenLabs TTS adapter. Requires ELEVENLABS_API_KEY.

Unlike OpenAI/Azure/Google/Polly, ElevenLabs voices are account-specific
(cloned/library voices, not universal named presets) - there is no safe
universal default voice_map here. The operator must configure
`tts.voice_map.elevenlabs` in config.yaml with real voice IDs from their
account before this engine can be used.
"""

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

MAX_CHARS = 4500


class ElevenLabsEngine(TTSEngine):
    """Adapter for ElevenLabs text-to-speech."""

    name = "elevenlabs"

    DEFAULT_VOICE_MAP: dict[str, str] = {}  # deliberately empty; see module docstring

    def __init__(
        self,
        api_key: str,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
        model_id: str = "eleven_multilingual_v2",
    ) -> None:
        from elevenlabs.client import ElevenLabs

        self._client = ElevenLabs(api_key=api_key)
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._model_id = model_id

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return bool(env.get("ELEVENLABS_API_KEY"))

    @classmethod
    def availability_hint(cls) -> str:
        return (
            "Set ELEVENLABS_API_KEY in .env (https://elevenlabs.io) and configure "
            "tts.voice_map.elevenlabs with voice IDs from your account - there is "
            "no universal default voice map for this provider."
        )

    @classmethod
    def from_config(cls, config: "Config") -> "ElevenLabsEngine":
        model_id = config.tts.model if config.tts.model != "default" else "eleven_multilingual_v2"
        return cls(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            work_dir=config.audio.work_dir / "elevenlabs_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
            model_id=model_id,
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=False, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No ElevenLabs voice configured for role '{voice_role}'. "
                f"Add a real voice ID from your account under tts.voice_map.elevenlabs in config.yaml."
            )

        chunks = chunk_text(text, MAX_CHARS) or [text]
        chunk_paths = []
        for index, chunk in enumerate(chunks):
            chunk_path = self._path_for(f"{text}|{index}", voice_id)
            self._synthesize_chunk(chunk, voice_id, chunk_path)
            chunk_paths.append(chunk_path)

        final_path = chunk_paths[0] if len(chunk_paths) == 1 else self._path_for(text, voice_id)
        if len(chunk_paths) > 1:
            concat_wavs(chunk_paths, final_path)

        return SynthesisResult(
            wav_path=final_path,
            duration_seconds=read_wav_duration_seconds(final_path),
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    def _synthesize_chunk(self, text: str, voice_id: str, output_path: Path) -> None:
        from elevenlabs.core.api_error import ApiError

        def call() -> None:
            audio_chunks = self._client.text_to_speech.convert(
                voice_id=voice_id, text=text, output_format="wav_24000", model_id=self._model_id
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"".join(audio_chunks))

        with_retries(call, retryable_exceptions=(ApiError,))

    def _path_for(self, key_text: str, voice_id: str) -> Path:
        cache_key = f"{self.name}|{self._model_id}|{voice_id}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
