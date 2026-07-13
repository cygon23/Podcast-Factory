# Self-Evaluation

Honest status against every numbered requirement in `INSTRUCTIONS.md`. Legend:
✅ implemented + verified running · ⚠️ partial (gap explained) · ❌ not done.

Nothing below is claimed as "working" unless I actually ran it in this
environment and observed the result (ffprobe output, pytest output, or a
rendered frame I inspected). Where I could not test something for real
(no API keys, no real Kokoro weights), I say so explicitly and how the
operator can test it.

## 1. Project goal

Not independently testable — it's the "why." The pipeline described in 2-9
below implements it.

## 2. Division of responsibilities

- ✅ No AI models downloaded. I did `pip install kokoro` (the pure-Python
  package) to read its real API and write a correct adapter against it, but
  never downloaded the ~82M parameter weights (hexgrad/Kokoro-82M) — that's
  the operator's job per `OPERATOR_TODO.md`.
- ✅ No API keys created, guessed, or hardcoded anywhere.
- ✅ No sign-ups, deployments, or hosting attempted.
- ✅ No fabricated audio/video: `MissingAssetError` is raised (not a silent
  skip) for missing backgrounds, missing configured music, missing cover
  art. `NullEngine` (silent test audio) is registered but deliberately
  excluded from the auto-detection chain (`test_null_engine_is_never_auto_selected`)
  so a real run can never silently fall back to silence.
- ✅ `OPERATOR_TODO.md` produced, ordered, names Kokoro's real HF repo
  (hexgrad/Kokoro-82M) and each provider's console by name — no invented URLs.

## 3. Input format parsing

✅ Fully implemented and verified against both real sample files: all 100
lessons across both files parse with **zero** parse errors
(`test_no_parse_errors_on_real_files`, and a separate full-corpus sweep I
ran manually for stray markdown artifacts). Edge cases handled and tested:
multi-paragraph turns, `Student 1 (Emma)` → `Emma`, `Daughter (Emma, 16)` →
`Emma`, inline stage directions (`*sympathetically*`) removed per your
explicit instruction (see conversation — I asked before deciding this,
since it was genuinely ambiguous). Tolerant parsing (one bad lesson logs to
`parse_errors` and the rest of the file still parses) is tested with a
deliberately malformed fixture, not just claimed.

## 4. Architecture

