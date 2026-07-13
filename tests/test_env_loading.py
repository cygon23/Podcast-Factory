"""Tests that `.env` is actually loaded into the process before engine
credential checks run - a real gap: no code previously loaded it at all,
so every engine's is_available() saw an empty environment regardless of
what was in .env.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from dorosak_factory.cli import main


def test_run_dry_run_picks_up_env_file_credentials(tmp_path, capsys):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "cat99.md").write_text(
        "# Category 99: T — ت\n## Dorosak English Podcast | Level: Beginner\n"
        "## All 1 Podcast Dialogue Scripts\n\n---\n\n"
        "## Lesson 1: T | ت\n\n**Scenario:** s\n\n**Host Intro:**\nHi.\n\n---\n"
        "**Tom:** Hi.\n\n**Key Vocabulary:**\n- *t* — d\n\n---\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test-from-dotenv\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        exit_code = main(["--base-dir", str(tmp_path), "run", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Engine resolved: openai" in output


def test_missing_env_file_does_not_crash(tmp_path, capsys):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    credential_vars = [
        "OPENAI_API_KEY",
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "ELEVENLABS_API_KEY",
        "KOKORO_MODEL_PATH",
        "KOKORO_CONFIG_PATH",
        "KOKORO_VOICES_DIR",
    ]
    # No .env file at all - should just fall through to normal auto-detection
    # (and fail cleanly with no credentials anywhere, not crash).
    with patch.dict(os.environ, {}, clear=False):
        for var in credential_vars:
            os.environ.pop(var, None)
        exit_code = main(["--base-dir", str(tmp_path), "run", "--dry-run"])

    assert exit_code == 1
