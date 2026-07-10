"""Google Cloud Text-to-Speech adapter. Requires GOOGLE_APPLICATION_CREDENTIALS."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import concat_wavs, read_wav_duration_seconds
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine
from dorosak_factory.tts.chunking import chunk_text
from dorosak_factory.tts.retry import with_retries

if TYPE_CHECKING:
    from dorosak_factory.config import Config

MAX_CHARS = 4900  # Google TTS's 5000-byte request limit, with headroom for multi-byte chars


class GoogleEngine(TTSEngine):
    """Adapter for Google Cloud Text-to-Speech (Neural2 voices)."""

    name = "google"

    DEFAULT_VOICE_MAP = {
        "host": "en-US-Neural2-D",
        "female_1": "en-US-Neural2-F",
        "male_1": "en-US-Neural2-A",
        "female_2": "en-US-Neural2-C",
        "male_2": "en-US-Neural2-I",
        "neutral_1": "en-US-Neural2-H",
    }

    def __init__(self, work_dir: Path, voice_map: dict[str, str] | None = None) -> None:
        from google.cloud import texttospeech

        self._client = texttospeech.TextToSpeechClient()
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        creds_path = env.get("GOOGLE_APPLICATION_CREDENTIALS")
        return bool(creds_path) and Path(creds_path).exists()

    @classmethod
    def availability_hint(cls) -> str:
        return (
            "Set GOOGLE_APPLICATION_CREDENTIALS in .env to a service-account "
            "JSON key path (Google Cloud Console > IAM > Service Accounts)"
        )

    @classmethod
    def from_config(cls, config: "Config") -> "GoogleEngine":
        return cls(
            work_dir=config.audio.work_dir / "google_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=True)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No Google voice configured for role '{voice_role}'. "
                f"Add it under tts.voice_map.google in config.yaml."
            )

        chunks = chunk_text(text, MAX_CHARS) or [text]
        chunk_paths = []
        for index, chunk in enumerate(chunks):
            chunk_path = self._path_for(f"{text}|{index}", voice_id, speed)
            self._synthesize_chunk(chunk, voice_id, speed, chunk_path)
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

    def _synthesize_chunk(self, text: str, voice_id: str, speed: float, output_path: Path) -> None:
        from google.api_core.exceptions import GoogleAPIError
        from google.cloud import texttospeech

        def call() -> None:
            response = self._client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_id),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                    sample_rate_hertz=24000,
                    speaking_rate=speed,
                ),
            )
            # LINEAR16 responses from Google TTS include a WAV header, so the
            # raw bytes are already a valid WAV file.
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.audio_content)

        with_retries(call, retryable_exceptions=(GoogleAPIError,))

    def _path_for(self, key_text: str, voice_id: str, speed: float) -> Path:
        cache_key = f"{self.name}|{voice_id}|{speed}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
