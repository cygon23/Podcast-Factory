"""Custom exceptions shared across the pipeline, so failures are precise and actionable."""

from __future__ import annotations


class DorosakError(Exception):
    """Base class for all Dorosak Factory errors."""


class FFmpegError(DorosakError):
    """Raised when an ffmpeg/ffprobe subprocess invocation fails."""


class MissingAssetError(DorosakError):
    """Raised when a configured operator-supplied asset (music, font, image) is missing."""
