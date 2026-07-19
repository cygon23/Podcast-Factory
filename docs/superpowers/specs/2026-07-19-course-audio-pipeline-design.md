# Course Audio Pipeline Design

Status: approved, pending pilot review
Date: 2026-07-19

## Context

Separately from the `cat*` Markdown-based "English for X" podcast pipeline
(`dorosak_factory/`, already shipping — `cat04`, `cat05`, `cat30` done,
`cat31` owned by another team member), the team has a second, overdue
deliverable: audio for Dorosak's actual course catalog, exported as 5
CSVs (`dialogues.csv`, `examples.csv`, `vocabulary.csv`,
`useful_phrases.csv`, `articles.csv`, currently in `~/Downloads/`, not
yet in the repo).

This is what the boss's WhatsApp message ("Day 3, still no audio") and
the instructor's transcript ("200 lessons... podcast content") were
about — cross-checked against the CSVs: **exactly 200 lessons** exist in
`articles.csv`, across 4 book levels (Beginner, Elementary, Intermediate,
Advanced), ~40 units. The transcript's "Jerusalem" is very likely a
mis-transcription of "Dorosak" (unconfirmed — flagged for the user to
verify against the source recording).

## Hard constraint

**The existing `dorosak_factory` pipeline (parser, TTS registry, audio
assembly, video renderer, manifest, CLI `run`/`status`/`validate`/
`cost-report`) must not be modified in any way that could change its
current behavior.** It's shipping, other team members depend on it, and
`cat31` is actively being worked on by someone else right now. This new
work is strictly additive: new modules, new CLI subcommand, new manifest
table. Existing tests must continue to pass unchanged.

## Data source findings

| CSV | Rows | Lessons covered | Structure |
|---|---|---|---|
| `dialogues.csv` | 2,875 | 188 | Teacher/Student, one line per row, ordered by `item_no` |
| `examples.csv` | 2,498 | 198 | `"English sentence — Arabic translation"` per row |
| `vocabulary.csv` | 3,084 | 194 | `"English word\tArabic translation"` per row |
| `useful_phrases.csv` | 3,078 | 186 | Plain English phrase per row |
| `articles.csv` | 201 | 200 | One English reading passage per lesson |

**Existing audio**: `item_audio_link` / `section_audio_link` columns hold
real S3-hosted recordings for some rows — concentrated almost entirely in
Book 1 (Beginner): vocabulary 314/3084, examples 205/2498, useful_phrases
288/3078, dialogues ~0, articles ~0 at item level (21/200 at section
level). **Decision: skip any row where either audio-link column is
already non-empty** — only fill gaps, never regenerate real recordings.

**Bilingual format confirmed empirically**: downloaded one real
vocabulary sample
(`L1 Voc Alphabet_الأبجدية.wav`) and ran `ffmpeg silencedetect` on it —
two speech segments (≈0.9s, ≈0.9s) separated by a ≈1s silence gap,
confirming the real recordings speak **English, pause, Arabic** — not
English-only. New audio must match this structure for vocabulary,
examples, and useful phrases (articles are English-only prose, no Arabic
pairing in the source data).

## Language/licensing finding: Arabic TTS

Kokoro (our existing free local English engine, Apache-2.0) has **no
Arabic voice** — confirmed against its own `VOICES.md` (9 languages: en,
en-GB, ja, zh, es, fr, hi, it, pt-BR; no `ar`). None of the cloud engines
already built into the pipeline (Azure/OpenAI/Google/Polly/ElevenLabs)
have real credentials configured in `.env` — all keys present but empty.

User explicitly wants **free + local**, no subscriptions. Evaluated:

- `facebook/mms-tts-ara` — real, works, but **CC-BY-NC 4.0 (non-commercial
  license)**. Rejected — Dorosak is a paid product; using a
  non-commercial-licensed model here would be a real legal risk, not a
  hypothetical one.
- **Piper TTS** (`pip install piper-tts`, formerly `rhasspy/piper`, now
  maintained at `OHF-Voice/piper1-gpl`) — engine is GPL-3.0 (fine: we run
  it as a tool, don't redistribute modified Piper source, and GPL doesn't
  restrict the audio *output* it produces). The `ar_JO` Arabic voice
  model (`rhasspy/piper-voices`, on Hugging Face) is **MIT-licensed** —
  no commercial-use conflict. Runs on CPU, lightweight (ONNX runtime,
  built for on-device use). **Selected.**

## Architecture

New `dorosak_factory/course/` subpackage, additive only, reusing proven
lower-level infrastructure rather than rebuilding it:

