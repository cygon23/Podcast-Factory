"""Key Vocabulary end card: a held text screen shown after dialogue ends.

Vocabulary is never spoken (INSTRUCTIONS.md section 3) - it only appears as
this video-only text screen, per section 4.6.
"""

from __future__ import annotations

from dorosak_factory.parser.models import VocabItem
from dorosak_factory.subtitles.ass import escape_ass_text, format_ass_timestamp

DEFAULT_FONT_NAME = "Noto Sans Arabic"
DEFAULT_FONT_SIZE = 40
DEFAULT_SECONDS_PER_ITEM = 2.0
DEFAULT_MIN_SECONDS = 8.0


def compute_vocab_card_duration(
    vocabulary: tuple[VocabItem, ...],
    seconds_per_item: float = DEFAULT_SECONDS_PER_ITEM,
    min_seconds: float = DEFAULT_MIN_SECONDS,
) -> float:
    """Hold duration for the vocab card: `seconds_per_item` per term, floored at `min_seconds`."""
    return max(min_seconds, len(vocabulary) * seconds_per_item)


def generate_vocab_card_ass(
    vocabulary: tuple[VocabItem, ...],
    start_seconds: float,
    duration_seconds: float,
    video_width: int,
    video_height: int,
    font_name: str = DEFAULT_FONT_NAME,
    font_size: int = DEFAULT_FONT_SIZE,
) -> str:
    """Renders the Key Vocabulary list as one centered ASS event over [start, start+duration]."""
    header = f"""[Script Info]
Title: Dorosak Key Vocabulary Card
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Vocab,{font_name},{font_size},&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,2,1,5,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    title_line = escape_ass_text("Key Vocabulary")
    term_lines = [
        escape_ass_text(f"{item.term} — {item.definition}" if item.definition else item.term)
        for item in vocabulary
    ]
    text = rf"{{\b1}}{title_line}{{\b0}}\N\N" + r"\N".join(term_lines)

    start = format_ass_timestamp(start_seconds)
    end = format_ass_timestamp(start_seconds + duration_seconds)
    event = f"Dialogue: 0,{start},{end},Vocab,,0,0,0,,{text}"

    return header + "\n" + event + "\n"
