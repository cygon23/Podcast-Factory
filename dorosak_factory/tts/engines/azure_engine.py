"""Azure Cognitive Services Speech TTS adapter. Requires AZURE_SPEECH_KEY + AZURE_SPEECH_REGION."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import concat_wavs, read_wav_duration_seconds, write_pcm16_wav
from dorosak_factory.exceptions import DorosakError
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine
from dorosak_factory.tts.chunking import chunk_text
from dorosak_factory.tts.retry import with_retries

if TYPE_CHECKING:
    from dorosak_factory.config import Config

MAX_CHARS = 5000  # conservative limit for plain-text (non-SSML) Azure synthesis


class AzureSynthesisError(DorosakError):
    """Raised when Azure Speech synthesis is canceled/fails."""


class AzureEngine(TTSEngine):
    """Adapter for Azure Cognitive Services Speech (neural voices)."""

    name = "azure"

    DEFAULT_VOICE_MAP = {
        "host": "en-US-GuyNeural",
        "female_1": "en-US-JennyNeural",
        "male_1": "en-US-DavisNeural",
        "female_2": "en-US-AriaNeural",
        "male_2": "en-US-TonyNeural",
        "neutral_1": "en-US-NancyNeural",
    }

    def __init__(
        self,
        subscription_key: str,
        region: str,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
    ) -> None:
        self._subscription_key = subscription_key
        self._region = region
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return bool(env.get("AZURE_SPEECH_KEY")) and bool(env.get("AZURE_SPEECH_REGION"))

    @classmethod
    def availability_hint(cls) -> str:
        return "Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env (Azure Portal > Speech resource)"

    @classmethod
    def from_config(cls, config: "Config") -> "AzureEngine":
        return cls(
            subscription_key=os.environ["AZURE_SPEECH_KEY"],
            region=os.environ["AZURE_SPEECH_REGION"],
            work_dir=config.audio.work_dir / "azure_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=True)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:

        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No Azure voice configured for role '{voice_role}'. "
                f"Add it under tts.voice_map.azure in config.yaml."
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
        import azure.cognitiveservices.speech as speechsdk

        def call() -> None:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._subscription_key, region=self._region
            )
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
            )
            speech_config.speech_synthesis_voice_name = voice_id
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

            ssml = self._build_ssml(text, voice_id, speed)
            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                write_pcm16_wav(output_path, result.audio_data, sample_rate=24000)
                return
            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                raise AzureSynthesisError(
                    f"Azure synthesis canceled: {details.reason} - {details.error_details}"
                )
            raise AzureSynthesisError(f"Unexpected Azure synthesis result reason: {result.reason}")

        with_retries(call, retryable_exceptions=(AzureSynthesisError,))

    @staticmethod
    def _build_ssml(text: str, voice_id: str, speed: float) -> str:
        rate_percent = round((speed - 1.0) * 100)
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{voice_id}"><prosody rate="{rate_percent:+d}%">{escaped}</prosody></voice>'
            "</speak>"
        )

    def _path_for(self, key_text: str, voice_id: str, speed: float) -> Path:
        cache_key = f"{self.name}|{voice_id}|{speed}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
