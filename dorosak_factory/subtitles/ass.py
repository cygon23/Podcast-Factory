"""ASS subtitle generation for burned-in video subtitles (INSTRUCTIONS.md 4.6).

Rendered via libass so Arabic titles elsewhere in the video RTL-shape
correctly; these dialogue cues are English, but the format itself is
Unicode-safe. Speaker name prefixes are colored distinctly from the body
text (a single accent color for all names, not a per-speaker palette -
the instruction reads as "name vs. body", not "speaker vs. speaker").
"""

from __future__ import annotations

from pathlib import Path

from dorosak_factory.audio.assembly import LineTiming

NAME_COLOR_ASS = "&H0000FFFF&"  # yellow (AABBGGRR)
BODY_COLOR_ASS = "&H00FFFFFF&"  # white
DEFAULT_FONT_NAME = "Noto Sans Arabic"
DEFAULT_FONT_SIZE = 48


def format_ass_timestamp(seconds: float) -> str:
    """Formats seconds as ASS's `H:MM:SS.cc` timestamp (centiseconds)."""
    total_cs = round(seconds * 100)
    hours, remainder_cs = divmod(total_cs, 360_000)
    minutes, remainder_cs = divmod(remainder_cs, 6_000)
    secs, centiseconds = divmod(remainder_cs, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def escape_ass_text(text: str) -> str:
    """Escapes text for safe inclusion in an ASS Dialogue line's Text field."""
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def generate_ass(
    timeline: tuple[LineTiming, ...],
    video_width: int,
    video_height: int,
    font_name: str = DEFAULT_FONT_NAME,
    font_size: int = DEFAULT_FONT_SIZE,
    margin_v: int = 60,
) -> str:
    """Renders a timeline into an ASS subtitle track with a colored speaker prefix."""
    header = f"""[Script Info]
Title: Dorosak Episode Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{BODY_COLOR_ASS},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header]
    for entry in timeline:
        start = format_ass_timestamp(entry.start_seconds)
        end = format_ass_timestamp(entry.end_seconds)
        speaker = escape_ass_text(entry.speaker)
        text = escape_ass_text(entry.text)
        dialogue_text = rf"{{\c{NAME_COLOR_ASS}}}{speaker}:{{\r}} {text}"
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{dialogue_text}")

    return "\n".join(lines) + "\n"


def write_ass(
    timeline: tuple[LineTiming, ...],
    path: Path,
    video_width: int,
    video_height: int,
    font_name: str = DEFAULT_FONT_NAME,
    font_size: int = DEFAULT_FONT_SIZE,
) -> None:
    """Generates and writes the .ass file for `timeline`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_ass(timeline, video_width, video_height, font_name, font_size)
    path.write_text(content, encoding="utf-8")
