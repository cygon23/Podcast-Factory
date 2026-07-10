"""Loads config.yaml into typed config objects, with documented defaults.

Only the audio-relevant slice (pauses, loudness, MP3, music) exists so far;
TTS/video/manifest sections are added as later steps need them. Every
default here matches a specific value mandated in INSTRUCTIONS.md section 4.5.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PauseConfig:
    """Silence gaps inserted during audio assembly, in milliseconds."""

    between_turns_ms: int = 700
    after_host_intro_ms: int = 1500
    between_paragraphs_ms: int = 400


@dataclass(frozen=True)
class LoudnessConfig:
    """Target integrated loudness and true peak for the final MP3 mix."""

    target_lufs: float = -16.0
    true_peak_dbtp: float = -1.5


@dataclass(frozen=True)
class MusicConfig:
    """Optional intro/outro music beds. None means no music mixed in."""

    intro_path: Path | None = None
    outro_path: Path | None = None
    intro_fade_in_ms: int = 2000
    intro_fade_out_ms: int = 1500
    intro_duck_db: float = -18.0


@dataclass(frozen=True)
class MP3Config:
    """MP3 export settings and ID3 tag defaults."""

    bitrate_kbps: int = 128
    artist: str = "Dorosak English Podcast"


@dataclass(frozen=True)
class AudioConfig:
    pauses: PauseConfig = field(default_factory=PauseConfig)
    loudness: LoudnessConfig = field(default_factory=LoudnessConfig)
    music: MusicConfig = field(default_factory=MusicConfig)
    mp3: MP3Config = field(default_factory=MP3Config)
    cache_dir: Path = Path("output/cache")
    work_dir: Path = Path("output/work")


@dataclass(frozen=True)
class TTSConfig:
    """TTS engine selection, per-engine voice maps, and pricing (section 4.1/4.2/4.3)."""

    engine: str | None = None  # None -> auto-detection chain
    model: str = "default"
    speed: float = 1.0
    voice_map: dict[str, dict[str, str]] = field(default_factory=dict)
    price_per_char: dict[str, float] = field(default_factory=dict)
    character_role_overrides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoConfig:
    """Video rendering settings shared by 16:9 and 9:16 (section 4.6)."""

    resolutions: tuple[str, ...] = ("16:9", "9:16")
    font_name: str = "Noto Sans Arabic"
    title_card_seconds: float = 6.0
    vocab_seconds_per_item: float = 2.0
    vocab_min_seconds: float = 8.0
    backgrounds_dir: Path = Path("assets/backgrounds")
    default_background: Path = Path("assets/backgrounds/default.png")


@dataclass(frozen=True)
class ManifestConfig:
    """SQLite manifest location (section 4.7)."""

    db_path: Path = Path("output/manifest.sqlite3")


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level run settings: where lessons come from, where output goes, parallelism."""

    input_dir: Path = Path("input")
    output_dir: Path = Path("output")
    concurrency: int = field(default_factory=lambda: min(4, os.cpu_count() or 1))


@dataclass(frozen=True)
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    manifest: ManifestConfig = field(default_factory=ManifestConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


def load_config(path: str | Path | None, base_dir: str | Path) -> Config:
    """Loads config from `path`, applying defaults for anything unspecified.

    `base_dir` anchors relative paths (music files, cache/work dirs). If
    `path` is None, pure defaults are returned. Raises FileNotFoundError if
    `path` is given but does not exist - a missing explicit config file is
    an operator mistake, not a state to silently fall back from.
    """
    base_dir = Path(base_dir)
    raw: dict = {}
    if path is not None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    audio_raw = raw.get("audio", {})

    pauses = PauseConfig(**audio_raw.get("pauses", {}))
    loudness = LoudnessConfig(**audio_raw.get("loudness", {}))
    mp3 = MP3Config(**audio_raw.get("mp3", {}))

    music_raw = dict(audio_raw.get("music", {}))
    for key in ("intro_path", "outro_path"):
        if music_raw.get(key) is not None:
            music_raw[key] = _resolve_path(music_raw[key], base_dir)
    music = MusicConfig(**music_raw)

    cache_dir = _resolve_path(audio_raw.get("cache_dir", "output/cache"), base_dir)
    work_dir = _resolve_path(audio_raw.get("work_dir", "output/work"), base_dir)

    audio = AudioConfig(
        pauses=pauses,
        loudness=loudness,
        music=music,
        mp3=mp3,
        cache_dir=cache_dir,
        work_dir=work_dir,
    )

    tts_raw = raw.get("tts", {})
    tts = TTSConfig(**tts_raw)

    video_raw = dict(raw.get("video", {}))
    if "resolutions" in video_raw:
        video_raw["resolutions"] = tuple(video_raw["resolutions"])
    backgrounds_dir = _resolve_path(video_raw.pop("backgrounds_dir", "assets/backgrounds"), base_dir)
    default_background = _resolve_path(
        video_raw.pop("default_background", backgrounds_dir / "default.png"), base_dir
    )
    video = VideoConfig(
        backgrounds_dir=backgrounds_dir, default_background=default_background, **video_raw
    )

    manifest_raw = dict(raw.get("manifest", {}))
    manifest_raw["db_path"] = _resolve_path(
        manifest_raw.get("db_path", "output/manifest.sqlite3"), base_dir
    )
    manifest = ManifestConfig(**manifest_raw)

    pipeline_raw = dict(raw.get("pipeline", {}))
    pipeline_raw["input_dir"] = _resolve_path(pipeline_raw.get("input_dir", "input"), base_dir)
    pipeline_raw["output_dir"] = _resolve_path(pipeline_raw.get("output_dir", "output"), base_dir)
    if "concurrency" not in pipeline_raw:
        pipeline_raw["concurrency"] = min(4, os.cpu_count() or 1)
    pipeline = PipelineConfig(**pipeline_raw)

    return Config(audio=audio, tts=tts, video=video, manifest=manifest, pipeline=pipeline)


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else base_dir / candidate
