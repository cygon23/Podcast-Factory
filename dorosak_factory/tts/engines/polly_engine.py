"""Amazon Polly TTS adapter. Requires AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import concat_wavs, read_wav_duration_seconds, write_pcm16_wav
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine
from dorosak_factory.tts.chunking import chunk_text
from dorosak_factory.tts.retry import with_retries

if TYPE_CHECKING:
    from dorosak_factory.config import Config

MAX_CHARS = 2900  # Polly's neural-engine request limit is 3000 characters


class PollyEngine(TTSEngine):
    """Adapter for Amazon Polly (neural voices)."""

    name = "polly"

    DEFAULT_VOICE_MAP = {
        "host": "Matthew",
        "female_1": "Joanna",
        "male_1": "Justin",
        "female_2": "Kendra",
        "male_2": "Stephen",
        "neutral_1": "Salli",
    }

    def __init__(
        self,
        region_name: str,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        import boto3

        self._client = boto3.client(
            "polly",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return bool(env.get("AWS_ACCESS_KEY_ID")) and bool(env.get("AWS_SECRET_ACCESS_KEY"))

    @classmethod
    def availability_hint(cls) -> str:
        return "Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION in .env (AWS IAM console)"

    @classmethod
    def from_config(cls, config: "Config") -> "PollyEngine":
        return cls(
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            work_dir=config.audio.work_dir / "polly_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=False, supports_ssml=True)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        voice_id = self._voice_map.get(voice_role)
        if voice_id is None:
            raise ValueError(
                f"No Polly voice configured for role '{voice_role}'. "
                f"Add it under tts.voice_map.polly in config.yaml."
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
        from botocore.exceptions import ClientError

        def call() -> None:
            ssml = self._build_ssml(text, speed)
            response = self._client.synthesize_speech(
                Text=ssml,
                TextType="ssml",
                OutputFormat="pcm",
                VoiceId=voice_id,
                Engine="neural",
                SampleRate="24000",
            )
            pcm_bytes = response["AudioStream"].read()
            write_pcm16_wav(output_path, pcm_bytes, sample_rate=24000)

        with_retries(call, retryable_exceptions=(ClientError,))

    @staticmethod
    def _build_ssml(text: str, speed: float) -> str:
        rate_percent = round(speed * 100)
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<speak><prosody rate="{rate_percent}%">{escaped}</prosody></speak>'

    def _path_for(self, key_text: str, voice_id: str, speed: float) -> Path:
        cache_key = f"{self.name}|{voice_id}|{speed}|{key_text}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}.wav"
