# Operator TODO — do this before the first real run

This is a full walkthrough, written so you can follow it even if you've
never set up a Python project before. Every command is copy-pasteable.
Every step says what you should see if it worked, and what to do if it
didn't.

Everything here is a manual step for a human — the pipeline itself will
refuse to run (with a clear error naming exactly what's missing) rather
than skip any of this silently, so if you forget a step you'll get told
which one.

**Order matters** — later steps assume earlier ones are done. Work top to
bottom.

---

## Step 1 — Install Python and set up the project

You need **Python 3.11 or newer**. Check what you have:

```bash
python3 --version
```

- **If you see `Python 3.11.x` or higher** — good, skip to the next command.
- **If it's older, or the command isn't found** — install Python from
  [python.org/downloads](https://www.python.org/downloads/) (Windows/macOS)
  or your package manager (`sudo apt install python3.12` on
  Ubuntu/Debian, `brew install python@3.12` on macOS with Homebrew).

Now, from the project's root folder (the one containing this `docs/`
folder and `dorosak_factory/`), create an isolated Python environment and
install the project's dependencies into it:

```bash
python3 -m venv .venv
```

This creates a `.venv` folder — a self-contained Python install just for
this project, so it can't conflict with anything else on your machine.

Activate it (you'll need to do this every time you open a new terminal to
work on this project):

```bash
# macOS / Linux:
source .venv/bin/activate

# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Windows (cmd.exe):
.venv\Scripts\activate.bat
```

**How to tell it worked**: your terminal prompt should now start with
`(.venv)`. Every `python`/`pip` command from here on uses this isolated copy.

Now install the base dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**What you should see**: a bunch of download/install lines ending in
something like `Successfully installed PyYAML-... openai-... boto3-...`.
This takes a minute or two.

**Verify it worked**:

```bash
python -m pytest tests/ -v
```

**What you should see**: a long list of lines ending in `passed` (200+ of
them), finishing with something like `215 passed in 80s`. This runs the
*entire* test suite using a built-in silent test engine — no API keys, no
internet access needed for this step. If this passes, your Python
environment is correctly set up and every step below should work.

If you see failures here, stop and fix this before continuing — nothing
past this point will work reliably otherwise.

---

## Step 2 — Install FFmpeg

Every audio and video file this project produces goes through FFmpeg.

**Install it:**

```bash
# Ubuntu / Debian:
sudo apt update && sudo apt install ffmpeg

# macOS (Homebrew):
brew install ffmpeg

# Windows: download a build from https://www.gyan.dev/ffmpeg/builds/
# (get the "full" build, unzip it, and add its bin/ folder to your PATH)
```

**Verify it worked:**

```bash
ffmpeg -version
ffprobe -version
```

You should see a version number and a long `configuration:` line. Check
that line contains **both** `--enable-libass` (needed for burned-in
subtitles) and `--enable-libmp3lame` (needed for MP3 export):

```bash
ffmpeg -version | grep -o "enable-libass\|enable-libmp3lame"
```

**Expected output** (both lines must appear, order doesn't matter):
```
enable-libass
enable-libmp3lame
```

If either is missing, your FFmpeg build doesn't support this project's
needs — install a "full"/"non-free" build instead of a minimal one (most
distro packages already include both, so this is rare).

---

## Step 3 — Choose ONE text-to-speech engine

You only need **one** working engine to start; you can add more later. If
you're not sure which to pick:

| If you want... | Pick |
|---|---|
| Zero cost, willing to do a one-time ~330MB download and don't mind it running slower on CPU | **Kokoro** (Step 4 below) |
| The fastest possible setup — just paste in an API key, no downloads | **OpenAI** or **Azure** (Step 5/6) |
| You already use Google Cloud / AWS for other things | **Google** or **Polly** (Step 7/8) |
| You specifically want ElevenLabs' voice quality and already have an account | **ElevenLabs** (Step 9) |

Do **one** of Steps 4–9 below (skip the rest), then continue to Step 10.

---

## Step 4 — Kokoro (local, $0, no API key, no internet needed at run time)

This is the most involved option because you're downloading a model
instead of just pasting in a key, but it's also the only option with zero
ongoing cost. Real, tested file sizes and commands below — nothing guessed.

### 4.1 Install the Python package

```bash
pip install kokoro
```

This pulls in `torch` (PyTorch) and a few text-processing libraries. It's
a sizeable download (a few hundred MB) but is a normal Python package
install — no manual steps needed, and it does **not** require a separate
system-level `espeak-ng` install (the package bundles its own).

**Verify it worked:**
```bash
python -c "import kokoro; print('kokoro OK')"
```

### 4.2 Download the model files

The model lives at **hexgrad/Kokoro-82M** on Hugging Face. You need three
things from it: the config, the model weights, and at least the specific
voice files this project uses by default. The `huggingface_hub` package
(installed automatically with `kokoro` above) gives you a `hf` command
that downloads directly — no browser needed.

Pick a folder to hold the model (anywhere on your machine — this example
uses a folder inside the project called `kokoro_model/`):

```bash
mkdir -p kokoro_model
```

Download the config file (~2 KB):
```bash
hf download hexgrad/Kokoro-82M config.json --local-dir ./kokoro_model
```

Download the model weights (~327 MB — this is the slow one):
```bash
hf download hexgrad/Kokoro-82M kokoro-v1_0.pth --local-dir ./kokoro_model
```

Download the 6 voice files this project's default configuration uses
(about 500 KB each, ~3 MB total). All six are American voices
(Kokoro's naming: `a` = American, `b` = British) — this project requires
American accent only, so never substitute a `b`-prefixed voice here:
```bash
hf download hexgrad/Kokoro-82M \
  voices/am_michael.pt voices/af_bella.pt voices/am_adam.pt \
  voices/af_sarah.pt voices/am_echo.pt voices/af_nicole.pt \
  --local-dir ./kokoro_model
```

**What you should end up with:**
```
kokoro_model/
  config.json
  kokoro-v1_0.pth
  voices/
    am_michael.pt
    af_bella.pt
    am_adam.pt
    af_sarah.pt
    am_echo.pt
    af_nicole.pt
```

Verify with:
```bash
ls -la kokoro_model/ kokoro_model/voices/
```

You should see `config.json` and `kokoro-v1_0.pth` in the first listing,
and the 6 `.pt` files in the second.

> **Want more voices later?** The full catalog (50 voices, American/British
> × female/male, plus several other languages) is listed at
> https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md — download
> any of them the same way (`hf download hexgrad/Kokoro-82M voices/NAME.pt
> --local-dir ./kokoro_model`) and reference them in `config.yaml` under
> `tts.voice_map.kokoro` (see `config.example.yaml`).

> **Why download voices individually instead of the whole model at once?**
> Kokoro's own code will try to download a voice from the internet
> automatically if it can't find it locally — which would violate this
> project's "never download anything at run time" rule. This project's
> adapter code specifically avoids that by requiring every voice file to
> already exist locally before it will use it (see the comment at the top
> of `dorosak_factory/tts/engines/kokoro_engine.py` if you want the
> technical detail).

### 4.3 Point `.env` at your downloaded files

(If you haven't created `.env` yet, do Step 10 first, then come back here.)

Open `.env` and fill in the full, absolute paths to what you just
downloaded:

```bash
KOKORO_MODEL_PATH=/absolute/path/to/kokoro_model/kokoro-v1_0.pth
KOKORO_CONFIG_PATH=/absolute/path/to/kokoro_model/config.json
KOKORO_VOICES_DIR=/absolute/path/to/kokoro_model/voices
```

Get the absolute path quickly with:
```bash
cd kokoro_model && pwd && cd ..
```

### 4.4 GPU vs CPU

Nothing to configure — this project automatically detects and uses an
NVIDIA GPU (CUDA) or Apple Silicon GPU (MPS) if either is available on
your machine, and falls back to CPU otherwise. It logs which one it picked
at the start of each run. CPU works fine, just slower.

### 4.5 Verify Kokoro is detected

```bash
python -m dorosak_factory run --dry-run
```

**What you should see**: `Engine resolved: kokoro` near the top of the
output. If it instead says a different engine (or errors out listing what
to configure), double check the three paths in `.env` are correct,
absolute, and that the files actually exist at those paths.

### 4.6 First real synthesis: a one-time extra download you'll see

The **first** time you actually synthesize audio (not `--dry-run` — an
actual `run`), kokoro's own text-processing dependency (`spacy`'s English
model, `en_core_web_sm`, ~13 MB) downloads and installs itself
automatically if it isn't already present. You'll see lines like
`Collecting en-core-web-sm==3.8.0 ... Successfully installed` scroll by.

This is real network access happening outside this project's control (deep
inside kokoro's own dependency chain, not something our adapter code
triggers or can prevent) — flagging it here so it doesn't look like this
project silently downloading something. It only happens once; every run
after that reuses the installed package with no network access.

---

## Step 5 — Azure Cognitive Services Speech

1. Go to [portal.azure.com](https://portal.azure.com) and sign in (or
   create a free account).
2. Search for **"Speech services"** in the top search bar → click
   **Create**.
3. Fill in: Subscription (your account), Resource group (create one if
   you don't have one, e.g. `dorosak-rg`), Region (pick one close to
   you — remember it, you'll need it), Name (anything), Pricing tier
   (Free F0 tier works for testing).
4. Click **Review + create**, then **Create**. Wait ~1 minute for
   deployment.
5. Go to the resource once it's created → left sidebar **"Keys and
   Endpoint"** → copy **KEY 1** and note the **Location/Region** shown on
   that same page (e.g. `eastus`).
6. In `.env`, set:
   ```bash
   AZURE_SPEECH_KEY=<paste KEY 1 here>
   AZURE_SPEECH_REGION=<e.g. eastus>
   ```

Verify: `python -m dorosak_factory run --dry-run` should print `Engine
resolved: azure` (as long as no engine ahead of it in priority — Kokoro —
is also configured; see the priority order in `docs/README.md`).

---

## Step 6 — OpenAI

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
   and sign in.
2. Click **Create new secret key**, name it (e.g. `dorosak`), click
   **Create secret key**.
3. **Copy it immediately** — OpenAI only shows it once.
4. In `.env`, set:
   ```bash
   OPENAI_API_KEY=<paste the key here, starts with sk-...>
   ```
5. Make sure your OpenAI account has billing set up (Settings → Billing) —
   the TTS API is pay-per-character, not covered by a free tier.

Verify: `python -m dorosak_factory run --dry-run` should print `Engine
resolved: openai` (assuming Kokoro/Azure aren't also configured).

---

## Step 7 — Google Cloud Text-to-Speech

1. Go to [console.cloud.google.com](https://console.cloud.google.com),
   create or select a project.
2. In the search bar, type **"Text-to-Speech API"** → open it → click
   **Enable**.
3. Go to **IAM & Admin → Service Accounts** → **Create Service Account**.
   Name it (e.g. `dorosak-tts`), skip the optional role/access steps
   (or grant "Cloud Text-to-Speech User" if you want to be precise),
   click **Done**.
4. Click on the service account you just created → **Keys** tab →
   **Add Key → Create new key → JSON** → this downloads a `.json` file to
   your computer.
5. Move that file somewhere safe (e.g. `mkdir -p ~/gcp-keys && mv
   ~/Downloads/*.json ~/gcp-keys/dorosak-tts.json`).
6. In `.env`, set:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/dorosak-tts.json
   ```

Verify: `python -m dorosak_factory run --dry-run` should print `Engine
resolved: google` (assuming no higher-priority engine is also configured).

---

## Step 8 — Amazon Polly

1. Go to [console.aws.amazon.com/iam](https://console.aws.amazon.com/iam)
   and sign in (or create an account).
2. **Users → Create user**, name it (e.g. `dorosak-polly`).
3. **Attach policies directly** → search for and check
   **AmazonPollyFullAccess** → continue → **Create user**.
4. Click the new user → **Security credentials** tab → **Create access
   key** → choose **Command Line Interface (CLI)** → confirm → **Create
   access key**.
5. Copy both the **Access key** and **Secret access key** shown (the
   secret is only shown once).
6. In `.env`, set:
   ```bash
   AWS_ACCESS_KEY_ID=<access key>
   AWS_SECRET_ACCESS_KEY=<secret access key>
   AWS_REGION=us-east-1
   ```
   (any region with Polly available works — `us-east-1` is a safe default)

Verify: `python -m dorosak_factory run --dry-run` should print `Engine
resolved: polly` (assuming no higher-priority engine is also configured).

---

## Step 9 — ElevenLabs

Unlike the other providers, ElevenLabs voices are specific to *your*
account (cloned/library voices), so there's an extra step here.

1. Go to [elevenlabs.io](https://elevenlabs.io), sign in.
2. **Profile icon → API Keys** → **Create API Key** → copy it.
3. In `.env`, set:
   ```bash
   ELEVENLABS_API_KEY=<paste key here>
   ```
4. Go to **Voices** in the ElevenLabs dashboard, pick (or add) 6 voices —
   one for each of: `host`, `female_1`, `male_1`, `female_2`, `male_2`,
   `neutral_1`. Click each voice → copy its **Voice ID** (a string like
   `21m00Tcm4TlvDq8ikWAM`).
5. Open `config.yaml` (create it from `config.example.yaml` first if you
   haven't — Step 11 below) and fill in:
   ```yaml
   tts:
     voice_map:
       elevenlabs:
         host: <voice ID>
         female_1: <voice ID>
         male_1: <voice ID>
         female_2: <voice ID>
         male_2: <voice ID>
         neutral_1: <voice ID>
   ```

This engine will not work without step 5 — it has no built-in default
voices (see `docs/ASSETS.md` for why).

---

## Step 10 — Create `.env`

If you haven't already (some steps above assumed this):

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in only the section(s) for the
engine(s) you configured above. Leave everything else blank.

**Never commit this file or share it** — it holds your real credentials.
It's already excluded via `.gitignore`.

---

## Step 11 — Create `config.yaml` (optional)

```bash
cp config.example.yaml config.yaml
```

Only needed if you want to change a default (pause timings, loudness
target, which video resolutions to render, voice mappings, ElevenLabs
voice IDs from Step 9, etc.) — every setting is commented in the file
itself. Skip this entirely and the pipeline runs on sane defaults.

---

## Step 12 — Place assets

See `docs/ASSETS.md` for the complete list with exact filenames. At
minimum, for video output you need:

- `assets/backgrounds/default.png` (a background image, at least
  1920×1080)
- An Arabic-capable font installed on your system — this project was
  built and tested against **Noto Sans Arabic**. Check if you already
  have it:
  ```bash
  fc-list | grep -i "noto sans arabic"
  ```
  If nothing prints, install it:
  ```bash
  # Ubuntu/Debian:
  sudo apt install fonts-noto

  # macOS:
  brew install --cask font-noto-sans-arabic
  ```

Music is optional — skip it entirely if you don't have any yet.

Audio-only runs (`--formats audio`, see Step 13) don't need any of this —
only video rendering does.

---

## Step 13 — Dry run

```bash
python -m dorosak_factory run --dry-run
```

**What you should see**: which engine was detected, how many lessons would
be processed, and an estimated character count/cost — nothing is
synthesized, no files are created except a small log under `output/logs/`.

If this errors out, the error message will name exactly what's missing —
fix that and re-run this command until it succeeds.

---

## Step 14 — Run one lesson

```bash
python -m dorosak_factory run --only cat30:1 --formats audio
```

This processes just Lesson 1 of category 30, audio only (fast — no video
encoding yet). Check the result:

```bash
# macOS:
afplay output/cat30/lesson1/episode.mp3
# Linux:
ffplay output/cat30/lesson1/episode.mp3
# Windows: just double-click the file in File Explorer
```

Listen to it. If it sounds right, you're ready to scale up. Add `--formats
both` once you also want to render video for this same lesson.

---

## Step 15 — Run everything

```bash
python -m dorosak_factory run
```

This processes every lesson in `input/` that hasn't succeeded yet. Reruns
are safe to repeat — see `docs/README.md`'s "How reruns work" section:
only new, changed, or previously-failed lessons are reprocessed.

Check overall status any time with:
```bash
python -m dorosak_factory status
python -m dorosak_factory cost-report
```

---

## Step 16 — Upload outputs to dorosak.com

Not automated by this project (out of scope by design — see
`docs/README.md`'s architecture notes). Finished episodes land in
`output/cat{N}/lesson{M}/` (MP3, both MP4s, `.srt`, `metadata.json`) for
you to upload manually or wire into your own deploy step.

---

## Step 17 — Final listening/watching quality review

Automated validation (duration, loudness, subtitle timing, resolution —
see `docs/SELF_EVALUATION.md` section 5) catches structural problems, not
whether an episode *sounds* or *looks* good. That's still your call before
publishing.
