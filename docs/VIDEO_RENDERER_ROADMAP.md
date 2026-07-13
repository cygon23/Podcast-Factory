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
a talking-head video clip. **Important distinction**: we only have a
*photo* + *audio* (no filmed performance to copy expressions from), so the
model must be **audio-driven**, not video-driven.

| Model | Org | Driven by | Notes |
|---|---|---|---|
| **SadTalker** ⭐ | — | audio + 1 photo | Purpose-built for exactly our case. Well-documented, moderate GPU need, plenty of ready-made Colab/Kaggle notebooks. **Top pick for the first test.** |
| **MuseTalk** ⭐ | Tencent | audio + 1 photo/video | Sharper lip-sync than SadTalker, heavier setup (face parsing + Whisper features). Upgrade path once SadTalker is validated. |
| LatentSync | ByteDance | audio + reference video | Highest quality, but wants a reference video, not just a photo — better suited to a later stage. |
| Wav2Lip | — | audio + 1 photo/video | Lightest weight, mouth-region-only, noticeably lower quality — fallback only. |
| ~~LivePortrait~~ | Kuaishou | **driving video** (not audio) | Re-targets an existing *filmed* expression/pose onto a photo. Not usable here directly since we have no driving footage — worth revisiting only if we ever record a real performance to retarget. |

SadTalker, MuseTalk, Wav2Lip and LatentSync are all open-weight and run
fully local (no API key, no network call at render time) — satisfying
"it has to be a local model."

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

## One-time free-GPU test procedure (before any code changes)

Goal: produce **one** avatar clip good enough to judge — not integrated
into the pipeline yet, just a raw MP4 to eyeball. Uses Kaggle Notebooks'
free GPU quota (30 GPU-hours/week, P100 or T4×2, 16GB VRAM) — no payment,
no local hardware.

### 1. Accounts (5 min)

1. Kaggle account at kaggle.com, then **Settings → Phone Verification**
   (required before Kaggle will grant GPU + internet access to notebooks).
2. Hugging Face account at huggingface.co, then **Settings → Access
   Tokens → New token** (role: "Read"). Copy it somewhere safe.
3. To avoid a licensing wait: use **FLUX.1-schnell**
   (`black-forest-labs/FLUX.1-schnell`) instead of FLUX.1-dev for this
   test — it's Apache-2.0, no gated-repo approval needed, and only needs
   ~4 inference steps (fast on a free GPU). Swap to `FLUX.1-dev` later if
   its extra quality is worth the approval wait (usually granted within
   minutes on the model's Hugging Face page, "Agree and access
   repository").

### 2. Kaggle notebook setup (5 min)

1. kaggle.com → **Create → New Notebook**.
2. Right sidebar → **Settings → Accelerator → GPU T4 x2** (or P100 if
   offered).
3. Same sidebar → toggle **Internet: On** (needed for `pip install` and
   downloading model weights).
4. **Add-ons → Secrets → Add a new secret**: name it `HF_TOKEN`, paste
   your Hugging Face token. (Keeps it out of the notebook's plaintext,
   important since Kaggle notebooks are easy to accidentally make public.)

### 3. Generate one avatar portrait (~2 min run time)

```python
!pip install -q diffusers transformers accelerate safetensors sentencepiece huggingface_hub

from huggingface_hub import login
from kaggle_secrets import UserSecretsClient
login(UserSecretsClient().get_secret("HF_TOKEN"))

import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-schnell", torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()  # keeps it inside 16GB VRAM

image = pipe(
    prompt=(
        "photorealistic portrait of a friendly professional podcast host, "
        "sitting in a modern studio, soft studio lighting, looking directly "
        "at camera, neutral expression, mouth closed, shoulders visible, "
        "high detail, 4k"
    ),
    num_inference_steps=4,
    guidance_scale=0.0,
).images[0]
image.save("/kaggle/working/host_avatar.png")
```

Download `host_avatar.png` from the notebook's file browser (or commit
the notebook so it appears under "Output").

### 4. Animate it with real episode audio (~10-15 min setup, GPU-fast run)

1. Upload one real dialogue line's audio as a Kaggle **Dataset** (simplest
   path: zip a short WAV — e.g. one line already synthesized locally by
   Kokoro — and upload it via **Add Data → Upload**), or just re-run the
   existing local pipeline for one lesson and grab `episode.mp3`/one
   cached line WAV from `output/cat30/lesson1/`.
2. In the same (or a new) Kaggle notebook:
   ```
   !git clone https://github.com/OpenTalker/SadTalker
   %cd SadTalker
   !pip install -q -r requirements.txt
   !bash scripts/download_models.sh
   ```
3. Run inference:
   ```
   !python inference.py \
     --driven_audio /kaggle/input/<your-dataset>/sample_line.wav \
     --source_image /kaggle/working/host_avatar.png \
     --result_dir /kaggle/working/result \
     --still --preprocess full --enhancer gfpgan
   ```
   (`--enhancer gfpgan` face-restores/sharpens the output — worth the
   extra runtime for a quality test.)
4. Download the resulting MP4 from `/kaggle/working/result/`.

### 5. Judge it

Watch the raw clip against `input/demo.mp4`'s bar. If it holds up:
promote SadTalker to a real `local_avatar_renderer.py` adapter (see next
section) and repeat the same two steps for the other 5 voice roles'
portraits. If lip-sync quality isn't sharp enough, try MuseTalk next with
the same portrait — no need to redo Stage 1.

Kaggle notebooks disconnect after ~20 min idle and cap sessions at 12
hours — for a single test this is a non-issue, just don't leave it idle
mid-run. Google Colab's free tier is a viable alternative (T4, similar
setup) if you prefer that UI, but its GPU availability is less
predictable and idle-disconnects are stricter.

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
