"""TTS engine adapters. Importing this package registers all built-in engines.

Every adapter module only imports its provider SDK lazily (inside methods,
not at module scope), so this import always succeeds even if an operator
hasn't installed every cloud SDK - only the one(s) for their chosen engine.
"""

from dorosak_factory.tts.engines.azure_engine import AzureEngine
from dorosak_factory.tts.engines.elevenlabs_engine import ElevenLabsEngine
from dorosak_factory.tts.engines.google_engine import GoogleEngine
from dorosak_factory.tts.engines.kokoro_engine import KokoroEngine
from dorosak_factory.tts.engines.null_engine import NullEngine
from dorosak_factory.tts.engines.openai_engine import OpenAIEngine
from dorosak_factory.tts.engines.piper_engine import PiperEngine
from dorosak_factory.tts.engines.polly_engine import PollyEngine
from dorosak_factory.tts.registry import default_registry

default_registry.register(NullEngine)
default_registry.register(KokoroEngine)
default_registry.register(AzureEngine)
default_registry.register(OpenAIEngine)
default_registry.register(GoogleEngine)
default_registry.register(PollyEngine)
default_registry.register(ElevenLabsEngine)
default_registry.register(PiperEngine)

__all__ = [
    "NullEngine",
    "KokoroEngine",
    "AzureEngine",
    "OpenAIEngine",
    "GoogleEngine",
    "PollyEngine",
    "ElevenLabsEngine",
    "PiperEngine",
]
