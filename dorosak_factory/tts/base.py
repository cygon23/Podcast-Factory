"""Abstract TTS engine interface. Every provider adapter implements this contract.

Voice roles are abstract (`host`, `female_1`, `male_1`, ...) - provider-specific
voice IDs are resolved from config inside each adapter, never in lesson logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dorosak_factory.config import Config


@dataclass(frozen=True)
class Capabilities:
    """What an engine can do, so callers can adapt (e.g. skip SSML if unsupported)."""

    supports_speed: bool
    supports_ssml: bool


@dataclass(frozen=True)
class SynthesisResult:
    """Output of one `synthesize` call: a 24kHz mono WAV plus usage metadata."""

    wav_path: Path
    duration_seconds: float
    characters: int
    engine: str
    voice_role: str
    from_cache: bool = False


class TTSEngine(ABC):
    """Abstract interface every TTS provider adapter must implement.

    Output is always normalized to 24kHz mono WAV so downstream audio assembly
    is provider-agnostic.
    """

    name: str

    @classmethod
    @abstractmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        """Whether this engine can actually be used right now (keys/model/package present)."""

    @classmethod
    @abstractmethod
    def from_config(cls, config: "Config") -> "TTSEngine":
        """Builds an instance from the loaded Config - the CLI's one uniform instantiation path."""

    @classmethod
    def availability_hint(cls) -> str:
        """Human-readable instructions for making this engine available, for error messages."""
        return f"no availability hint provided for engine '{cls.name}'"

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Declares supported features (speed control, SSML, ...)."""

    @abstractmethod
    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        """Synthesizes `text` spoken as `voice_role` and returns the resulting WAV + metadata."""
