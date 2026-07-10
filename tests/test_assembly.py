"""Integration tests for full lesson audio assembly: synth + cache + pauses +
loudness normalization + MP3 export with ID3 tags, driven end-to-end through
NullEngine (no external dependencies, no API keys).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from dorosak_factory.audio.assembly import assemble_lesson_audio
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import AudioConfig, LoudnessConfig, MP3Config, PauseConfig
from dorosak_factory.parser.models import Category, DialogueTurn, Lesson, VocabItem
from dorosak_factory.tts.engines.null_engine import NullEngine


def ffprobe_format(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["format"]


@pytest.fixture
def category():
    return Category(
        number=99,
        title_en="Test Category",
        title_ar="ar",
        level="Beginner",
        source_file="fixture.md",
    )


@pytest.fixture
def lesson():
    return Lesson(
        number=1,
        title_en="A Tiny Test Lesson",
        title_ar="ar",
        scenario="s",
        host_intro="Welcome to the test lesson. Let's begin.",
        turns=(
            DialogueTurn(
                speaker="Tom", raw_speaker_label="Tom", paragraphs=("Hello Priya, how are you today?",)
            ),
            DialogueTurn(
                speaker="Priya", raw_speaker_label="Priya", paragraphs=("I am well, thank you Tom.",)
            ),
            DialogueTurn(
                speaker="Tom",
                raw_speaker_label="Tom",
                paragraphs=("That is good to hear.", "Let's talk about the weather now."),
            ),
        ),
        vocabulary=(VocabItem(term="Well", definition="in good health"),),
        source_file="fixture.md",
        raw_header="## Lesson 1",
    )


@pytest.fixture
def fast_config(tmp_path):
    return AudioConfig(
        pauses=PauseConfig(between_turns_ms=100, after_host_intro_ms=150, between_paragraphs_ms=80),
        loudness=LoudnessConfig(target_lufs=-16.0, true_peak_dbtp=-1.5),
        mp3=MP3Config(bitrate_kbps=128, artist="Dorosak English Podcast"),
        cache_dir=tmp_path / "cache",
        work_dir=tmp_path / "work",
    )


@pytest.fixture
def engine(tmp_path):
    return NullEngine(output_dir=tmp_path / "engine_raw")


@pytest.fixture
def cache(fast_config):
    return LineCache(cache_dir=fast_config.cache_dir)


def test_mp3_output_exists_and_is_playable(tmp_path, category, lesson, engine, cache, fast_config):
    output_mp3 = tmp_path / "episode.mp3"

    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    assert output_mp3.exists()
    fmt = ffprobe_format(output_mp3)
    assert fmt["format_name"] == "mp3"
    assert float(fmt["duration"]) == pytest.approx(result.duration_seconds, abs=0.1)


def test_id3_tags_match_spec(tmp_path, category, lesson, engine, cache, fast_config):
    output_mp3 = tmp_path / "episode.mp3"
    assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    tags = ffprobe_format(output_mp3)["tags"]
    assert tags["title"] == "Cat 99 · Lesson 1 — A Tiny Test Lesson"
    assert tags["album"] == "Test Category"
    assert tags["artist"] == "Dorosak English Podcast"
    assert tags["track"] == "1"


def test_timeline_covers_host_intro_and_every_turn(
    tmp_path, category, lesson, engine, cache, fast_config
):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    # host intro + 3 turns (one turn has 2 paragraphs) = 5 timeline entries
    assert len(result.timeline) == 5
    assert result.timeline[0].speaker == "Host"
    assert result.timeline[0].start_seconds == 0.0
    assert result.timeline[1].speaker == "Tom"
    assert result.timeline[2].speaker == "Priya"
    assert result.timeline[3].speaker == "Tom"
    assert result.timeline[4].speaker == "Tom"


def test_timeline_is_monotonic_with_gaps_for_pauses(
    tmp_path, category, lesson, engine, cache, fast_config
):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    for earlier, later in zip(result.timeline, result.timeline[1:]):
        assert later.start_seconds >= earlier.end_seconds
        assert earlier.end_seconds > earlier.start_seconds


def test_host_intro_gap_matches_configured_pause(tmp_path, category, lesson, engine, cache, fast_config):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    gap = result.timeline[1].start_seconds - result.timeline[0].end_seconds
    assert gap == pytest.approx(0.15, abs=0.02)  # after_host_intro_ms = 150


def test_between_paragraph_gap_matches_configured_pause(
    tmp_path, category, lesson, engine, cache, fast_config
):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    # timeline[3] and timeline[4] are the two paragraphs of Tom's last turn
    gap = result.timeline[4].start_seconds - result.timeline[3].end_seconds
    assert gap == pytest.approx(0.08, abs=0.02)  # between_paragraphs_ms = 80


def test_voice_roles_are_assigned_and_recorded(tmp_path, category, lesson, engine, cache, fast_config):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    assert result.voice_roles["Tom"] == "female_1"
    assert result.voice_roles["Priya"] == "male_1"


def test_characters_synthesized_matches_all_spoken_text(
    tmp_path, category, lesson, engine, cache, fast_config
):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    expected = len(lesson.host_intro) + sum(len(p) for t in lesson.turns for p in t.paragraphs)
    assert result.characters_synthesized == expected


def test_loudness_step_runs_without_crashing_on_null_engine_silence(
    tmp_path, category, lesson, engine, cache, fast_config
):
    output_mp3 = tmp_path / "episode.mp3"
    result = assemble_lesson_audio(category, lesson, engine, cache, fast_config, output_mp3)

    # NullEngine output is pure silence, which cannot be meaningfully
    # amplified to -16 LUFS (there's no signal). The pipeline must still
    # complete and report what it measured, rather than crashing on the
    # out-of-range ffmpeg loudnorm inputs that pure silence produces.
    assert result.pre_normalization_loudness.input_i <= -60.0
    assert output_mp3.exists()


def test_cache_is_reused_on_a_second_assembly_of_the_same_lesson(
    tmp_path, category, lesson, fast_config, cache
):
    class CountingNullEngine(NullEngine):
        def __init__(self, output_dir):
            super().__init__(output_dir=output_dir)
            self.calls = 0

        def synthesize(self, text, voice_role, speed=1.0):
            self.calls += 1
            return super().synthesize(text, voice_role, speed)

    counting_engine = CountingNullEngine(output_dir=tmp_path / "engine_raw")

    assemble_lesson_audio(category, lesson, counting_engine, cache, fast_config, tmp_path / "ep1.mp3")
    first_call_count = counting_engine.calls
    assemble_lesson_audio(category, lesson, counting_engine, cache, fast_config, tmp_path / "ep2.mp3")

    assert first_call_count > 0
    assert counting_engine.calls == first_call_count  # second run was all cache hits
