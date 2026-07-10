"""Tests for the per-line audio cache: SHA256(engine, model, voice_id, speed, text) -> WAV.

Cache hits must skip calling the engine entirely, so reruns are cheap and
typo fixes only resynthesize the changed line.
"""

from __future__ import annotations

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.tts.engines.null_engine import NullEngine


class CountingNullEngine(NullEngine):
    """Wraps NullEngine to count how many times synthesize() actually runs."""

    def __init__(self, output_dir):
        super().__init__(output_dir=output_dir)
        self.synthesize_calls = 0

    def synthesize(self, text, voice_role, speed=1.0):
        self.synthesize_calls += 1
        return super().synthesize(text, voice_role, speed)


def make_cache(tmp_path):
    return LineCache(cache_dir=tmp_path / "cache")


def test_cache_miss_calls_engine_and_stores_result(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    result = cache.get_or_synthesize(
        engine, text="Hello there.", voice_role="host", model="null-model", voice_id="v1", speed=1.0
    )

    assert engine.synthesize_calls == 1
    assert result.wav_path.exists()
    assert result.from_cache is False


def test_identical_call_is_a_cache_hit(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)
    result2 = cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)

    assert engine.synthesize_calls == 1  # second call was a cache hit
    assert result2.from_cache is True


def test_changed_text_is_a_cache_miss(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)
    cache.get_or_synthesize(engine, "Hello there!", "host", "null-model", "v1", 1.0)

    assert engine.synthesize_calls == 2


def test_changed_voice_id_is_a_cache_miss(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)
    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v2", 1.0)

    assert engine.synthesize_calls == 2


def test_changed_speed_is_a_cache_miss(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)
    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.2)

    assert engine.synthesize_calls == 2


def test_incidental_whitespace_differences_are_a_cache_hit(tmp_path):
    cache = make_cache(tmp_path)
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")

    cache.get_or_synthesize(engine, "Hello   there.", "host", "null-model", "v1", 1.0)
    cache.get_or_synthesize(engine, "Hello there.", "host", "null-model", "v1", 1.0)

    assert engine.synthesize_calls == 1


def test_cache_persists_across_new_cache_instances(tmp_path):
    engine = CountingNullEngine(output_dir=tmp_path / "engine_out")
    cache_dir = tmp_path / "cache"

    LineCache(cache_dir=cache_dir).get_or_synthesize(
        engine, "Hello there.", "host", "null-model", "v1", 1.0
    )
    result = LineCache(cache_dir=cache_dir).get_or_synthesize(
        engine, "Hello there.", "host", "null-model", "v1", 1.0
    )

    assert engine.synthesize_calls == 1
    assert result.from_cache is True
