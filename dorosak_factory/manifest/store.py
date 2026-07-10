"""SQLite manifest: per-lesson state for idempotent reruns (INSTRUCTIONS.md 4.7).

Stores content hash, engine used, output paths, and validation status per
lesson. The main `run` command diffs the input against this manifest and
only processes new/changed/failed lessons.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dorosak_factory.parser.models import Category, Lesson

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    category_number INTEGER NOT NULL,
    lesson_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    engine TEXT NOT NULL,
    audio_path TEXT,
    video_16x9_path TEXT,
    video_9x16_path TEXT,
    srt_path TEXT,
    metadata_json_path TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    characters_synthesized INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category_number, lesson_number)
);
"""


@dataclass(frozen=True)
class ManifestRecord:
    """One lesson's recorded state in the manifest."""

    category_number: int
    lesson_number: int
    content_hash: str
    engine: str
    audio_path: str | None
    video_16x9_path: str | None
    video_9x16_path: str | None
    srt_path: str | None
    metadata_json_path: str | None
    status: str  # "success" | "failed"
    failure_reason: str | None
    characters_synthesized: int = 0
    updated_at: str | None = None


@dataclass(frozen=True)
class PlanItem:
    """One lesson's place in a planned run: process it, or skip (already up to date)."""

    category_number: int
    lesson: Lesson
    needs_processing: bool
    reason: str


class Manifest:
    """SQLite-backed store of per-lesson processing state."""

    def __init__(self, db_path: Path | None) -> None:
        self._db_path = db_path
        target = str(db_path) if db_path is not None else ":memory:"
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def compute_content_hash(lesson: Lesson) -> str:
        """SHA256 over every field that affects output, so any edit invalidates the cache."""
        parts = [
            str(lesson.number),
            lesson.title_en,
            lesson.title_ar,
            lesson.scenario,
            lesson.host_intro,
        ]
        for turn in lesson.turns:
            parts.append(turn.speaker)
            parts.extend(turn.paragraphs)
        for item in lesson.vocabulary:
            parts.append(item.term)
            parts.append(item.definition)
        raw = "\x1f".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_record(self, category_number: int, lesson_number: int) -> ManifestRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM lessons WHERE category_number = ? AND lesson_number = ?",
                (category_number, lesson_number),
            ).fetchone()
        if row is None:
            return None
        return ManifestRecord(**{key: row[key] for key in row.keys()})

    def upsert_record(self, record: ManifestRecord) -> None:
        updated_at = record.updated_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._upsert_locked(record, updated_at)

    def _upsert_locked(self, record: ManifestRecord, updated_at: str) -> None:
        self._conn.execute(
            """
            INSERT INTO lessons (
                category_number, lesson_number, content_hash, engine, audio_path,
                video_16x9_path, video_9x16_path, srt_path, metadata_json_path,
                status, failure_reason, characters_synthesized, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_number, lesson_number) DO UPDATE SET
                content_hash=excluded.content_hash,
                engine=excluded.engine,
                audio_path=excluded.audio_path,
                video_16x9_path=excluded.video_16x9_path,
                video_9x16_path=excluded.video_9x16_path,
                srt_path=excluded.srt_path,
                metadata_json_path=excluded.metadata_json_path,
                status=excluded.status,
                failure_reason=excluded.failure_reason,
                characters_synthesized=excluded.characters_synthesized,
                updated_at=excluded.updated_at
            """,
            (
                record.category_number,
                record.lesson_number,
                record.content_hash,
                record.engine,
                record.audio_path,
                record.video_16x9_path,
                record.video_9x16_path,
                record.srt_path,
                record.metadata_json_path,
                record.status,
                record.failure_reason,
                record.characters_synthesized,
                updated_at,
            ),
        )
        self._conn.commit()

    def all_records(self) -> list[ManifestRecord]:
        """Returns every record in the manifest, for status/cost-report summaries."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM lessons").fetchall()
        return [ManifestRecord(**{key: row[key] for key in row.keys()}) for row in rows]

    def needs_processing(
        self, category_number: int, lesson: Lesson, engine: str, force: bool = False
    ) -> bool:
        """True if this lesson has no successful up-to-date record for this engine."""
        if force:
            return True
        record = self.get_record(category_number, lesson.number)
        if record is None:
            return True
        if record.status != "success":
            return True
        if record.engine != engine:
            return True
        if record.content_hash != self.compute_content_hash(lesson):
            return True
        return False

    def plan_run(
        self,
        categories: list[Category],
        engine: str,
        force: bool = False,
        only_category: int | None = None,
        only_lesson: int | None = None,
    ) -> list[PlanItem]:
        """Builds the full processing plan: which lessons need work, and why."""
        plan: list[PlanItem] = []
        for category in categories:
            if only_category is not None and category.number != only_category:
                continue
            for lesson in category.lessons:
                if only_lesson is not None and lesson.number != only_lesson:
                    continue
                needs = self.needs_processing(category.number, lesson, engine, force=force)
                reason = self._describe_reason(category.number, lesson, engine, force, needs)
                plan.append(
                    PlanItem(
                        category_number=category.number,
                        lesson=lesson,
                        needs_processing=needs,
                        reason=reason,
                    )
                )
        return plan

    def _describe_reason(
        self, category_number: int, lesson: Lesson, engine: str, force: bool, needs: bool
    ) -> str:
        if not needs:
            return "up_to_date"
        if force:
            return "forced"
        record = self.get_record(category_number, lesson.number)
        if record is None:
            return "new"
        if record.status != "success":
            return "previously_failed"
        if record.engine != engine:
            return "engine_changed"
        return "content_changed"
