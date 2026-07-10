# Assets the operator must supply

Nothing in this list is downloaded, generated, or fabricated by the pipeline.
If a file below is missing when it's needed, the run fails loudly with the
exact path it expected — it never silently skips or produces placeholder
output.

## Backgrounds (video)

Path: `assets/backgrounds/`

| File | Used for |
|---|---|
| `cat{N}.png` (e.g. `cat30.png`, `cat31.png`) | Background for every lesson in category N |
| `default.png` | Fallback when no `cat{N}.png` exists for a category |

- **Resolution**: at least 1920×1080. The builder scales-and-crops to fill
  both 16:9 (1920×1080) and 9:16 (1080×1920), so a landscape image with
  visually uneventful edges (no important content near the left/right
  thirds) crops best for the 9:16 version.
- **Format**: PNG or JPG (anything ffmpeg can decode as a still image).

## Fonts

Path: `assets/fonts/` (or installed system-wide via fontconfig — either works)

- **Required**: an Arabic-capable font for the on-screen Arabic lesson
  titles and the burned-in subtitle track. This project was built and
  tested against **Noto Sans Arabic** / **Noto Naskh Arabic**, which render
  correctly RTL-shaped via libass. If you use a different font, verify it
  has Arabic glyphs and test with a real Arabic string before relying on it.
- Set the font name in `config.yaml` under `video.font_name` — it's looked
  up by name via fontconfig, so it must be installed on the machine running
  the pipeline (`fc-list | grep -i arabic` to check).

## Music (optional)

Path: `assets/music/`

Both are **optional** — leave `audio.music.intro_path` / `outro_path` unset
in `config.yaml` to run with no music at all. If you set a path, that file
must exist or the run fails loudly.

| File | Used for |
|---|---|
| Intro bed (e.g. `intro.mp3`) | Fades in, ducks under the Host Intro narration, fades out — set via `audio.music.intro_path` |
| Outro sting (e.g. `outro.mp3`) | Short clip appended at the end of the audio-only MP3 — set via `audio.music.outro_path` |

No specific format/length requirement — any ffmpeg-readable audio file
works; it's resampled to the pipeline's internal format automatically.

## Cover art (optional)

Any square image (1400×1400 or larger is the usual podcast-platform
recommendation) passed explicitly to the MP3 exporter. Not wired into the
CLI's default `run` command yet — see SELF_EVALUATION.md.

## Kokoro model (if using the local engine)

Not a file you place in `assets/` — see `OPERATOR_TODO.md` step 4 for the
full download walkthrough (exact commands, verified file sizes). You need
three things pointed at via `.env`: `KOKORO_MODEL_PATH` (the `.pth` weights
file), `KOKORO_CONFIG_PATH` (`config.json`), and `KOKORO_VOICES_DIR` (a
folder containing the `.pt` voice files you want to use — the adapter
requires the specific local file for each voice and will not download one
on the fly, by design).

## ElevenLabs voice IDs (if using that engine)

ElevenLabs voices are account-specific (cloned or library voices), unlike
the other providers which ship with universal named presets. There is no
built-in default voice map for this engine — you must add one to
`config.yaml`:

```yaml
tts:
  voice_map:
    elevenlabs:
      host: <voice ID from your ElevenLabs account>
      female_1: <voice ID>
      male_1: <voice ID>
      female_2: <voice ID>
      male_2: <voice ID>
      neutral_1: <voice ID>
```