```
dorosak_factory/course/
  models.py           # Book, Unit, CourseLesson, DialogueLine, ExampleItem,
                       # VocabularyItem, PhraseItem, ArticleSection
  csv_parser.py        # reads the 5 CSVs -> models, splits English/Arabic,
                       # skips rows with existing item_audio_link/section_audio_link
  assembly.py           # per-content-type synthesis + file assembly
  course_manifest.py    # new SQLite table, per-item granularity

dorosak_factory/tts/engines/
  piper_engine.py       # new TTSEngine adapter, mirrors kokoro_engine.py's
                         # local-model pattern (is_available checks the .onnx
                         # voice file exists locally, never auto-downloads)
```

Reused as-is, unmodified: `tts.registry` (Piper registers alongside the 6
existing engines), `audio.cache` (per-line SHA256 cache — big win once we
resume after any interruption), `audio.loudness`, `tts.retry`.

### Why a new manifest table instead of extending the existing one

The existing `manifest.sqlite3` records are keyed at
`(category_number, lesson_number)` — one row per lesson, matching the
`cat*` pipeline's one-episode-per-lesson output. This new pipeline has
**item-level** outputs for 3 of 5 content types (one clip per vocabulary
word/example/phrase, not one per lesson). Reusing the existing table
would mean cramming a different granularity into a schema that doesn't
fit it. A new table
(`course_items(csv_source, book_id, unit_id, lesson_id, section_id,
item_no) -> output_path, status`) in the *same* SQLite file keeps
operational simplicity (one DB file) without distorting the existing
schema or touching existing code that reads it.

## Voice mapping

- **Dialogue**: Teacher → one fixed voice role (`host`) across all 200
  lessons and all 4 levels — a consistent recurring "teacher" character.
  Student → one of 4 voice roles, selected by book level (Beginner →
  `female_1`, Elementary → `male_1`, Intermediate → `female_2`, Advanced
  → `male_2`, exact mapping confirmed during pilot review — signals
  progression through the course without needing per-lesson variation).
- **Vocabulary / Examples / Useful Phrases**: English half via Kokoro
  (one consistent narrator voice, `host`), Arabic half via
  `PiperEngine`'s `ar_JO` voice, concatenated with ~1s silence — matching
  the measured real-recording pattern.
- **Article**: single narrator voice (`host`) reads the full passage.

## Output layout

Mirrors the existing S3 naming convention for continuity with
already-recorded files sitting in the same lesson lists:

```
output/course/<book_slug>/unit<N>/lesson<N>/
  dialogue/episode.mp3
  vocabulary/<item_no>_<term_slug>.mp3
  examples/<item_no>.mp3
  useful_phrases/<item_no>.mp3
  article/narration.mp3
```

## CLI

New subcommand, additive to `dorosak_factory/cli.py`'s existing
subparsers (does not change `run`/`status`/`validate`/`cost-report`):

```
python -m dorosak_factory course run --content dialogues|examples|vocabulary|useful_phrases|articles|all
                                      --only <book>:<unit>:<lesson>
                                      --dry-run
                                      --force
```

## Rollout plan (per explicit user instruction)

**Do not generate all 200 lessons in one shot.** Sequence:

1. Build the full pipeline (parser, `PiperEngine`, assembly, manifest,
   CLI) with real tests, TDD throughout — same discipline as the rest of
   this project.
2. **Pilot**: run it end-to-end for **one lesson only** (Lesson 1:
   Alphabet Basics — already has partial real audio, good test of the
   skip-existing logic), producing all 5 content types' audio for that
   one lesson.
3. Share the pilot output with the team for feedback (voice choice,
   bilingual pacing, file naming, overall quality) before spending any
   more compute/time on the other ~199 lessons.
4. Once approved, batch-process the remaining lessons across all 4 book
   levels — the pipeline is already built at that point, so this step is
   just running it, not more development.

## Testing approach

Same TDD discipline as the rest of the project: real CSV fixtures (small,
hand-written, matching the real files' exact column structure), real
`NullEngine` for pipeline-level tests (no network, no cost), real ffmpeg
for audio assembly/silence-gap verification, `PiperEngine` tested against
a real locally-downloaded `ar_JO` voice file (skipped if the file isn't
present, same pattern as Kokoro's engine tests).

## Open risks / unconfirmed items

- "Jerusalem" vs "Dorosak" in the transcript — user to re-check the
  source recording.
- Piper's `ar_JO` voice quality is unverified until the pilot — Jordanian
  Arabic accent may or may not match team expectations; alternate Piper
  Arabic voices exist if `ar_JO` doesn't land well.
- Exact Student-voice-per-level mapping (which of the 4 remaining voice
  roles maps to which book level) is a placeholder above, to be confirmed
  during pilot review, not a hard requirement.
