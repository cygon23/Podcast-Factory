"""Video renderer adapters. Importing this package registers all built-in renderers.

Mirrors tts/engines/__init__.py's pattern: a future local avatar renderer or
cloud API renderer only needs its own adapter module plus one registration
line here - nothing else in the pipeline changes.
"""

from dorosak_factory.video.renderer_registry import default_registry
from dorosak_factory.video.renderers.static_background_renderer import StaticBackgroundRenderer

default_registry.register(StaticBackgroundRenderer)

__all__ = [
    "StaticBackgroundRenderer",
]
