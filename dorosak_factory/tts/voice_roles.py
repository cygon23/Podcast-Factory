"""Deterministic character -> abstract voice-role assignment (INSTRUCTIONS.md 4.2).

Provider voice names never appear in lesson logic; only these abstract roles
do. A character explicitly labeled "Host" (e.g. "Host (Emma)") maps directly
to the `host` role; every other character is assigned a role the first time
they speak, alternating female/male, and keeps that role for every
subsequent turn in the lesson.
"""

from __future__ import annotations

from dorosak_factory.parser.models import Lesson

NON_HOST_ROLES: tuple[str, ...] = ("female_1", "male_1", "female_2", "male_2", "neutral_1")
HOST_ROLE = "host"


def assign_voice_roles(lesson: Lesson, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Maps each speaker display name in `lesson` to an abstract voice role.

    `overrides` lets an operator pin a specific character to a specific role
    (per-lesson or per-character config), taking priority over automatic
    assignment.
    """
    overrides = overrides or {}
    roles: dict[str, str] = {}
    next_role_index = 0

    for turn in lesson.turns:
        speaker = turn.speaker
        if speaker in roles:
            continue

        if speaker in overrides:
            roles[speaker] = overrides[speaker]
            continue

        role_label = turn.raw_speaker_label.split("(")[0].strip()
        if role_label.lower() == "host":
            roles[speaker] = HOST_ROLE
            continue

        roles[speaker] = NON_HOST_ROLES[next_role_index % len(NON_HOST_ROLES)]
        next_role_index += 1

    return roles
