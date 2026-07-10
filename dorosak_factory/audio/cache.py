"""Per-line audio cache: reuses synthesized WAVs across reruns.

Keyed by SHA256(engine, model, voice_id, speed, normalized_text) per
INSTRUCTIONS.md section 4.4, so a typo fix in one line only resynthesizes
that line, and mixed-engine setups (e.g. a premium voice for `host` only)
work without any special-casing here.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from dorosak_factory.audio.wav_utils import read_wav_duration_seconds
from dorosak_factory.tts.base import SynthesisResult, TTSEngine


def normalize_text(text: str) -> str:
    """Collapses incidental whitespace differences so they don't bust the cache."""
    return " ".join(text.split())


def compute_cache_key(engine: str, model: str, voice_id: str, speed: float, text: str) -> str:
    """SHA256 cache key over (engine, model, voice_id, speed, normalized_text)."""
    raw = f"{engine}|{model}|{voice_id}|{speed}|{normalize_text(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LineCache:
    """Maps (engine, model, voice_id, speed, text) to a cached WAV on disk."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_or_synthesize(
        self,
        engine: TTSEngine,
        text: str,
        voice_role: str,
        model: str,
        voice_id: str,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Returns the cached synthesis result, or synthesizes and caches it on a miss."""
        key = compute_cache_key(engine.name, model, voice_id, speed, text)
        cached_path = self._cache_dir / f"{key}.wav"

        if cached_path.exists():
            return SynthesisResult(
                wav_path=cached_path,
                duration_seconds=read_wav_duration_seconds(cached_path),
                characters=len(text),
                engine=engine.name,
                voice_role=voice_role,
                from_cache=True,
            )

        result = engine.synthesize(text, voice_role=voice_role, speed=speed)
        shutil.copyfile(result.wav_path, cached_path)
        return SynthesisResult(
            wav_path=cached_path,
            duration_seconds=result.duration_seconds,
            characters=result.characters,
            engine=result.engine,
            voice_role=result.voice_role,
            from_cache=False,
        )