### 4.1 TTS adapter contract
✅ `SynthesisResult(wav_path, duration_seconds, characters, engine, voice_role, from_cache)`,
all engines normalize to 24kHz mono WAV (verified via `wave`/ffprobe in
every engine's tests). Retries with exponential backoff: real, tested
(`tts/retry.py` + per-engine "recovers after transient error" tests, not
just present but exercised). Chunking: real, tested against provider
character limits (`tts/chunking.py`, splits at sentence boundaries, never
truncates). Capabilities object: present on every engine. Cost tracking:
characters are tracked end-to-end (`SynthesisResult.characters` →
`AssemblyResult.characters_synthesized` → manifest → `report.run_report`);
the price table lives in `config.tts.price_per_char` and is applied
centrally in `--dry-run` and `cost-report`, not inside each adapter — a
reasonable reading of "editable without code changes," but worth knowing
if you expected per-adapter cost math.

### 4.2 Voice roles
✅ `tts/voice_roles.py`: Host Intro always `host`; other characters
assigned deterministically in order of first appearance, alternating
female/male, verified with the real data's maximum of 5 distinct non-host
speakers in one lesson (exactly matching the 5 non-host roles). Manual
override via `config.tts.character_role_overrides`. One interpretation I
made without asking (lower-stakes than the stage-direction one): a
character explicitly labeled "Host" in dialogue (e.g. `Host (Emma):`, seen
in the real files) maps directly to the `host` role rather than the
alternating sequence — documented in `tts/voice_roles.py`'s docstring.
Logged into metadata JSON per episode: ✅ (`voice_roles` key).

### 4.3 Engine auto-detection chain
✅ Exact priority order implemented and tested with all 6 real engines
registered (`test_registry_all_engines.py`): kokoro → azure → openai →
google → polly → elevenlabs, explicit `--engine` bypasses the chain, clear
actionable error listing what to configure when nothing is available.
Kokoro's GPU/MPS/CPU detection is real code exercised in this sandbox
(confirmed falls back to `cpu`, since no CUDA/MPS here) — logged via
`logging`, not print. "Switching providers requires only .env/config.yaml"
is verified by the CLI tests using `--engine null` vs relying on
auto-detection — no code path differs. Adding a 7th provider: the pattern
is proven by 6 independent implementations of the exact same interface with
zero special-casing in `registry.py`/`pipeline.py`/`cli.py`; I did not
literally add a 7th to prove it, but README's step-by-step + code skeleton
reflects exactly what the 6 existing adapters do.

**Bug found and fixed after initial delivery**: while writing the detailed
Kokoro download instructions for `docs/OPERATOR_TODO.md`, I inspected
kokoro's actual pipeline source (`KPipeline.load_single_voice`) and found
that passing a bare voice name (e.g. `"af_bella"`) makes kokoro call
`hf_hub_download` — a real network fetch to Hugging Face — unless the
string already ends in `.pt`. My original adapter passed bare names, which
would have silently violated this project's "never download anything at
run time" rule the first time a new voice was used. Fixed by resolving
every voice role to a full local path (`KOKORO_VOICES_DIR/{voice}.pt`)
before calling the pipeline, and raising a clear error instead of
proceeding if that file doesn't exist locally. Added
`KOKORO_VOICES_DIR` as a required third environment variable (alongside
`KOKORO_MODEL_PATH`/`KOKORO_CONFIG_PATH`) and two new tests
(`test_synthesize_resolves_voice_to_a_local_pt_path_not_a_bare_name`,
`test_synthesize_missing_voice_file_raises_clear_error_instead_of_downloading`)
that would have caught this. I did not catch this during the original
build; I'm recording it here rather than quietly fixing it.

### 4.4 Per-line audio cache
✅ SHA256(engine, model, voice_id, speed, normalized_text) → WAV, tested
for hits/misses/cross-instance persistence (`tests/test_audio_cache.py`).
⚠️ **Gap**: "support per-role engine override in config" (e.g. premium
voice for `host` only, free engine for everyone else) is **not**
implemented — `assemble_lesson_audio` takes one engine for the whole
lesson. Mixed-engine-per-role would require passing an engine-per-role map
through `pipeline.process_lesson`; the cache key already includes `engine`
so the caching mechanism itself would support it, but the wiring doesn't
exist yet.

### 4.5 Audio assembly
✅ Pause timings configurable and match the mandated defaults exactly
(700/1500/400ms — asserted in tests, not just set). Music: intro
duck/fade/outro sting implemented with **real** ffmpeg filter graphs and
tested (synthetic sine-tone fixtures, since no real music assets exist
here — genuinely can't test with real assets, but the ffmpeg command
construction is exercised for real). Loudness: real two-pass ffmpeg
`loudnorm`, verified reaching -16 ±1.5 LUFS against real signal-bearing
audio (`test_normalize_loud_input_reaches_target_lufs`, etc.) — not just
code that looks right. MP3 export 128kbps + ID3 tags (title format
"Cat N · Lesson M — Title", album, track, artist): ✅ verified via
`ffprobe` reading the tags back. Cover art support exists in
`mp3_export.py` and is tested, but ⚠️ **not wired into `pipeline.py`** — the
CLI's `run` command doesn't currently pass a cover art path through, so no
episode gets cover art by default even if you configure one.

### 4.6 Video assembly
✅ Pure FFmpeg, no MoviePy anywhere. 16:9 and 9:16 from the same audio:
tested with real ffmpeg encodes + ffprobe verification of resolution/codec.
On-screen category/lesson/English/Arabic title via **libass, not
drawtext** (the instruction explicitly warns drawtext can't shape Arabic
correctly) — I verified this by rendering a real frame with the actual
Arabic string from your Lesson 1 (`الحديث عن طقس اليوم`) and visually
inspecting it: RTL, letters correctly joined. Subtitles from known
per-line timings (no STT anywhere): ✅, burned via libass, exported as
`.srt` separately: ✅. Speaker-name coloring: I colored the name prefix one
accent color distinct from the body text (not a unique color per speaker)
— the instruction reads as "name vs. body" to me, but "per-speaker
palette" is a defensible alternate reading I didn't ask about; flagging it
now. Vocabulary end card: N seconds (2/item, min 8) ✅ tested and visually
verified with all 7 real vocab terms from Lesson 1 rendering correctly.
⚠️ **Gap**: "gentle outro music underneath" the vocab card specifically is
**not implemented** — the vocab card currently plays over silence, not
music, even if outro music is configured. (The *audio-only* MP3's outro
sting, a separate requirement in 4.5, does work.) H.264/yuv420p/AAC/faststart:
✅ verified via ffprobe. "6-minute episode renders in minutes": ⚠️ I only
tested with tiny fixtures (tens of seconds to ~2 minutes of content) and
added `-preset veryfast` after seeing test runtime — I have **not**
benchmarked an actual 6-minute episode end to end. Given the encoder is
mostly re-rendering a static image, I'd expect it to hold, but this is an
extrapolation, not a measurement.

### 4.7 Manifest & idempotent reruns
✅ SQLite manifest: content hash, engine, output paths, status, timestamps,
characters synthesized. Diff logic tested thoroughly (new / changed /
previously-failed / engine-changed / up-to-date), including persistence
across process restarts. `--force`, `--only cat31:5`/`cat31`, `--formats
audio|video|both`, `--dry-run`: all implemented and tested via real CLI
invocations, not just argument parsing. Parallelism: `ThreadPoolExecutor`,
`config.pipeline.concurrency` (default `min(4, cpu_count)`) — implemented,
but ⚠️ **not stress-tested** with a large batch to confirm real concurrent
speedup or thread-safety under load beyond the manifest's SQLite lock
(which is deliberately synchronized — `Manifest._lock`). "Cloud engines
respect per-provider rate limits": ❌ **not implemented** — retries-with-
backoff exist per adapter, but there's no proactive rate limiter (token
bucket / request pacing) anywhere. "Safe to Ctrl+C and resume": by
construction each lesson's manifest write happens only after that lesson
fully completes, so an interrupted run should leave completed lessons
recorded and simply reprocess the interrupted one on rerun — but I did
**not** test this with an actual simulated interrupt (e.g. SIGINT mid-run).

