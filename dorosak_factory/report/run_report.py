"""Run summary: counts, durations, estimated cost, failures (INSTRUCTIONS.md 4.8/5)."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LessonOutcome:
    """What happened to one lesson during a run."""

    category_number: int
    lesson_number: int
    status: str  # "processed" | "skipped" | "failed"
    engine: str | None = None
    characters_synthesized: int = 0
    failure_reason: str | None = None


@dataclass
class RunReport:
    """Aggregates per-lesson outcomes for one `run` invocation."""

    outcomes: list[LessonOutcome] = field(default_factory=list)
    wall_time_seconds: float = 0.0

    @property
    def processed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "processed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "failed")

    def characters_by_engine(self) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for outcome in self.outcomes:
            if outcome.engine is not None:
                totals[outcome.engine] += outcome.characters_synthesized
        return dict(totals)

    def estimated_cost_by_engine(self, price_per_char: dict[str, float]) -> dict[str, float]:
        return {
            engine: chars * price_per_char.get(engine, 0.0)
            for engine, chars in self.characters_by_engine().items()
        }

    def failures(self) -> list[LessonOutcome]:
        return [o for o in self.outcomes if o.status == "failed"]

    def render_text(self, price_per_char: dict[str, float] | None = None) -> str:
        price_per_char = price_per_char or {}
        lines = [
            "Run report",
            f"  Processed: {self.processed_count}",
            f"  Skipped:   {self.skipped_count}",
            f"  Failed:    {self.failed_count}",
            f"  Wall time: {self.wall_time_seconds:.1f}s",
        ]
        chars_by_engine = self.characters_by_engine()
        if chars_by_engine:
            lines.append("  Characters synthesized:")
            for engine, chars in sorted(chars_by_engine.items()):
                cost = chars * price_per_char.get(engine, 0.0)
                lines.append(f"    {engine}: {chars} chars (~${cost:.4f})")
        if self.failed_count:
            lines.append("  Failures:")
            for outcome in self.failures():
                lines.append(
                    f"    Cat {outcome.category_number} Lesson {outcome.lesson_number}: {outcome.failure_reason}"
                )
        return "\n".join(lines)

    def render_json(self) -> str:
        return json.dumps(
            {
                "processed": self.processed_count,
                "skipped": self.skipped_count,
                "failed": self.failed_count,
                "wall_time_seconds": self.wall_time_seconds,
                "characters_by_engine": self.characters_by_engine(),
                "failures": [
                    {
                        "category": o.category_number,
                        "lesson": o.lesson_number,
                        "reason": o.failure_reason,
                    }
                    for o in self.failures()
                ],
            },
            indent=2,
        )
