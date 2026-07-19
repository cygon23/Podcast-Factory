"""SQLite manifest for the course audio pipeline: per-item state, additive
to the same output/manifest.sqlite3 file the cat*/Markdown pipeline uses
(dorosak_factory/manifest/store.py), in a separate table (course_items) so
neither pipeline's schema affects the other.

Per-item, not per-lesson, because 3 of the 5 content types (vocabulary,
examples, useful_phrases) produce one output file per row, not one per
lesson - a lesson-level manifest (like the cat* pipeline's) would not be
able to express "12 of this lesson's 15 vocabulary words are done, 3 are
still pending."
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS course_items (
    csv_source TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    lesson_id INTEGER NOT NULL,
    section_id TEXT NOT NULL,
    item_no INTEGER NOT NULL,
    output_path TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (csv_source, section_id, item_no)
);
"""


@dataclass(frozen=True)
class CourseItemRecord:
    """One item's (or one dialogue/article section's, item_no=0) recorded state."""

    csv_source: str  # "dialogues" | "examples" | "vocabulary" | "useful_phrases" | "articles"
    book_id: int
    unit_id: int
    lesson_id: int
    section_id: str
    item_no: int
    output_path: str | None
    status: str  # "success" | "failed"
    failure_reason: str | None
    updated_at: str | None = None


class CourseManifest:
    """SQLite-backed store of per-item processing state for the course pipeline."""

    def __init__(self, db_path: Path | None) -> None:
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

    def get_record(self, csv_source: str, section_id: str, item_no: int) -> CourseItemRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM course_items WHERE csv_source = ? AND section_id = ? AND item_no = ?",
                (csv_source, section_id, item_no),
            ).fetchone()
        if row is None:
            return None
        return CourseItemRecord(**{key: row[key] for key in row.keys()})

    def upsert_record(self, record: CourseItemRecord) -> None:
        updated_at = record.updated_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO course_items (
                    csv_source, book_id, unit_id, lesson_id, section_id, item_no,
                    output_path, status, failure_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(csv_source, section_id, item_no) DO UPDATE SET
                    book_id=excluded.book_id,
                    unit_id=excluded.unit_id,
                    lesson_id=excluded.lesson_id,
                    output_path=excluded.output_path,
                    status=excluded.status,
                    failure_reason=excluded.failure_reason,
                    updated_at=excluded.updated_at
                """,
                (
                    record.csv_source,
                    record.book_id,
                    record.unit_id,
                    record.lesson_id,
                    record.section_id,
                    record.item_no,
                    record.output_path,
                    record.status,
                    record.failure_reason,
                    updated_at,
                ),
            )
            self._conn.commit()

    def needs_processing(self, csv_source: str, section_id: str, item_no: int, force: bool = False) -> bool:
        if force:
            return True
        record = self.get_record(csv_source, section_id, item_no)
        return record is None or record.status != "success"

    def all_records(self) -> list[CourseItemRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM course_items").fetchall()
        return [CourseItemRecord(**{key: row[key] for key in row.keys()}) for row in rows]
