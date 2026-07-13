# Video Renderer Roadmap: from static background to AI avatar

Today's video renderer (`static_background`) is a looped image + burned
subtitles — real, tested, and shipping now. This doc is the plan for the
"stunning, podcast-style" upgrade the team asked for (a photorealistic AI
presenter, lip-synced to the episode audio, like `input/demo.mp4`), plus
how cloud API renderers plug in later without touching the pipeline.

**Nothing in this doc is implemented yet.** It's a spec to build against
once GPU hardware is available — see "Why this isn't built yet" below.

## Architecture already in place

Video rendering goes through the same pluggable-adapter pattern as TTS:

```
dorosak_factory/video/
  renderer_base.py       # VideoRenderer ABC (mirrors tts/base.py's TTSEngine)
  renderer_registry.py   # Registry + auto-detection chain (mirrors tts/registry.py)
  renderers/
    __init__.py                       # imports register every built-in renderer
    static_background_renderer.py     # today's real, default renderer
    (future) local_avatar_renderer.py # this doc's subject
    (future) heygen_renderer.py, did_renderer.py, ...  # cloud APIs
```

`pipeline.process_lesson` calls `renderer.render(...)` — it has no idea
whether that's ffmpeg-and-a-static-image or a GPU avatar pipeline or a
cloud API call. `cli.py` resolves the renderer once per run via
`--renderer <name>` or auto-detection (`video.renderer` in `config.yaml`,
priority chain in `DEFAULT_RENDERER_PRIORITY`), exactly like `--engine`
for TTS.

## The target: local avatar renderer, CPU/API-provider-agnostic

Two independent stages, each swappable:

### Stage 1 — one reference portrait per voice role (generated once, reused forever)

Each voice role already has one consistent TTS voice (`host`, `female_1`,
`male_1`, `female_2`, `male_2`, `neutral_1`). The avatar renderer needs one
consistent *face* per role, generated once and reused across all lessons —
the same identity-consistency principle as the voice map.

- **Model**: [FLUX.1 \[dev\]](https://huggingface.co/black-forest-labs/FLUX.1-dev)
  (Black Forest Labs) — the strongest current open-weight photorealistic
  image model. Runs locally, no API call.
- **Output**: one PNG per role, stored in `assets/avatars/<role>.png`
  (mirrors how `assets/backgrounds/` works today).
- **Cost**: one-time, offline, not part of the per-lesson pipeline.

### Stage 2 — lip-sync animation (runs per lesson, per line)

Takes the Stage 1 portrait + the episode's synthesized audio and produces
a talking-head video clip.

| Model | Org | Notes |
|---|---|---|
| **LivePortrait** ⭐ | Kuaishou | Fastest of the group, strong identity preservation, actively maintained. Top pick. |
| **MuseTalk** ⭐ | Tencent | Real-time-capable, good lip-sync accuracy. Top pick. |
| LatentSync | ByteDance | Newer, higher quality, heavier compute. |
| SadTalker | — | Older, well-documented, lighter weight — good fallback. |
| Wav2Lip | — | Lightest weight, lowest quality — last resort. |

All five are open-weight and run fully local (no API key, no network
call at render time) — satisfying "it has to be a local model."

### Why this isn't built yet

This machine has **no NVIDIA GPU** (Intel UHD 620 integrated graphics
only, confirmed via `lspci`), 7.6GB RAM, 8 CPU cores. Every model above
either requires CUDA outright or is impractically slow on CPU (minutes
per second of video, at best, for a 50-lesson batch that needs to ship on
a deadline). Shipping a renderer that can't actually be exercised here
would violate this project's "never fabricate, no half-finished
implementations" rule — so the architecture is ready, the model choice is
researched and documented, but the adapter itself waits for GPU access
(cloud GPU rental, e.g. a single RunPod/Lambda A10 session for batch
rendering, is the cheapest unblock — no local hardware purchase needed).

## Adding `local_avatar_renderer.py` once GPU access exists

Same shape as `static_background_renderer.py` and the TTS "adding a new
engine adapter" recipe in `README.md`:

1. Create `dorosak_factory/video/renderers/local_avatar_renderer.py`
   implementing `VideoRenderer`: `is_available()` checks the model
   weights exist locally (same pattern as Kokoro's `KOKORO_MODEL_PATH`
   check — never triggers a hidden download), `from_config()` reads
   avatar/model paths from a new `config.video.avatar` block,
   `render()` produces the same `VideoBuildResult` shape.
2. Register it in `dorosak_factory/video/renderers/__init__.py`.
3. Add `"local_avatar"` ahead of `"static_background"` in
   `DEFAULT_RENDERER_PRIORITY` (`renderer_registry.py`) — already done,
   so this step is just registering the class.
4. Document the required model files in `OPERATOR_TODO.md`, same style as
   the Kokoro voice-file setup steps.

## Future cloud API renderers

Same recipe, one adapter each, registered the same way — e.g.
`heygen_renderer.py`, `did_renderer.py`, `synthesia_renderer.py`. Each
`is_available()` checks for its own API key env var
(`HEYGEN_API_KEY`, etc.), exactly like the cloud TTS engines. A team
member who wants to use a paid API instead of the local model sets that
engine's key in `.env` and passes `--renderer heygen` (or lets
auto-detection pick it up if it's placed ahead of `static_background` in
priority) — zero code changes, matching the explicit request that "the
pipeline should support APIs from different providers in future."
