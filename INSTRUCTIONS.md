# Dorosak Podcast Factory — Build Instructions for Claude Code

You are building a production system, not a demo. Read this entire document before writing any code. At the end you must self-evaluate against the Acceptance Criteria section and report honestly what passes, what fails, and what is untested.

---

## 1. Project goal (the "why")

Dorosak (dorosak.com) is an English-learning platform. We have ~1,200 podcast lesson scripts stored as Markdown files (50 lessons per category file). The goal is a **fully automated pipeline** that converts every Markdown lesson into:

1. An **audio podcast episode (MP3)** — multi-voice dialogue with distinct AI voices per character, natural pauses, intro/outro music, normalized loudness, embedded metadata.
2. A **video podcast episode (MP4)** — in BOTH 16:9 (1920x1080, YouTube) and 9:16 (1080x1920, Shorts/Reels) formats, with a branded background, episode title (English + Arabic), episode number, burned-in English subtitles, and a Key Vocabulary text screen at the end.
3. A standalone **.srt subtitle file** and a **metadata JSON** per episode.

The end state: the operator drops new Markdown files into an input folder, runs ONE command, and only the new/changed lessons are processed. The system must scale gracefully from 50 lessons to 10,000+ with no code changes.

## 2. Division of responsibilities — critical

**You (Claude Code) deliver LOGIC ONLY.** You must NOT attempt to:

- Download AI models or model weights
- Create, guess, or hardcode any API keys
- Sign up for services, deploy, or host anything
- Fabricate audio/video output when a dependency is missing

**The operator (human) will handle:** downloading the Kokoro model, adding API keys to `.env`, supplying assets (music, background images, fonts), installing FFmpeg, renting cloud machines, uploading outputs to dorosak.com, and final listening/watching quality review.

Whenever your code needs something the operator must provide, the code must **fail loudly with a precise, actionable message** (e.g., "Missing asset: assets/music/intro.mp3 — see ASSETS.md section 2") — never silently skip, never generate placeholder audio. Additionally, produce a file `OPERATOR_TODO.md` listing every manual step the operator must complete before the first run, in order, with links/names of what to obtain (names only — do not invent URLs you are not certain of).

## 3. Input format (parse this exactly — do not assume, verify against samples)

Two real sample files are provided in `input/`. Their structure:

```
# Category 31: English for Science & Technology — الإنجليزية للعلوم والتكنولوجيا
## Dorosak English Podcast | Level: Beginner & Intermediate
## All 50 Podcast Dialogue Scripts
---
## Lesson 1: Talking About Science in Daily Life | الحديث عن العلوم في الحياة اليومية

**Scenario:** One-line description.

**Host Intro:**
Paragraph spoken by the Host voice.
---
**Priya:** dialogue line...
**Tom:** dialogue line...
(speaker lines continue; some speakers have parenthetical names like "Student 1 (Emma):";
some turns contain multiple paragraphs)

**Key Vocabulary:**
- *Term* — definition
- *Term* — definition
---
(next lesson)
```

Parsing requirements:

- Extract per file: category number, category English title, category Arabic title, level.
- Extract per lesson: lesson number, English title, Arabic title, scenario, host intro text, ordered list of (speaker_name, text) dialogue turns, vocabulary list of (term, definition).
- Handle edge cases you will find in the real files: multi-paragraph turns, speakers named like `Student 1 (Emma)` (use "Emma" as display name), bold/italic markdown inside dialogue (strip formatting for TTS, keep plain text), `---` separators, possible trailing whitespace. Build the parser against the REAL sample files and write unit tests that parse them and assert lesson counts (50 each) and spot-check known lessons.
- The parser must be tolerant: if a lesson fails to parse, log it to a `parse_errors` report with file + lesson header and continue with the rest. Never crash the whole run for one bad lesson.
- **Key Vocabulary is NOT spoken.** It is rendered as a text screen appended to the end of the video only.

## 4. Architecture (mandatory design)

Language: **Python 3.11+**, typed (type hints everywhere), modular package layout, no provider-specific code outside adapters. Suggested layout:

```
dorosak_factory/
  cli.py                  # single entry point
  config.py               # loads config.yaml + .env, validates
  parser/                 # markdown -> Lesson dataclasses
  tts/
    base.py               # TTSEngine abstract interface
    registry.py           # engine discovery + auto-detection chain
    engines/
      kokoro_engine.py    # local, $0
      openai_engine.py
      azure_engine.py
      google_engine.py
      polly_engine.py
      elevenlabs_engine.py
  audio/                  # per-line cache, stitching, pauses, music, loudness, mp3+ID3
  video/                  # ffmpeg command builders: 16:9, 9:16, subtitles, vocab card
  subtitles/              # SRT/ASS generation from known per-line timings
  manifest/               # SQLite state: lesson hash -> outputs, skip logic
  validate/               # per-episode + per-run self-checks
  report/                 # run summary: counts, durations, estimated cost, failures
tests/
assets/                   # operator-supplied (documented in ASSETS.md)
input/                    # markdown files
output/
```

