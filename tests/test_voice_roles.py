"""Tests for character -> abstract voice-role assignment (INSTRUCTIONS.md 4.2).

Deterministic: Host Intro always uses `host`; other speakers get roles in
order of first appearance, alternating female/male; the same character name
always gets the same role within a lesson; manual overrides can pin roles.
"""

from __future__ import annotations

from dorosak_factory.parser.models import DialogueTurn, Lesson
from dorosak_factory.tts.voice_roles import assign_voice_roles


def make_lesson(turns):
    return Lesson(
        number=1,
        title_en="t",
        title_ar="t",
        scenario="s",
        host_intro="h",
        turns=tuple(turns),
        vocabulary=(),
        source_file="x.md",
        raw_header="## Lesson 1",
    )


def turn(speaker, raw_label=None, text="text"):
    return DialogueTurn(speaker=speaker, raw_speaker_label=raw_label or speaker, paragraphs=(text,))


def test_first_two_speakers_alternate_female_then_male():
    lesson = make_lesson([turn("Tom"), turn("Priya"), turn("Tom")])
    roles = assign_voice_roles(lesson)
    assert roles["Tom"] == "female_1"
    assert roles["Priya"] == "male_1"


def test_same_character_always_gets_same_role():
    lesson = make_lesson([turn("Tom"), turn("Priya"), turn("Tom"), turn("Priya")])
    roles = assign_voice_roles(lesson)
    assert len(roles) == 2
    assert roles["Tom"] == "female_1"
    assert roles["Priya"] == "male_1"


def test_five_distinct_speakers_get_five_distinct_roles():
    lesson = make_lesson([turn(name) for name in ["Emma", "Rosa", "Tom", "Aisha", "Marcus"]])
    roles = assign_voice_roles(lesson)
    assert len(set(roles.values())) == 5
    assert roles["Emma"] == "female_1"
    assert roles["Rosa"] == "male_1"
    assert roles["Tom"] == "female_2"
    assert roles["Aisha"] == "male_2"
    assert roles["Marcus"] == "neutral_1"


def test_speaker_labeled_host_maps_directly_to_host_role():
    lesson = make_lesson([turn("Emma", raw_label="Host (Emma)"), turn("Jake")])
    roles = assign_voice_roles(lesson)
    assert roles["Emma"] == "host"
    assert roles["Jake"] == "female_1"


def test_manual_override_pins_a_character_to_a_specific_role():
    lesson = make_lesson([turn("Tom"), turn("Priya")])
    roles = assign_voice_roles(lesson, overrides={"Priya": "neutral_1"})
    assert roles["Tom"] == "female_1"
    assert roles["Priya"] == "neutral_1"


def test_assignment_order_follows_first_appearance_not_alphabetical():
    lesson = make_lesson([turn("Zoe"), turn("Amy")])
    roles = assign_voice_roles(lesson)
    assert roles["Zoe"] == "female_1"
    assert roles["Amy"] == "male_1"
