"""NullEngine: a silent, zero-dependency TTS engine used for tests and dry runs.

Generates a real WAV file (silence) whose duration is proportional to the
input text length, so the full pipeline (assembly, subtitles, timing math)
is testable end-to-end with zero external dependencies or API keys.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import write_silence_wav
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine

if TYPE_CHECKING:
    from dorosak_factory.config import Config

_WORDS_PER_MINUTE = 150.0
_MIN_DURATION_SECONDS = 0.3


class NullEngine(TTSEngine):
    """Silent TTS engine: never contacts a real provider, never requires credentials."""

    name = "null"

    def __init__(self, output_dir: Path, words_per_minute: float = _WORDS_PER_MINUTE) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._words_per_minute = words_per_minute

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        return True

    @classmethod
    def availability_hint(cls) -> str:
        return "always available - built-in test engine, no configuration needed"

    @classmethod
    def from_config(cls, config: "Config") -> "NullEngine":
        return cls(output_dir=config.audio.work_dir / "null_engine_raw")

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=True, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        duration = self._estimate_duration(text, speed)
        wav_path = self._path_for(text, voice_role, speed)
        write_silence_wav(wav_path, duration)
        return SynthesisResult(
            wav_path=wav_path,
            duration_seconds=duration,
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    def _estimate_duration(self, text: str, speed: float) -> float:
        word_count = max(len(text.split()), 1)
        duration = (word_count / self._words_per_minute) * 60.0 / speed
        return max(duration, _MIN_DURATION_SECONDS)

    def _path_for(self, text: str, voice_role: str, speed: float) -> Path:
        cache_key = f"{self.name}|{voice_role}|{speed}|{text.strip().lower()}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._output_dir / f"{digest}.wav"