### 4.1 TTS adapter contract

One abstract interface, roughly: `synthesize(text: str, voice_role: str, speed: float) -> SynthesisResult(wav_path, duration_seconds)`. Every adapter must:

- Normalize output to a single internal format: **24kHz mono WAV**.
- Own its provider's chunking limits, retries with exponential backoff, and rate limiting.
- Declare capabilities (speed control, ssml) via a simple capabilities object.
- Track usage: characters synthesized, and estimated cost using a per-engine price table in config (so prices are editable without code changes).

### 4.2 Voice roles (never provider voice names in lesson logic)

Abstract roles: `host`, `female_1`, `male_1`, `female_2`, `male_2`, `neutral_1`. Each engine adapter has a mapping table role → provider voice ID, defined in `config.yaml`. Character-to-role assignment: automatic and deterministic — the Host maps to `host`; other speakers are assigned roles in order of first appearance, alternating female/male, with a config override file allowing manual per-lesson or per-character pinning. The same character name within one lesson must always get the same voice. Log the final character→role→voice mapping into each episode's metadata JSON.

### 4.3 Engine auto-detection chain (the flexibility requirement)

At startup, unless `--engine X` is passed, resolve the engine in this priority order, checking real availability:

1. **kokoro** — if the package is importable AND model files exist at the configured path (detect GPU via torch.cuda/mps if present; fall back to CPU automatically and log which device is used).
2. **azure** — if `AZURE_SPEECH_KEY` + region are set in env.
3. **openai** — if `OPENAI_API_KEY` is set.
4. **google / polly / elevenlabs** — if their credentials are set.
5. Otherwise: exit with a clear message listing exactly what to configure.

Switching providers must require ONLY: adding a key to `.env` and/or one line in `config.yaml`. Verify this is true in your self-evaluation. The design must make adding a brand-new future provider = writing one adapter file + one config block, touching nothing else.

### 4.4 Per-line audio cache

Cache each synthesized line as a WAV keyed by SHA256 of `(engine, model, voice_id, speed, normalized_text)`. On rerun, cached lines are reused. This makes typo fixes cheap and mixed-engine setups possible (e.g., premium voice for `host` only — support per-role engine override in config).

### 4.5 Audio assembly (FFmpeg / pydub — FFmpeg must do the heavy lifting)

- Silence gaps: configurable; defaults — 700ms between speaker turns, 1500ms after host intro, 400ms between paragraphs within one turn.
- Music: `assets/music/` bed(s); intro music fades in, ducks under host intro (sidechain-style volume reduction is acceptable via ffmpeg volume automation), fades out; outro sting at the end. All timings configurable.
- Loudness: normalize final mix to **-16 LUFS integrated** (ffmpeg loudnorm, two-pass), true peak ≤ -1.5 dBTP.
- Export MP3 128kbps (configurable) with ID3 tags: title "Cat {N} · Lesson {M} — {English title}", album = category title, track number = lesson number, artist "Dorosak English Podcast", cover art from assets.

### 4.6 Video assembly (pure FFmpeg — do NOT use MoviePy)

- Inputs: episode MP3, background template image per category (fallback to a global default), fonts from `assets/fonts/`.
- 16:9 and 9:16 rendered from the same audio; text layout parameters per format live in config, not hardcoded.
- On-screen: category + lesson number, English title, Arabic title (ensure the chosen ffmpeg drawtext/subtitles path renders Arabic RTL correctly — use libass with a font that has Arabic glyphs; document the font requirement in ASSETS.md; test with real Arabic strings).
- Subtitles: generated from known per-line durations (start time = running offset incl. pauses) — NO speech-to-text anywhere. Burned in via libass (.ass for styling: speaker name prefix in a distinct color) AND exported as plain .srt.
- Vocabulary end card: after the dialogue ends, hold N seconds (config; default 2s per vocab item, min 8s) showing the Key Vocabulary list as styled text over the background, with gentle outro music underneath.
- Target: H.264, yuv420p, AAC audio, faststart. A 6-minute episode must render in minutes, not tens of minutes.

### 4.7 Manifest & idempotent reruns