### 4.8 CLI
✅ `python -m dorosak_factory run` with sane defaults; `status`,
`cost-report` implemented and tested. `validate` is implemented as a
**lighter spot-check** (confirms manifest-recorded files still exist and
are ffprobe-playable) rather than fully re-running every section-5 check
— re-running loudness/duration/timeline checks on already-produced output
would need the full `AssemblyResult`/timeline reconstructed from stored
artifacts, which the manifest doesn't currently retain; documented as a
scope reduction, not silently shipped as if it were the full thing.
⚠️ "Rich, readable console output with a progress bar": output is
structured and readable (`report.run_report.render_text`), but there is
**no progress bar** (no `rich`/`tqdm` integration). ✅ "full logs to
`output/logs/run_{timestamp}.log`": implemented and tested
(`test_run_writes_a_timestamped_log_file`) — every `run` invocation
(including `--dry-run`) writes a timestamped log file recording the
resolved engine, any parse errors, and the final report/plan text. This is
a **summary log**, not a verbose per-subprocess trace (individual ffmpeg
invocations aren't logged line-by-line) — worth knowing if you expected
full debug-level output there.

## 5. Validation & self-evaluation

✅ Every per-episode check from this section is implemented in
`validate/episode.py` and individually tested with real files, including
deliberately-broken cases so I know the checks actually fire (missing MP3,
too-short duration, missing SRT, incomplete metadata, silent audio failing
loudness, wrong video resolution) — not just a function that always
returns `passed=True`. Failing episodes are marked `failed` in the
manifest with the concrete reason (verified via the CLI integration test:
`NullEngine`'s inherent silence correctly fails the loudness gate every
time, proving the gate is real, not a rubber stamp). Run report totals
(processed/skipped/failed, wall time, characters, cost by engine): ✅
tested.

## 6. Testing requirements

- ✅ Parser: 25 tests against the two real files.
- ✅ Voice-role determinism: 6 tests.
- ✅ Subtitle timing math: 15 tests (SRT + ASS).
- ✅ Manifest diff logic: 9 tests.
- ✅ Engine auto-detection with mocked env vars: 6 tests for the mechanism
  in isolation + 6 more against all real registered engines.
- ✅ Cost calculation: `test_run_report.py`.
- ✅ Integration test with a tiny 2-lesson fixture via NullEngine, run
  through the **actual CLI** end-to-end: `tests/test_cli.py` +
  `tests/fixtures/cat99_tiny_fixture.md`. FFmpeg **was** available in this
  environment, and I did run it for real throughout (every audio/video
  test invokes real `ffmpeg`/`ffprobe` subprocesses, verified by reading
  their output — not asserted blindly).
- ✅ `pytest tests/` runs everything; `Makefile`'s `make test` target wraps it.

**Test count**: 211 tests as of the last full run before this document,
all passing (`.venv/bin/pytest tests/ -v`). Total wall time ~2 minutes,
dominated by real ffmpeg video encodes.

## 7. Documentation deliverables

- ✅ `README.md`: quickstart (5 steps), mermaid architecture diagram, how
  reruns work, how to add a lesson file, how to switch engines, how to add
  a new engine (step-by-step + code skeleton matching the real interface).
- ✅ `ASSETS.md`: backgrounds (exact naming convention `cat{N}.png` +
  `default.png`), fonts (names the actual Arabic font used and tested —
  Noto Sans/Naskh Arabic), music (optional, exact config keys), cover art,
  ElevenLabs' special case (no universal voice defaults, must configure).
- ✅ `OPERATOR_TODO.md`: ordered, names Kokoro's real HF repo and each
  provider's console by name, no fabricated URLs.
- ✅ `config.example.yaml` + `.env.example`: fully commented, every key
  matches an actual `Config` dataclass field (not aspirational/unused keys).
- ⚠️ Docstrings: present on effectively every public function/class I
  wrote — I did not grep-audit every single one individually, but the
  pattern was consistent throughout (module docstring + class/function
  docstrings explaining *why*, not restating the signature). No dead code
  or TODO-comments: confirmed by grep (`grep -rn "TODO\|FIXME\|except:"
  dorosak_factory/` → none found).

## 8. Quality bar

- ✅ `black` + `ruff` both pass clean as of the final pass in this session
  (`ruff check dorosak_factory tests` → "All checks passed!").
- ✅ Custom exceptions (`DorosakError`, `FFmpegError`, `MissingAssetError`,
  `AzureSynthesisError`), no bare `except:` anywhere (grepped, confirmed).
- ✅ No hardcoded paths — everything routes through `Config`.
- ⚠️ Structured logging: only `kokoro_engine.py` uses Python's `logging`
  module (device detection). Everywhere else, the CLI uses `print()` for
  user-facing output (appropriate for a CLI) but there's no internal
  structured logger for diagnostics in `pipeline.py`, `validate/`, etc. —
  combined with the missing log-file gap in 4.8, this is the same
  underlying gap counted twice from two angles.
- ✅ Small, focused modules — no file in this codebase does more than one
  clearly-named job.

## 9. Order of work

Followed 1 → 7 as written. For steps 6-9 I reordered pragmatically: I
pulled `validate/episode.py` and `report/run_report.py` (nominally step 8)
forward into step 6, because the CLI's `run` command genuinely can't mark
manifest entries failed/succeeded without them — building the CLI first
and stubbing validation would have meant either faking success or leaving
`run` half-built. I flagged this reordering at the time rather than
silently deviating from the stated sequence.

## Summary of honest gaps (not buried above)

1. Per-role engine override (e.g. premium voice for host only) — not wired.
2. Cover art — implemented but not connected to the default pipeline run.
3. Vocab card background music — plays silence, not the configured outro.
4. Real 6-minute-episode render time — extrapolated, not measured.
5. Cloud provider rate limiting — retry-on-failure exists, proactive
   pacing does not.
6. Ctrl+C/resume safety — correct by construction, not tested with a real
   interrupt.
7. `validate` CLI command — spot-check only, not a full section-5 re-run.
8. No progress bar (the log file gap was closed — see 4.8).

None of these were hidden during the build — each was flagged in this
document at the point it applies, with the reasoning for why it's a gap
rather than a silent shortcut.

## Changelog: fixes from real team/client feedback (post-delivery)

A team review thread surfaced two concrete, verified requirements that
weren't in the original `INSTRUCTIONS.md` and were fixed in response:

1. **American accent only, never British.** Audited every engine's
   default voice map against real provider data (Azure/Google encode
   locale directly in the voice name; Polly's 6 default voices verified
   against AWS's official voice table — all `English (US)`). Found one
   real violation: `KokoroEngine.DEFAULT_VOICE_MAP["male_2"]` was
   `bm_george` — Kokoro's naming prefixes voices `a` (American) / `b`
   (British), so this was a genuine British-voice default. Fixed to
   `am_echo`. Added `test_default_voice_map_is_american_only`, which
   asserts every Kokoro default voice starts with `a`, so this class of
   regression can't reoccur silently. Updated `docs/OPERATOR_TODO.md`'s
   download command to match.
2. **Episodes must open with "Podcast N," not "Lesson N."** This turned
   out to be more than a label change: the real source Markdown scripts
   literally speak "Lesson N" in the Host Intro text that gets
   synthesized (verified against `new_inputs/MDFiles/.../cat07_academic_english...md`).
   Added `rename_lesson_to_podcast()` in `audio/assembly.py`, applied to
   the Host Intro before synthesis so the word actually spoken changes
   (and the subtitle/timeline text matches what's spoken). Also updated
   the two written surfaces that said "Lesson N": the MP3 ID3 title
   (`audio/mp3_export.py`) and the video title card
   (`subtitles/title_card.py`). Scope check: confirmed via the real files
   that "Lesson N" only ever appears in the Markdown header (structural,
   never rendered to the listener) and the Host Intro (spoken) — never
   inside dialogue turns or vocabulary — so no other transform was needed.
3. **"Voices should be different for all the podcasts"** — interpreted as
   already satisfied (each speaker within an episode already gets a
   distinct voice via `tts/voice_roles.py`) rather than a request for
   voice variety *between* different episodes, based on context (said in
   the same breath as a listening-QA pass across sample episodes). This
   was my call, not a silent guess — I flagged the ambiguity to the
   operator and they deferred the decision back to me; recording the
   reasoning here in case it turns out to mean something else.

Not yet addressed from that same thread: the ~500 lessons already
delivered in the first batch (10 categories) were produced before these
fixes and will need regenerating with the corrected voice map and Host
Intro wording — the manifest's content-hash diffing won't catch this on
its own since the source Markdown didn't change, only the pipeline logic
did (a `--force` rerun, or a manifest-engine-version bump, is needed to
trigger reprocessing of already-"successful" lessons).

## Changelog: two more bugs found via a real (non-mocked) run

Getting an actual Kokoro synthesis working on the operator's machine
surfaced two more real gaps that unit tests with mocked engines couldn't
have caught:

1. **`.env` was never actually loaded.** Every engine's `is_available()`
   reads `os.environ`, every doc told the operator to create `.env`, but
   nothing anywhere ever loaded that file into the running process -
   `run --dry-run` always reported "No TTS engine available" regardless
   of what was in `.env`. Fixed with `python-dotenv`, loaded once at the
   top of `cli.py`'s `main()`, before config/engine resolution. Added
   `tests/test_env_loading.py`. This is the kind of gap that's invisible
   to a test suite that always passes explicit env dicts directly and
   never exercises the real CLI entry point against a real file - worth
   remembering for future integration tests.
2. **Kokoro's own dependency chain downloads a spaCy model on first real
   use.** `misaki`/kokoro's English G2P component pulls `en_core_web_sm`
   (~13 MB) via pip automatically the first time text is actually
   synthesized (not on `--dry-run`, which never reaches this code path -
   that's why it wasn't caught earlier). This is real network access
   this project doesn't control (it's inside kokoro's own dependency, not
   our adapter code) - documented in `docs/OPERATOR_TODO.md` step 4.6 so
   it doesn't read as this project silently downloading something. One
   real end-to-end lesson (`cat30:1`, audio only) completed successfully
   after this: 102.5s of real audio, correct "Podcast 1" ID3 title,
   zero validation failures - the first genuine (non-`NullEngine`) proof
   the full pipeline works.
