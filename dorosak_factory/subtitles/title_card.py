"""Episode title card: category/lesson number, English title, Arabic title.

Rendered via libass (not ffmpeg drawtext) specifically because libass shapes
Arabic (RTL, joined letterforms) correctly through HarfBuzz/FriBidi;
drawtext draws glyphs in codepoint order and would render Arabic backwards
and unjoined. Verified visually against real Arabic strings from the
sample lesson files.
"""

from __future__ import annotations

from dorosak_factory.subtitles.ass import escape_ass_text, format_ass_timestamp

DEFAULT_FONT_NAME = "Noto Sans Arabic"
DEFAULT_TITLE_FONT_SIZE = 64


def generate_title_card_ass(
    category_number: int,
    lesson_number: int,
    title_en: str,
    title_ar: str,
    video_width: int,
    video_height: int,
    display_seconds: float = 6.0,
    font_name: str = DEFAULT_FONT_NAME,
    font_size: int = DEFAULT_TITLE_FONT_SIZE,
) -> str:
    """Renders a top-centered title card shown for the first `display_seconds`."""
    header = f"""[Script Info]
Title: Dorosak Episode Title Card
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font_name},{font_size},&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,2,1,8,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    first_line = escape_ass_text(f"Cat {category_number} · Podcast {lesson_number}")
    english_line = escape_ass_text(title_en)
    arabic_line = escape_ass_text(title_ar)
    text = rf"{first_line}\N{english_line}\N{arabic_line}"

    start = format_ass_timestamp(0.0)
    end = format_ass_timestamp(display_seconds)
    event = f"Dialogue: 0,{start},{end},Title,,0,0,0,,{text}"

    return header + "\n" + event + "\n"