SQLite (or JSON if you justify it) storing per lesson: content hash, engine used, output paths, validation status, timestamps. The main command scans `input/`, diffs against the manifest, and processes only new/changed/failed lessons. Flags: `--force` (rebuild all), `--only cat31:5` (one lesson), `--only cat31` (one category), `--formats audio|video|both`, `--dry-run` (print the full plan: lessons to process, engine resolved, estimated characters and cost — synthesize nothing).
Parallelism: process N lessons concurrently (config, default = min(4, cpu_count)); cloud engines additionally respect per-provider rate limits. Must be safe to Ctrl+C and resume.

### 4.8 CLI (single command UX)

`python -m dorosak_factory run` does everything with sane defaults. Also: `status` (manifest summary), `validate` (re-run checks on existing outputs), `cost-report`. Rich, readable console output with a progress bar; full logs to `output/logs/run_{timestamp}.log`.

## 5. Validation & self-evaluation (anti-hallucination discipline)

After EACH episode, programmatically verify and record:

- MP3 exists, duration > 30s, and duration ≈ sum(line durations + pauses + music tails) within ±3s.
- Every dialogue turn appears in the SRT; SRT timestamps monotonic; last subtitle end ≤ audio duration.
- Both MP4s exist, are playable (ffprobe returns valid streams), video duration ≈ audio duration + vocab card duration ±2s, correct resolutions.
- Integrated loudness within -16 ±1.5 LUFS (read back with ffmpeg loudnorm print).
- Metadata JSON present and complete.
  An episode failing any check is marked FAILED in the manifest with the reason, and the run report lists it. The run report also totals: lessons processed/skipped/failed, wall time, characters synthesized, estimated cost by engine.

**Your final self-evaluation (mandatory, in `SELF_EVALUATION.md`):** go through every numbered requirement in this document and mark it ✅ implemented + where, ⚠️ partially (why), or ❌ not done (why). Explicitly state what you could NOT test in this environment (e.g., real Azure calls without a key) and how the operator can test it. Do not claim anything works that you have not executed. If a requirement was ambiguous, state the interpretation you chose.

## 6. Testing requirements

- Unit tests: parser (against the two real sample files), voice-role assignment determinism, subtitle timing math, manifest diff logic, engine auto-detection resolution (mock env vars), cost calculation.
- Integration test: a tiny fixture markdown with 2 mini-lessons run end-to-end using a **NullEngine** (built-in test engine that generates silent WAV of length proportional to text — exists precisely so the full pipeline is testable with zero external dependencies). If FFmpeg is available in your environment, actually run it and validate outputs; if not, say so in SELF_EVALUATION.md.
- All tests runnable via `pytest`, and a `make test` / script equivalent.

## 7. Documentation deliverables

- `README.md` — what it is, quickstart (5 steps max), architecture diagram (mermaid), how reruns work, how to add a new lesson file, how to switch engines, how to add a NEW engine adapter (step-by-step with a code skeleton).
- `ASSETS.md` — exact list of what the operator must place in `assets/` (music files and expected names, background images with exact resolutions per category naming convention `assets/backgrounds/cat{N}.png` + `default.png`, fonts including an Arabic-capable font, cover art size).
- `OPERATOR_TODO.md` — ordered manual steps: install FFmpeg, download Kokoro model (name the model: hexgrad/Kokoro-82M on Hugging Face), create `.env` from `.env.example`, obtain keys (name each provider's console, don't fabricate URLs), place assets, run the dry-run, run 1 lesson, run all.
- `config.example.yaml` + `.env.example` fully commented.
- Docstrings on every public function; no dead code; no TODO-comments left for core requirements.

## 8. Quality bar

Clean, presentable, professional: consistent formatting (black/ruff), meaningful names, small focused modules, custom exceptions, structured logging, no bare `except`, no hardcoded paths (everything via config), graceful degradation with actionable errors. Assume this repo will be maintained for years and read by other engineers.

## 9. Order of work (follow this)

1. Data models + parser + parser tests (prove on the two real files).
2. TTS base interface + NullEngine + registry/auto-detection + tests.
3. Audio cache + assembly + loudness + MP3 metadata.
4. Subtitles from timings.
5. Video (16:9 first, then 9:16, then vocab card, then Arabic text verification).
6. Manifest + CLI + parallelism + dry-run.
7. Real engine adapters: kokoro, openai, azure (then google/polly/elevenlabs as thin variants).
8. Validation layer + reports.
9. Docs + SELF_EVALUATION.md.

Begin with step 1. After each step, run its tests before moving on. If any instruction here conflicts with reality you discover in the sample files, trust the files and document the deviation.
