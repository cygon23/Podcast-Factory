"""Video renderer registry: explicit selection plus the auto-detection priority chain.

Mirrors tts/registry.py exactly. Auto-detection order prefers a local avatar
renderer over the static-background fallback once one is registered and
available; `static_background` is always available so the chain never fails.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from dorosak_factory.video.renderer_base import VideoRenderer

DEFAULT_RENDERER_PRIORITY: tuple[str, ...] = (
    "local_avatar",
    "static_background",
)


class RendererResolutionError(Exception):
    """Raised when an explicit renderer name is unknown or no renderer is available."""


class Registry:
    """Holds registered video renderer classes and resolves which one to use."""

    def __init__(self, priority: tuple[str, ...] | list[str] = DEFAULT_RENDERER_PRIORITY) -> None:
        self._renderers: dict[str, type[VideoRenderer]] = {}
        self._priority: tuple[str, ...] = tuple(priority)

    def register(self, renderer_cls: type[VideoRenderer]) -> type[VideoRenderer]:
        """Registers a renderer class under its `name`. Usable as a decorator."""
        self._renderers[renderer_cls.name] = renderer_cls
        return renderer_cls

    def get(self, name: str) -> type[VideoRenderer]:
        try:
            return self._renderers[name]
        except KeyError as exc:
            raise RendererResolutionError(
                f"Unknown renderer '{name}'. Registered renderers: {sorted(self._renderers)}"
            ) from exc

    def resolve_renderer_class(
        self,
        explicit: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> type[VideoRenderer]:
        """Resolves the renderer class to use.

        If `explicit` is given, it must be a registered renderer name. Otherwise,
        walks the priority chain and returns the first renderer whose
        `is_available(env)` returns True.
        """
        if explicit is not None:
            return self.get(explicit)

        resolved_env = env if env is not None else os.environ
        for renderer_name in self._priority:
            renderer_cls = self._renderers.get(renderer_name)
            if renderer_cls is None:
                continue
            if renderer_cls.is_available(resolved_env):
                return renderer_cls

        hints = [
            f"- {renderer_name}: {self._renderers[renderer_name].availability_hint()}"
            for renderer_name in self._priority
            if renderer_name in self._renderers
        ]
        hint_text = "\n".join(hints) if hints else "no renderers are registered"
        raise RendererResolutionError(
            "No video renderer available. Configure one of the following:\n" + hint_text
        )


default_registry = Registry()


def register(renderer_cls: type[VideoRenderer]) -> type[VideoRenderer]:
    """Registers a renderer class in the module-level default registry."""
    return default_registry.register(renderer_cls)


def resolve_renderer_class(
    explicit: str | None = None, env: Mapping[str, str] | None = None
) -> type[VideoRenderer]:
    """Resolves a renderer class using the module-level default registry."""
    return default_registry.resolve_renderer_class(explicit=explicit, env=env)
