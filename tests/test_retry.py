"""Tests for the shared exponential-backoff retry helper."""

from __future__ import annotations

import pytest

from dorosak_factory.tts.retry import with_retries


class FlakyError(Exception):
    pass


def test_succeeds_on_first_try_without_sleeping():
    sleeps = []
    result = with_retries(lambda: 42, sleep=sleeps.append)
    assert result == 42
    assert sleeps == []


def test_retries_and_eventually_succeeds():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise FlakyError("transient")
        return "ok"

    sleeps = []
    result = with_retries(flaky, max_attempts=3, base_delay_seconds=0.01, sleep=sleeps.append)

    assert result == "ok"
    assert calls["count"] == 3
    assert len(sleeps) == 2  # slept before attempt 2 and attempt 3


def test_backoff_delays_double_each_attempt():
    calls = {"count": 0}

    def always_fails():
        calls["count"] += 1
        raise FlakyError("nope")

    sleeps = []
    with pytest.raises(FlakyError):
        with_retries(always_fails, max_attempts=4, base_delay_seconds=1.0, sleep=sleeps.append)

    assert sleeps == [1.0, 2.0, 4.0]


def test_exhausts_attempts_and_reraises():
    def always_fails():
        raise FlakyError("permanent")

    with pytest.raises(FlakyError, match="permanent"):
        with_retries(always_fails, max_attempts=2, base_delay_seconds=0.01, sleep=lambda s: None)


def test_only_retries_specified_exception_types():
    def raises_value_error():
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        with_retries(
            raises_value_error, max_attempts=3, retryable_exceptions=(FlakyError,), sleep=lambda s: None
        )
