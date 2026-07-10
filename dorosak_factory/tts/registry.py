"""TTS engine registry: explicit selection plus the auto-detection priority chain.

Auto-detection order (section 4.3): kokoro -> azure -> openai -> google -> polly
-> elevenlabs. `NullEngine` is registered for explicit use (tests, dry runs) but
deliberately excluded from the auto chain so it is never picked silently in a
real run.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from dorosak_factory.tts.base import TTSEngine

DEFAULT_ENGINE_PRIORITY: tuple[str, ...] = (
    "kokoro",
    "azure",
    "openai",
    "google",
    "polly",
    "elevenlabs",
)


class EngineResolutionError(Exception):
    """Raised when an explicit engine name is unknown or no engine is available."""


class Registry:
    """Holds registered TTS engine classes and resolves which one to use."""

    def __init__(self, priority: tuple[str, ...] | list[str] = DEFAULT_ENGINE_PRIORITY) -> None:
        self._engines: dict[str, type[TTSEngine]] = {}
        self._priority: tuple[str, ...] = tuple(priority)

    def register(self, engine_cls: type[TTSEngine]) -> type[TTSEngine]:
        """Registers an engine class under its `name`. Usable as a decorator."""
        self._engines[engine_cls.name] = engine_cls
        return engine_cls

    def get(self, name: str) -> type[TTSEngine]:
        try:
            return self._engines[name]
        except KeyError as exc:
            raise EngineResolutionError(
                f"Unknown engine '{name}'. Registered engines: {sorted(self._engines)}"
            ) from exc

    def resolve_engine_class(
        self,
        explicit: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> type[TTSEngine]:
        """Resolves the engine class to use.

        If `explicit` is given, it must be a registered engine name. Otherwise,
        walks the priority chain and returns the first engine whose
        `is_available(env)` returns True.
        """
        if explicit is not None:
            return self.get(explicit)

        resolved_env = env if env is not None else os.environ
        for engine_name in self._priority:
            engine_cls = self._engines.get(engine_name)
            if engine_cls is None:
                continue
            if engine_cls.is_available(resolved_env):
                return engine_cls

        hints = [
            f"- {engine_name}: {self._engines[engine_name].availability_hint()}"
            for engine_name in self._priority
            if engine_name in self._engines
        ]
        hint_text = "\n".join(hints) if hints else "no engines are registered"
        raise EngineResolutionError(
            "No TTS engine available. Configure one of the following:\n" + hint_text
        )


default_registry = Registry()


def register(engine_cls: type[TTSEngine]) -> type[TTSEngine]:
    """Registers an engine class in the module-level default registry."""
    return default_registry.register(engine_cls)


def resolve_engine_class(
    explicit: str | None = None, env: Mapping[str, str] | None = None
) -> type[TTSEngine]:
    """Resolves an engine class using the module-level default registry."""
    return default_registry.resolve_engine_class(explicit=explicit, env=env)
