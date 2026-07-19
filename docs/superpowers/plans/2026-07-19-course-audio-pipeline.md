# Course Audio Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new, additive `dorosak_factory/course/` pipeline that turns Dorosak's 5 course-catalog CSVs (dialogues, examples, vocabulary, useful_phrases, articles — ~200 lessons across 4 book levels) into audio, skipping any row that already has real recorded audio, then produce one pilot lesson's output for team review before any full batch run.

**Architecture:** New parser (CSV → dataclasses), a new local Arabic TTS adapter (Piper, MIT-licensed voice), new per-content-type assembly functions, and a new SQLite manifest table — all reusing the existing `TTSEngine` registry, per-line cache, loudness normalization, and MP3 export exactly as-is. Nothing in the existing `cat*`/Markdown pipeline (parser, `pipeline.py`, video renderer, CLI `run`/`status`/`validate`/`cost-report`) is modified in a way that changes its behavior — only new files and new, additive config/CLI surface.

**Tech Stack:** Python 3.11+, `piper-tts` (new dependency), existing `dorosak_factory` internals (`tts.registry`, `audio.cache`, `audio.loudness`, `audio.wav_utils`, `audio.mp3_export`), `pytest`, real `ffmpeg`/`ffprobe`.

Reference: `docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md` (approved design).

---

### Task 1: Shared CSV test-fixture helper

**Files:**
- Create: `tests/course_fixtures.py`
- Test: `tests/test_course_fixtures.py`

The 5 real CSVs share one 34-column header. Hand-writing raw CSV text with exact comma counts is error-prone, so this helper builds rows from keyword arguments instead.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_fixtures.py
from __future__ import annotations

import csv
import io

from tests.course_fixtures import CSV_HEADER, csv_row


def test_csv_row_round_trips_through_csv_dictreader():
    text = CSV_HEADER + "\n" + csv_row(item_no=1, item_text="Hello.") + "\n"
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["item_no"] == "1"
    assert rows[0]["item_text"] == "Hello."
    assert set(rows[0].keys()) == set(CSV_HEADER.split(","))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_fixtures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.course_fixtures'`

- [ ] **Step 3: Write the fixture helper**

```python
# tests/course_fixtures.py
"""Builds one row of the 5 course CSVs' shared 34-column header from keyword
arguments, so tests never hand-count commas in raw CSV text.
"""

from __future__ import annotations

CSV_HEADER = (
    "book_id,book_name,unit_id,unit_name,unit_sort,lesson_id,lesson_name,lesson_sort,"
    "page_id,page_title,page_index,page_sort,section_id,section_title,section_type,"
    "section_sort,locale,item_no,item_text,item_audio_link,item_video_link,content_text,"
    "content_html,section_audio_link,section_video_link,image_link,reference_link,"
    "reference_text,quiz_id,page_created_at,page_updated_at,section_created_at,"
    "section_updated_at,content_missing"
)


def csv_row(
    book_id: int = 1,
    book_name: str = "Mastering English with Dorosak (Beginner)",
    unit_id: int = 6,
    unit_name: str = "Unit 1: Basics",
    unit_sort: int = 1,
    lesson_id: int = 20,
    lesson_name: str = "Lesson 1: Alphabet Basics",
    lesson_sort: int = 1,
    page_id: int = 60,
    page_title: str = "Dialogue",
    page_index: int = 7,
    page_sort: int = 7,
    section_id: str = "74",
    section_title: str = "Dialogue",
    section_type: str = "text",
    section_sort: int = 0,
    locale: str = "en",
    item_no: int = 1,
    item_text: str = "",
    item_audio_link: str = "",
    item_video_link: str = "",
    content_text: str = "",
    content_html: str = "",
    section_audio_link: str = "",
    section_video_link: str = "",
    image_link: str = "",
    reference_link: str = "",
    reference_text: str = "",
    quiz_id: str = "",
    page_created_at: str = "",
    page_updated_at: str = "",
    section_created_at: str = "",
    section_updated_at: str = "",
    content_missing: int = 0,
) -> str:
    """Returns one CSV data row (no trailing newline) matching CSV_HEADER's column order.

    No field used across this test suite contains a comma, so plain
    comma-joining is safe - no CSV quoting/escaping needed.
    """
    fields = [
        book_id, book_name, unit_id, unit_name, unit_sort, lesson_id, lesson_name,
        lesson_sort, page_id, page_title, page_index, page_sort, section_id,
        section_title, section_type, section_sort, locale, item_no, item_text,
        item_audio_link, item_video_link, content_text, content_html,
        section_audio_link, section_video_link, image_link, reference_link,
        reference_text, quiz_id, page_created_at, page_updated_at,
        section_created_at, section_updated_at, content_missing,
    ]
    return ",".join(str(f) for f in fields)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_fixtures.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/course_fixtures.py tests/test_course_fixtures.py
git commit -m "test: add course CSV fixture-row builder for course pipeline tests"
```

---

### Task 2: Course content models

**Files:**
- Create: `dorosak_factory/course/__init__.py` (empty)
- Create: `dorosak_factory/course/models.py`
- Test: `tests/test_course_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_models.py
from __future__ import annotations

from dorosak_factory.course.models import (
    ArticleSection,
    BilingualItem,
    BilingualSection,
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    PhraseItem,
    PhraseSection,
    Unit,
)


def _book_unit_lesson():
    book = Book(book_id=1, name="Mastering English with Dorosak (Beginner)")
    unit = Unit(unit_id=6, book_id=1, name="Unit 1: Basics")
    lesson = CourseLesson(lesson_id=20, unit_id=6, book_id=1, name="Lesson 1: Alphabet Basics")
    return book, unit, lesson


def test_dialogue_section_holds_ordered_lines():
    book, unit, lesson = _book_unit_lesson()
    lines = (
        DialogueLine(item_no=1, speaker="Teacher", text="Welcome."),
        DialogueLine(item_no=2, speaker="Student", text="Hello."),
    )
    section = DialogueSection(book=book, unit=unit, lesson=lesson, lines=lines)
    assert section.lines[0].speaker == "Teacher"
    assert section.lesson.name == "Lesson 1: Alphabet Basics"


def test_bilingual_section_holds_english_arabic_pairs():
    book, unit, lesson = _book_unit_lesson()
    items = (BilingualItem(item_no=1, english="Alphabet", arabic="الأبجدية"),)
    section = BilingualSection(book=book, unit=unit, lesson=lesson, items=items)
    assert section.items[0].english == "Alphabet"
    assert section.items[0].arabic == "الأبجدية"


def test_phrase_section_holds_plain_text_items():
    book, unit, lesson = _book_unit_lesson()
    items = (PhraseItem(item_no=1, text="How do you say this?"),)
    section = PhraseSection(book=book, unit=unit, lesson=lesson, items=items)
    assert section.items[0].text == "How do you say this?"


def test_article_section_holds_one_passage():
    book, unit, lesson = _book_unit_lesson()
    section = ArticleSection(book=book, unit=unit, lesson=lesson, text="The alphabet is...")
    assert section.text == "The alphabet is..."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dorosak_factory.course'`

- [ ] **Step 3: Write the models**

```python
# dorosak_factory/course/models.py
"""Content models for the course CSV audio pipeline.

Deliberately separate from dorosak_factory.parser.models (Category/Lesson/
DialogueTurn/VocabItem) - those model the cat*/Markdown "English for X"
podcast pipeline. These model Dorosak's actual course catalog (book/unit/
lesson/section, 5 distinct content shapes per lesson), sourced from a CSV
export rather than Markdown. Kept separate rather than shared because
forcing one model to fit both would blur two genuinely different content
shapes into an awkward compromise.

Vocabulary and Examples share a shape (English/Arabic pairs) and so share
BilingualItem/BilingualSection; Useful Phrases (English-only) and Article
(one passage, no per-item list) each get their own shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    book_id: int
    name: str


@dataclass(frozen=True)
class Unit:
    unit_id: int
    book_id: int
    name: str


@dataclass(frozen=True)
class CourseLesson:
    lesson_id: int
    unit_id: int
    book_id: int
    name: str


@dataclass(frozen=True)
class DialogueLine:
    item_no: int
    speaker: str  # "Teacher" | "Student"
    text: str


@dataclass(frozen=True)
class DialogueSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    lines: tuple[DialogueLine, ...]


@dataclass(frozen=True)
class BilingualItem:
    """One vocabulary word or example sentence, paired with its Arabic translation."""

    item_no: int
    english: str
    arabic: str


@dataclass(frozen=True)
class BilingualSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    items: tuple[BilingualItem, ...]


@dataclass(frozen=True)
class PhraseItem:
    item_no: int
    text: str


@dataclass(frozen=True)
class PhraseSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    items: tuple[PhraseItem, ...]


@dataclass(frozen=True)
class ArticleSection:
    book: Book
    unit: Unit
    lesson: CourseLesson
    text: str
```

Also create the empty package marker:

```python
# dorosak_factory/course/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/__init__.py dorosak_factory/course/models.py tests/test_course_models.py
git commit -m "feat: add course content models (Book/Unit/CourseLesson + per-content-type shapes)"
```

---

### Task 3: Add `CourseConfig` (additive to `config.py`)

**Files:**
- Modify: `dorosak_factory/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Read the existing test file to match its conventions**

Run: `cat tests/test_config.py` (or open it) — find where existing `Config`/section tests live so the new test is appended in the same style, not to guess formatting blind.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_default_config_includes_course_section_with_expected_defaults():
    from dorosak_factory.config import Config

    config = Config()
    assert config.course.teacher_voice_role == "host"
    assert config.course.narrator_voice_role == "host"
    assert config.course.arabic_voice_role == "arabic_narrator"
    assert config.course.bilingual_gap_ms == 1000
    assert config.course.student_voice_by_book["Mastering English with Dorosak (Beginner)"] == "female_1"


def test_load_config_resolves_course_paths_against_base_dir(tmp_path):
    from dorosak_factory.config import load_config

    config = load_config(path=None, base_dir=tmp_path)
    assert config.course.csv_dir == tmp_path / "input" / "course_csv"
    assert config.course.output_dir == tmp_path / "output" / "course"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -k course -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'course'`

- [ ] **Step 4: Add `CourseConfig`**

In `dorosak_factory/config.py`, add this new dataclass after `PipelineConfig` (before the `Config` class):

```python
@dataclass(frozen=True)
class CourseConfig:
    """Course CSV audio pipeline settings - additive, separate from the
    cat*/Markdown pipeline's config sections above. See
    docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md."""

    csv_dir: Path = Path("input/course_csv")
    output_dir: Path = Path("output/course")
    teacher_voice_role: str = "host"
    narrator_voice_role: str = "host"
    arabic_voice_role: str = "arabic_narrator"
    bilingual_gap_ms: int = 1000
    # Real book_name strings from the CSV export have irregular spacing
    # (extra/missing spaces around parentheses) - keys must match exactly,
    # do not "clean up" this spacing.
    student_voice_by_book: dict[str, str] = field(
        default_factory=lambda: {
            "Mastering English with Dorosak (Beginner)": "female_1",
            "Mastering English with Dorosak (Elementary)": "male_1",
            "Mastering English with Dorosak ( intermediate)": "female_2",
            "Mastering English with Dorosak  (Advanced)": "male_2",
        }
    )
```

Modify the `Config` dataclass to add the new field:

```python
@dataclass(frozen=True)
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    manifest: ManifestConfig = field(default_factory=ManifestConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    course: CourseConfig = field(default_factory=CourseConfig)
```

In `load_config()`, right before the final `return Config(...)` line, add:

```python
    course_raw = dict(raw.get("course", {}))
    course_raw["csv_dir"] = _resolve_path(course_raw.get("csv_dir", "input/course_csv"), base_dir)
    course_raw["output_dir"] = _resolve_path(course_raw.get("output_dir", "output/course"), base_dir)
    course = CourseConfig(**course_raw)
```

And update the return statement:

```python
    return Config(
        audio=audio, tts=tts, video=video, manifest=manifest, pipeline=pipeline, course=course
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS, all tests (existing + new) pass

- [ ] **Step 6: Commit**

```bash
git add dorosak_factory/config.py tests/test_config.py
git commit -m "feat: add CourseConfig (additive) for the course audio pipeline"
```

---

### Task 4: CSV parser shared helpers + `parse_dialogues_csv`

**Files:**
- Create: `dorosak_factory/course/csv_parser.py`
- Test: `tests/test_course_csv_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_csv_parser.py
from __future__ import annotations

from pathlib import Path

from tests.course_fixtures import CSV_HEADER, csv_row


def _write_csv(tmp_path: Path, name: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_parse_dialogues_csv_groups_lines_by_section_in_item_no_order(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(section_id="74", item_no=2, item_text="Student: Hello, teacher."),
        csv_row(section_id="74", item_no=1, item_text="Teacher: Welcome to class."),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert len(sections) == 1
    assert [line.item_no for line in sections[0].lines] == [1, 2]
    assert sections[0].lines[0].speaker == "Teacher"
    assert sections[0].lines[0].text == "Welcome to class."
    assert sections[0].lines[1].speaker == "Student"
    assert sections[0].book.name == "Mastering English with Dorosak (Beginner)"
    assert sections[0].lesson.lesson_id == 20


def test_parse_dialogues_csv_separates_multiple_lessons(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(section_id="74", lesson_id=20, item_no=1, item_text="Teacher: Hi."),
        csv_row(section_id="80", lesson_id=21, item_no=1, item_text="Teacher: Bye."),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert {s.lesson.lesson_id for s in sections} == {20, 21}


def test_parse_dialogues_csv_skips_section_with_existing_section_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_dialogues_csv

    rows = [
        csv_row(
            section_id="74",
            item_no=1,
            item_text="Teacher: Hi.",
            section_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
    ]
    path = _write_csv(tmp_path, "dialogues.csv", rows)

    sections = parse_dialogues_csv(path)

    assert sections == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dorosak_factory.course.csv_parser'`

- [ ] **Step 3: Write the parser (shared helpers + dialogues)**

```python
# dorosak_factory/course/csv_parser.py
"""Parses the 5 Dorosak course CSVs into course/models.py dataclasses.

Groups rows by section (book_id, unit_id, lesson_id, section_id all appear
duplicated on every row of a section, mirroring the real CSV export) and
skips rows that already have real recorded audio - see the "existing
audio" finding in docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md.

Dialogues skip at the whole-section level (section_audio_link marks one
combined recording for the whole conversation - individual lines are
never separately recorded). Vocabulary/Examples/Useful Phrases skip at
the individual-item level (item_audio_link marks one specific word/
sentence as already recorded, independent of its siblings in the section).
"""

from __future__ import annotations

import csv
from pathlib import Path

from dorosak_factory.course.models import (
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    Unit,
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _has_existing_audio(row: dict[str, str]) -> bool:
    return bool(row["item_audio_link"].strip()) or bool(row["section_audio_link"].strip())


def _book_unit_lesson(row: dict[str, str]) -> tuple[Book, Unit, CourseLesson]:
    book = Book(book_id=int(row["book_id"]), name=row["book_name"])
    unit = Unit(unit_id=int(row["unit_id"]), book_id=book.book_id, name=row["unit_name"])
    lesson = CourseLesson(
        lesson_id=int(row["lesson_id"]),
        unit_id=unit.unit_id,
        book_id=book.book_id,
        name=row["lesson_name"],
    )
    return book, unit, lesson


def _group_by_section(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["section_id"], []).append(row)
    return groups


def parse_dialogues_csv(path: Path) -> list[DialogueSection]:
    """Parses dialogues.csv: one DialogueSection per lesson's Teacher/Student conversation."""
    rows = _read_rows(path)
    sections: list[DialogueSection] = []
    for section_rows in _group_by_section(rows).values():
        if any(_has_existing_audio(r) for r in section_rows):
            continue
        book, unit, lesson = _book_unit_lesson(section_rows[0])
        ordered = sorted(section_rows, key=lambda r: int(r["item_no"]))
        lines = tuple(_parse_dialogue_line(r) for r in ordered)
        sections.append(DialogueSection(book=book, unit=unit, lesson=lesson, lines=lines))
    return sections


def _parse_dialogue_line(row: dict[str, str]) -> DialogueLine:
    speaker, _, text = row["item_text"].partition(":")
    return DialogueLine(item_no=int(row["item_no"]), speaker=speaker.strip(), text=text.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/csv_parser.py tests/test_course_csv_parser.py
git commit -m "feat: add course CSV parser with parse_dialogues_csv"
```

---

### Task 5: Bilingual split helpers + `parse_vocabulary_csv` / `parse_examples_csv`

**Files:**
- Modify: `dorosak_factory/course/csv_parser.py`
- Modify: `tests/test_course_csv_parser.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_course_csv_parser.py`:

```python
def test_split_bilingual_dash_separates_english_and_arabic():
    from dorosak_factory.course.csv_parser import split_bilingual_dash

    english, arabic = split_bilingual_dash("This is the letter A. — هذا هو الحرف A.")
    assert english == "This is the letter A."
    assert arabic == "هذا هو الحرف A."


def test_split_bilingual_tab_separates_english_and_arabic():
    from dorosak_factory.course.csv_parser import split_bilingual_tab

    english, arabic = split_bilingual_tab("Alphabet\tالأبجدية")
    assert english == "Alphabet"
    assert arabic == "الأبجدية"


def test_parse_examples_csv_splits_dash_separated_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_examples_csv

    rows = [
        csv_row(
            section_id="75",
            item_no=1,
            item_text="This is the letter A. — هذا هو الحرف A.",
        ),
    ]
    path = _write_csv(tmp_path, "examples.csv", rows)

    sections = parse_examples_csv(path)

    assert len(sections) == 1
    assert sections[0].items[0].english == "This is the letter A."
    assert sections[0].items[0].arabic == "هذا هو الحرف A."


def test_parse_vocabulary_csv_splits_tab_separated_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_vocabulary_csv

    rows = [csv_row(section_id="77", item_no=1, item_text="Alphabet\tالأبجدية")]
    path = _write_csv(tmp_path, "vocabulary.csv", rows)

    sections = parse_vocabulary_csv(path)

    assert sections[0].items[0].english == "Alphabet"
    assert sections[0].items[0].arabic == "الأبجدية"


def test_parse_vocabulary_csv_skips_only_items_with_existing_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_vocabulary_csv

    rows = [
        csv_row(
            section_id="77",
            item_no=1,
            item_text="Alphabet\tالأبجدية",
            item_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
        csv_row(section_id="77", item_no=2, item_text="Letter\tحرف"),
    ]
    path = _write_csv(tmp_path, "vocabulary.csv", rows)

    sections = parse_vocabulary_csv(path)

    assert len(sections) == 1
    assert len(sections[0].items) == 1
    assert sections[0].items[0].english == "Letter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'split_bilingual_dash'`

- [ ] **Step 3: Add the bilingual helpers and parsers**

Append to `dorosak_factory/course/csv_parser.py` (add `BilingualItem, BilingualSection` to the existing import line at the top from `dorosak_factory.course.models`):

```python
from dorosak_factory.course.models import (
    BilingualItem,
    BilingualSection,
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    Unit,
)
```

Then append these functions to the file:

```python
def split_bilingual_dash(text: str) -> tuple[str, str]:
    """Splits "English sentence — Arabic translation" on the em-dash separator."""
    english, _, arabic = text.partition(" — ")
    return english.strip(), arabic.strip()


def split_bilingual_tab(text: str) -> tuple[str, str]:
    """Splits "English word\tArabic translation" on the tab separator."""
    english, _, arabic = text.partition("\t")
    return english.strip(), arabic.strip()


def _parse_bilingual_csv(path: Path, split_fn) -> list[BilingualSection]:
    rows = _read_rows(path)
    sections: list[BilingualSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        items = tuple(_parse_bilingual_item(r, split_fn) for r in ordered)
        sections.append(BilingualSection(book=book, unit=unit, lesson=lesson, items=items))
    return sections


def _parse_bilingual_item(row: dict[str, str], split_fn) -> BilingualItem:
    english, arabic = split_fn(row["item_text"])
    return BilingualItem(item_no=int(row["item_no"]), english=english, arabic=arabic)


def parse_examples_csv(path: Path) -> list[BilingualSection]:
    """Parses examples.csv: "English — Arabic" sentence pairs, grouped per lesson."""
    return _parse_bilingual_csv(path, split_bilingual_dash)


def parse_vocabulary_csv(path: Path) -> list[BilingualSection]:
    """Parses vocabulary.csv: "English\\tArabic" word pairs, grouped per lesson."""
    return _parse_bilingual_csv(path, split_bilingual_tab)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/csv_parser.py tests/test_course_csv_parser.py
git commit -m "feat: add bilingual split helpers, parse_vocabulary_csv, parse_examples_csv"
```

---

### Task 6: `parse_useful_phrases_csv` + `parse_articles_csv`

**Files:**
- Modify: `dorosak_factory/course/csv_parser.py`
- Modify: `tests/test_course_csv_parser.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_course_csv_parser.py`:

```python
def test_parse_useful_phrases_csv_keeps_plain_text_items(tmp_path):
    from dorosak_factory.course.csv_parser import parse_useful_phrases_csv

    rows = [
        csv_row(section_id="76", item_no=1, item_text="This is a letter."),
        csv_row(section_id="76", item_no=2, item_text="These are letters."),
    ]
    path = _write_csv(tmp_path, "useful_phrases.csv", rows)

    sections = parse_useful_phrases_csv(path)

    assert len(sections[0].items) == 2
    assert sections[0].items[0].text == "This is a letter."


def test_parse_articles_csv_uses_content_text_not_item_text(tmp_path):
    from dorosak_factory.course.csv_parser import parse_articles_csv

    rows = [
        csv_row(
            section_id="78",
            item_no=1,
            item_text="Article (Alphabet Basics)",
            content_text="The English alphabet is the foundation of the language.",
        ),
    ]
    path = _write_csv(tmp_path, "articles.csv", rows)

    sections = parse_articles_csv(path)

    assert len(sections) == 1
    assert sections[0].text == "The English alphabet is the foundation of the language."


def test_parse_articles_csv_skips_rows_with_existing_audio(tmp_path):
    from dorosak_factory.course.csv_parser import parse_articles_csv

    rows = [
        csv_row(
            section_id="78",
            item_no=1,
            content_text="Already recorded article.",
            item_audio_link="https://dorosak-english.s3.amazonaws.com/already-recorded.wav",
        ),
    ]
    path = _write_csv(tmp_path, "articles.csv", rows)

    sections = parse_articles_csv(path)

    assert sections == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_useful_phrases_csv'`

- [ ] **Step 3: Add the two parsers**

Update the import line at the top of `dorosak_factory/course/csv_parser.py` to also bring in `ArticleSection, PhraseItem, PhraseSection`:

```python
from dorosak_factory.course.models import (
    ArticleSection,
    BilingualItem,
    BilingualSection,
    Book,
    CourseLesson,
    DialogueLine,
    DialogueSection,
    PhraseItem,
    PhraseSection,
    Unit,
)
```

Append to the file:

```python
def parse_useful_phrases_csv(path: Path) -> list[PhraseSection]:
    """Parses useful_phrases.csv: plain English phrases, grouped per lesson."""
    rows = _read_rows(path)
    sections: list[PhraseSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        items = tuple(
            PhraseItem(item_no=int(r["item_no"]), text=r["item_text"].strip()) for r in ordered
        )
        sections.append(PhraseSection(book=book, unit=unit, lesson=lesson, items=items))
    return sections


def parse_articles_csv(path: Path) -> list[ArticleSection]:
    """Parses articles.csv: one reading passage per lesson.

    Unlike the other 4 CSVs, the spoken content lives in `content_text`
    (the article body), not `item_text` (just a short title like
    "Article (Alphabet Basics)").
    """
    rows = _read_rows(path)
    sections: list[ArticleSection] = []
    for section_rows in _group_by_section(rows).values():
        kept_rows = [r for r in section_rows if not _has_existing_audio(r)]
        if not kept_rows:
            continue
        book, unit, lesson = _book_unit_lesson(kept_rows[0])
        ordered = sorted(kept_rows, key=lambda r: int(r["item_no"]))
        text = " ".join(r["content_text"].strip() for r in ordered if r["content_text"].strip())
        sections.append(ArticleSection(book=book, unit=unit, lesson=lesson, text=text))
    return sections
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_csv_parser.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/csv_parser.py tests/test_course_csv_parser.py
git commit -m "feat: add parse_useful_phrases_csv and parse_articles_csv"
```

---

### Task 7: `PiperEngine` TTS adapter (local Arabic voice)

**Files:**
- Create: `dorosak_factory/tts/engines/piper_engine.py`
- Modify: `dorosak_factory/tts/engines/__init__.py`
- Modify: `requirements.txt`
- Test: `tests/test_piper_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_piper_engine.py
"""Tests for the Piper (local) Arabic TTS adapter.

Mirrors tests/test_kokoro_engine.py's pattern: is_available/from_config are
tested for real (no model needed), synthesize() is tested with PiperVoice
mocked at the boundary (real voice weights are not committed to the repo -
that's the operator's job, same as Kokoro's model weights).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dorosak_factory.tts.engines.piper_engine import PiperEngine


def _make_voice_files(tmp_path):
    onnx_path = tmp_path / "ar_JO-kareem-medium.onnx"
    onnx_path.write_bytes(b"fake")
    (tmp_path / "ar_JO-kareem-medium.onnx.json").write_text("{}")
    return onnx_path


def test_is_available_false_without_configured_path():
    assert PiperEngine.is_available({}) is False


def test_is_available_false_when_onnx_file_missing(tmp_path):
    env = {"PIPER_AR_VOICE_PATH": str(tmp_path / "missing.onnx")}
    assert PiperEngine.is_available(env) is False


def test_is_available_false_when_config_json_missing(tmp_path):
    onnx_path = tmp_path / "voice.onnx"
    onnx_path.write_bytes(b"fake")
    # .onnx.json deliberately not created
    env = {"PIPER_AR_VOICE_PATH": str(onnx_path)}
    assert PiperEngine.is_available(env) is False


def test_is_available_true_when_package_importable_and_files_exist(tmp_path):
    onnx_path = _make_voice_files(tmp_path)
    env = {"PIPER_AR_VOICE_PATH": str(onnx_path)}
    assert PiperEngine.is_available(env) is True


@patch("piper.PiperVoice")
def test_synthesize_writes_a_24khz_wav(mock_piper_voice_cls, tmp_path):
    def fake_synthesize_wav(text, wav_file):
        import wave

        with wave.open(wav_file if hasattr(wav_file, "write") else str(wav_file), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00\x00" * 1000)

    mock_voice = MagicMock()
    mock_voice.synthesize_wav.side_effect = fake_synthesize_wav
    mock_piper_voice_cls.load.return_value = mock_voice

    onnx_path = _make_voice_files(tmp_path)
    engine = PiperEngine(voice_path=onnx_path, work_dir=tmp_path / "out")

    result = engine.synthesize("مرحبا", voice_role="arabic_narrator")

    assert result.wav_path.exists()
    assert result.engine == "piper"
    import wave

    with wave.open(str(result.wav_path), "rb") as w:
        assert w.getframerate() == 24000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_piper_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dorosak_factory.tts.engines.piper_engine'`

- [ ] **Step 3: Add `piper-tts` to requirements and write the adapter**

Add this line to `requirements.txt`:

```
piper-tts
```

Create `dorosak_factory/tts/engines/piper_engine.py`:

```python
"""Piper TTS adapter: local, free, Arabic voice for the course audio pipeline.

Piper (`pip install piper-tts`) is GPL-3.0 (fine here - we run it as a
tool, don't redistribute modified Piper source, and GPL doesn't restrict
the audio *output* it produces). The Arabic voice model itself
(`rhasspy/piper-voices` on Hugging Face, e.g. the `ar_JO` family) is
separately MIT-licensed - no commercial-use conflict, unlike
facebook/mms-tts-ara which is CC-BY-NC (rejected for this reason - see
docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md).

This adapter never downloads anything itself: the operator downloads a
voice's .onnx + .onnx.json pair and points PIPER_AR_VOICE_PATH at the
.onnx file - same pattern as Kokoro's KOKORO_MODEL_PATH.

Unlike Kokoro, Piper's native sample rate is not 24kHz, so synthesize()
always resamples its raw output through convert_to_pipeline_wav before
returning - every other engine in this pipeline assumes 24kHz mono
16-bit PCM WAV (see audio/wav_utils.py's module docstring); skipping this
step would corrupt concatenation with Kokoro-produced audio.
"""

from __future__ import annotations

import hashlib
import wave
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from dorosak_factory.audio.wav_utils import convert_to_pipeline_wav, read_wav_duration_seconds
from dorosak_factory.tts.base import Capabilities, SynthesisResult, TTSEngine

if TYPE_CHECKING:
    from dorosak_factory.config import Config


class PiperEngine(TTSEngine):
    """Adapter for a local Piper voice model - used for the Arabic half of
    course vocabulary/examples/useful-phrases audio."""

    name = "piper"

    DEFAULT_VOICE_MAP = {
        "arabic_narrator": "ar_JO-kareem-medium",
    }

    def __init__(
        self,
        voice_path: Path,
        work_dir: Path,
        voice_map: dict[str, str] | None = None,
    ) -> None:
        from piper import PiperVoice

        self._voice = PiperVoice.load(str(voice_path))
        self._voice_map = {**self.DEFAULT_VOICE_MAP, **(voice_map or {})}
        self._work_dir = Path(work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_available(cls, env: Mapping[str, str]) -> bool:
        import importlib.util

        if importlib.util.find_spec("piper") is None:
            return False
        voice_path = env.get("PIPER_AR_VOICE_PATH")
        if not voice_path:
            return False
        onnx_path = Path(voice_path)
        config_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
        return onnx_path.exists() and config_path.exists()

    @classmethod
    def availability_hint(cls) -> str:
        return (
            "Install piper-tts (`pip install piper-tts`), download an Arabic "
            "voice's .onnx + .onnx.json pair from rhasspy/piper-voices on "
            "Hugging Face (e.g. the ar_JO family), and set PIPER_AR_VOICE_PATH "
            "in .env to the .onnx file."
        )

    @classmethod
    def from_config(cls, config: "Config") -> "PiperEngine":
        import os

        return cls(
            voice_path=Path(os.environ["PIPER_AR_VOICE_PATH"]),
            work_dir=config.audio.work_dir / "piper_raw",
            voice_map=config.tts.voice_map.get(cls.name, {}),
        )

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(supports_speed=False, supports_ssml=False)

    def synthesize(self, text: str, voice_role: str, speed: float = 1.0) -> SynthesisResult:
        voice_id = self._voice_map.get(voice_role, voice_role)
        raw_path = self._path_for(text, voice_id, suffix="_raw")
        with wave.open(str(raw_path), "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file)

        output_path = self._path_for(text, voice_id, suffix="")
        convert_to_pipeline_wav(raw_path, output_path)

        return SynthesisResult(
            wav_path=output_path,
            duration_seconds=read_wav_duration_seconds(output_path),
            characters=len(text),
            engine=self.name,
            voice_role=voice_role,
        )

    def _path_for(self, key_text: str, voice_id: str, suffix: str) -> Path:
        cache_key = f"{self.name}|{voice_id}|{key_text}{suffix}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self._work_dir / f"{digest}{suffix}.wav"
```

Register it in `dorosak_factory/tts/engines/__init__.py` — add the import and one registration line (do not touch the existing 7 lines already there):

```python
from dorosak_factory.tts.engines.piper_engine import PiperEngine
```

```python
default_registry.register(PiperEngine)
```

And add `"PiperEngine"` to the `__all__` list at the bottom of that file.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_piper_engine.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full existing TTS test suite to confirm nothing broke**

Run: `python -m pytest tests/test_kokoro_engine.py tests/ -k "registry or engine" -v`
Expected: PASS, all existing engine/registry tests still pass unchanged

- [ ] **Step 6: Commit**

```bash
git add dorosak_factory/tts/engines/piper_engine.py dorosak_factory/tts/engines/__init__.py requirements.txt tests/test_piper_engine.py
git commit -m "feat: add PiperEngine (local, MIT-licensed Arabic TTS adapter)"
```

---

### Task 8: `synthesize_bilingual_item` (vocabulary/examples/phrases assembly)

**Files:**
- Create: `dorosak_factory/course/assembly.py`
- Test: `tests/test_course_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_assembly.py
"""Tests for course audio assembly: real ffmpeg, real NullEngine (no
network, no cost) - same testing philosophy as tests/test_video_builder.py
and tests/test_audio_assembly.py for the cat*/Markdown pipeline.
"""

from __future__ import annotations

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import AudioConfig, CourseConfig
from dorosak_factory.course.models import BilingualItem
from dorosak_factory.media_probe import probe_duration_seconds
from dorosak_factory.tts.engines.null_engine import NullEngine


def test_synthesize_bilingual_item_produces_one_mp3_with_a_silence_gap(tmp_path):
    from dorosak_factory.course.assembly import synthesize_bilingual_item

    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "work")
    course_config = CourseConfig(bilingual_gap_ms=1000)
    cache = LineCache(cache_dir=audio_config.cache_dir)
    english_engine = NullEngine(output_dir=tmp_path / "en_raw")
    arabic_engine = NullEngine(output_dir=tmp_path / "ar_raw")

    item = BilingualItem(item_no=1, english="Alphabet", arabic="الأبجدية")
    output_path = tmp_path / "item.mp3"

    synthesize_bilingual_item(
        item,
        english_engine=english_engine,
        arabic_engine=arabic_engine,
        cache=cache,
        audio_config=audio_config,
        course_config=course_config,
        output_mp3_path=output_path,
        work_dir=tmp_path / "item_work",
        narrator_voice_role="host",
    )

    assert output_path.exists()
    english_only_duration = probe_duration_seconds(
        english_engine.synthesize("Alphabet", voice_role="host").wav_path
    )
    arabic_only_duration = probe_duration_seconds(
        arabic_engine.synthesize("الأبجدية", voice_role="arabic_narrator").wav_path
    )
    combined_duration = probe_duration_seconds(output_path)
    # combined >= english + gap + arabic (loudnorm/mp3 encoding can shift
    # duration slightly, so this checks the gap was really inserted rather
    # than asserting an exact value).
    assert combined_duration >= english_only_duration + arabic_only_duration + 0.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dorosak_factory.course.assembly'`

- [ ] **Step 3: Write the assembly module (bilingual item synthesis)**

```python
# dorosak_factory/course/assembly.py
"""Synthesizes and assembles course audio: bilingual item clips
(vocabulary, examples, useful phrases), multi-voice dialogue episodes, and
single-narrator article readings.

Reuses the same low-level building blocks as the cat*/Markdown pipeline
(LineCache, wav_utils, loudness normalization, MP3 export) but with its
own top-level functions, since course/models.py's shapes
(DialogueSection/BilingualSection/...) don't match parser.models.Lesson.
"""

from __future__ import annotations

from pathlib import Path

from dorosak_factory.audio.cache import LineCache
from dorosak_factory.audio.loudness import normalize_loudness
from dorosak_factory.audio.mp3_export import ID3Tags, export_mp3
from dorosak_factory.audio.wav_utils import concat_wavs, write_silence_wav
from dorosak_factory.config import AudioConfig, CourseConfig
from dorosak_factory.course.models import BilingualItem
from dorosak_factory.tts.base import TTSEngine


def synthesize_bilingual_item(
    item: BilingualItem,
    english_engine: TTSEngine,
    arabic_engine: TTSEngine,
    cache: LineCache,
    audio_config: AudioConfig,
    course_config: CourseConfig,
    output_mp3_path: Path,
    work_dir: Path,
    narrator_voice_role: str,
) -> Path:
    """English clip + silence gap + Arabic clip, concatenated into one MP3.

    Matches the measured real-recording pattern (see design spec): two
    speech segments separated by course_config.bilingual_gap_ms of silence.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    english_result = cache.get_or_synthesize(
        english_engine,
        item.english,
        voice_role=narrator_voice_role,
        model="default",
        voice_id=narrator_voice_role,
    )
    arabic_result = cache.get_or_synthesize(
        arabic_engine,
        item.arabic,
        voice_role=course_config.arabic_voice_role,
        model="default",
        voice_id=course_config.arabic_voice_role,
    )

    gap_path = work_dir / f"gap_{item.item_no}.wav"
    write_silence_wav(gap_path, course_config.bilingual_gap_ms / 1000.0)

    combined_path = work_dir / f"combined_{item.item_no}.wav"
    concat_wavs([english_result.wav_path, gap_path, arabic_result.wav_path], combined_path)

    normalized_path = work_dir / f"normalized_{item.item_no}.wav"
    normalize_loudness(
        combined_path,
        normalized_path,
        target_lufs=audio_config.loudness.target_lufs,
        target_tp=audio_config.loudness.true_peak_dbtp,
    )

    tags = ID3Tags(
        title=item.english,
        artist=audio_config.mp3.artist,
        album="Dorosak Course Audio",
        track_number=item.item_no,
    )
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=audio_config.mp3.bitrate_kbps, tags=tags)
    return output_mp3_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/assembly.py tests/test_course_assembly.py
git commit -m "feat: add synthesize_bilingual_item for course vocabulary/examples/phrases audio"
```

---

### Task 9: `assemble_dialogue_lesson`

**Files:**
- Modify: `dorosak_factory/course/assembly.py`
- Modify: `tests/test_course_assembly.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_course_assembly.py`:

```python
def test_assemble_dialogue_lesson_produces_one_multi_voice_mp3(tmp_path):
    from dorosak_factory.course.assembly import assemble_dialogue_lesson
    from dorosak_factory.course.models import Book, CourseLesson, DialogueLine, DialogueSection, Unit

    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "work")
    cache = LineCache(cache_dir=audio_config.cache_dir)
    teacher_engine = NullEngine(output_dir=tmp_path / "teacher_raw")
    student_engine = NullEngine(output_dir=tmp_path / "student_raw")

    section = DialogueSection(
        book=Book(book_id=1, name="Mastering English with Dorosak (Beginner)"),
        unit=Unit(unit_id=6, book_id=1, name="Unit 1"),
        lesson=CourseLesson(lesson_id=20, unit_id=6, book_id=1, name="Lesson 1: Alphabet Basics"),
        lines=(
            DialogueLine(item_no=1, speaker="Teacher", text="Welcome to today's class."),
            DialogueLine(item_no=2, speaker="Student", text="Hello, teacher."),
        ),
    )
    output_path = tmp_path / "dialogue.mp3"

    assemble_dialogue_lesson(
        section,
        teacher_engine=teacher_engine,
        student_engine=student_engine,
        cache=cache,
        audio_config=audio_config,
        output_mp3_path=output_path,
        work_dir=tmp_path / "dialogue_work",
        teacher_voice_role="host",
        student_voice_role="female_1",
    )

    assert output_path.exists()
    assert probe_duration_seconds(output_path) > 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_dialogue_lesson'`

- [ ] **Step 3: Add the dialogue assembly function**

Append to `dorosak_factory/course/assembly.py` (add `DialogueSection` to the existing `from dorosak_factory.course.models import BilingualItem` line, making it `from dorosak_factory.course.models import BilingualItem, DialogueSection`):

```python
def assemble_dialogue_lesson(
    section: DialogueSection,
    teacher_engine: TTSEngine,
    student_engine: TTSEngine,
    cache: LineCache,
    audio_config: AudioConfig,
    output_mp3_path: Path,
    work_dir: Path,
    teacher_voice_role: str,
    student_voice_role: str,
    between_lines_ms: int = 500,
) -> Path:
    """One combined multi-voice MP3 for a Teacher/Student dialogue lesson."""
    work_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []

    for index, line in enumerate(section.lines):
        is_teacher = line.speaker == "Teacher"
        engine = teacher_engine if is_teacher else student_engine
        role = teacher_voice_role if is_teacher else student_voice_role
        result = cache.get_or_synthesize(
            engine, line.text, voice_role=role, model="default", voice_id=role
        )
        segments.append(result.wav_path)
        if index < len(section.lines) - 1:
            gap_path = work_dir / f"gap_{index}.wav"
            write_silence_wav(gap_path, between_lines_ms / 1000.0)
            segments.append(gap_path)

    raw_path = work_dir / "dialogue_raw.wav"
    concat_wavs(segments, raw_path)

    normalized_path = work_dir / "normalized.wav"
    normalize_loudness(
        raw_path,
        normalized_path,
        target_lufs=audio_config.loudness.target_lufs,
        target_tp=audio_config.loudness.true_peak_dbtp,
    )

    tags = ID3Tags(
        title=f"{section.lesson.name} - Dialogue",
        artist=audio_config.mp3.artist,
        album=section.book.name,
        track_number=section.lesson.lesson_id,
    )
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=audio_config.mp3.bitrate_kbps, tags=tags)
    return output_mp3_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/assembly.py tests/test_course_assembly.py
git commit -m "feat: add assemble_dialogue_lesson for course Teacher/Student dialogue audio"
```

---

### Task 10: `assemble_article_lesson`

**Files:**
- Modify: `dorosak_factory/course/assembly.py`
- Modify: `tests/test_course_assembly.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_course_assembly.py`:

```python
def test_assemble_article_lesson_produces_one_narrated_mp3(tmp_path):
    from dorosak_factory.course.assembly import assemble_article_lesson
    from dorosak_factory.course.models import ArticleSection, Book, CourseLesson, Unit

    audio_config = AudioConfig(cache_dir=tmp_path / "cache", work_dir=tmp_path / "work")
    cache = LineCache(cache_dir=audio_config.cache_dir)
    narrator_engine = NullEngine(output_dir=tmp_path / "narrator_raw")

    section = ArticleSection(
        book=Book(book_id=1, name="Mastering English with Dorosak (Beginner)"),
        unit=Unit(unit_id=6, book_id=1, name="Unit 1"),
        lesson=CourseLesson(lesson_id=20, unit_id=6, book_id=1, name="Lesson 1: Alphabet Basics"),
        text="The English alphabet is the foundation of the language.",
    )
    output_path = tmp_path / "article.mp3"

    assemble_article_lesson(
        section,
        narrator_engine=narrator_engine,
        cache=cache,
        audio_config=audio_config,
        output_mp3_path=output_path,
        work_dir=tmp_path / "article_work",
        narrator_voice_role="host",
    )

    assert output_path.exists()
    assert probe_duration_seconds(output_path) > 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_article_lesson'`

- [ ] **Step 3: Add the article assembly function**

Update the import line at the top of `dorosak_factory/course/assembly.py` to also bring in `ArticleSection`:

```python
from dorosak_factory.course.models import ArticleSection, BilingualItem, DialogueSection
```

Append to the file:

```python
def assemble_article_lesson(
    section: ArticleSection,
    narrator_engine: TTSEngine,
    cache: LineCache,
    audio_config: AudioConfig,
    output_mp3_path: Path,
    work_dir: Path,
    narrator_voice_role: str,
) -> Path:
    """One narrated MP3 reading an article's full passage."""
    work_dir.mkdir(parents=True, exist_ok=True)
    result = cache.get_or_synthesize(
        narrator_engine,
        section.text,
        voice_role=narrator_voice_role,
        model="default",
        voice_id=narrator_voice_role,
    )

    normalized_path = work_dir / "normalized.wav"
    normalize_loudness(
        result.wav_path,
        normalized_path,
        target_lufs=audio_config.loudness.target_lufs,
        target_tp=audio_config.loudness.true_peak_dbtp,
    )

    tags = ID3Tags(
        title=f"{section.lesson.name} - Article",
        artist=audio_config.mp3.artist,
        album=section.book.name,
        track_number=section.lesson.lesson_id,
    )
    export_mp3(normalized_path, output_mp3_path, bitrate_kbps=audio_config.mp3.bitrate_kbps, tags=tags)
    return output_mp3_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_assembly.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add dorosak_factory/course/assembly.py tests/test_course_assembly.py
git commit -m "feat: add assemble_article_lesson for course article narration audio"
```

---

### Task 11: `CourseManifest` (new SQLite table, per-item granularity)

**Files:**
- Create: `dorosak_factory/course/course_manifest.py`
- Test: `tests/test_course_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_manifest.py
from __future__ import annotations

from dorosak_factory.course.course_manifest import CourseItemRecord, CourseManifest


def test_new_item_needs_processing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is True
    finally:
        manifest.close()


def test_successful_item_does_not_need_reprocessing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary",
                book_id=1,
                unit_id=6,
                lesson_id=20,
                section_id="77",
                item_no=1,
                output_path="output/course/beginner/unit6/lesson20/vocabulary/1_alphabet.mp3",
                status="success",
                failure_reason=None,
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is False
    finally:
        manifest.close()


def test_force_reprocesses_even_successful_item(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary", book_id=1, unit_id=6, lesson_id=20, section_id="77",
                item_no=1, output_path="x.mp3", status="success", failure_reason=None,
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1, force=True) is True
    finally:
        manifest.close()


def test_failed_item_needs_reprocessing(tmp_path):
    manifest = CourseManifest(db_path=tmp_path / "manifest.sqlite3")
    try:
        manifest.upsert_record(
            CourseItemRecord(
                csv_source="vocabulary", book_id=1, unit_id=6, lesson_id=20, section_id="77",
                item_no=1, output_path=None, status="failed", failure_reason="synthesis error",
            )
        )
        assert manifest.needs_processing("vocabulary", section_id="77", item_no=1) is True
    finally:
        manifest.close()


def test_manifest_coexists_in_same_db_file_as_the_lessons_table(tmp_path):
    # Additive constraint: this new table must not collide with the
    # existing cat*/Markdown pipeline's manifest.Manifest, which uses the
    # same physical SQLite file (output/manifest.sqlite3) with a different
    # table ("lessons").
    from dorosak_factory.manifest.store import Manifest

    db_path = tmp_path / "manifest.sqlite3"
    lessons_manifest = Manifest(db_path=db_path)
    course_manifest = CourseManifest(db_path=db_path)
    try:
        assert lessons_manifest.all_records() == []
        assert course_manifest.all_records() == []
    finally:
        lessons_manifest.close()
        course_manifest.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dorosak_factory.course.course_manifest'`

- [ ] **Step 3: Write the manifest**

```python
# dorosak_factory/course/course_manifest.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_manifest.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the existing manifest test suite to confirm no collision**

Run: `python -m pytest tests/test_manifest.py -v`
Expected: PASS, all existing tests unchanged

- [ ] **Step 6: Commit**

```bash
git add dorosak_factory/course/course_manifest.py tests/test_course_manifest.py
git commit -m "feat: add CourseManifest (per-item SQLite table, additive to existing DB file)"
```

---

### Task 12: `course-run` CLI subcommand

**Files:**
- Modify: `dorosak_factory/cli.py`
- Test: `tests/test_course_cli.py`

This wires everything together: resolve the English engine (existing `tts.registry`, e.g. Kokoro) and the Arabic engine (`PiperEngine`), parse the requested CSV(s), and run the matching assembly function per section/item, skipping already-successful items unless `--force`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_course_cli.py
"""CLI integration test for `course-run`, using NullEngine (no network,
no cost) - same philosophy as tests/test_cli.py's `run` command tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dorosak_factory.cli import main
from tests.course_fixtures import CSV_HEADER, csv_row


@pytest.fixture
def project(tmp_path):
    (tmp_path / "input" / "course_csv").mkdir(parents=True)
    vocab_path = tmp_path / "input" / "course_csv" / "vocabulary.csv"
    rows = [
        csv_row(section_id="77", item_no=1, item_text="Alphabet\tالأبجدية"),
        csv_row(section_id="77", item_no=2, item_text="Letter\tحرف"),
    ]
    vocab_path.write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


def test_course_run_dry_run_prints_plan_without_producing_output(project, capsys):
    exit_code = main(
        [
            "--base-dir", str(project),
            "course-run",
            "--content", "vocabulary",
            "--english-engine", "null",
            "--arabic-engine", "null",
            "--dry-run",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "vocabulary" in captured.out
    assert not (project / "output" / "course").exists()


def test_course_run_produces_one_mp3_per_vocabulary_item(project):
    exit_code = main(
        [
            "--base-dir", str(project),
            "course-run",
            "--content", "vocabulary",
            "--english-engine", "null",
            "--arabic-engine", "null",
        ]
    )
    assert exit_code == 0
    output_dir = project / "output" / "course"
    mp3s = list(output_dir.rglob("*.mp3"))
    assert len(mp3s) == 2


def test_course_run_is_idempotent_on_rerun(project):
    main(
        [
            "--base-dir", str(project), "course-run", "--content", "vocabulary",
            "--english-engine", "null", "--arabic-engine", "null",
        ]
    )
    output_dir = project / "output" / "course"
    first_run_mtimes = {p: p.stat().st_mtime for p in output_dir.rglob("*.mp3")}

    main(
        [
            "--base-dir", str(project), "course-run", "--content", "vocabulary",
            "--english-engine", "null", "--arabic-engine", "null",
        ]
    )
    second_run_mtimes = {p: p.stat().st_mtime for p in output_dir.rglob("*.mp3")}

    assert first_run_mtimes == second_run_mtimes  # nothing re-rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_course_cli.py -v`
Expected: FAIL with `SystemExit` / `argument command: invalid choice` (no `course-run` subcommand yet)

- [ ] **Step 3: Add the `PiperEngine`-free NullEngine path and wire the subcommand**

`NullEngine` needs to work as a stand-in for `arabic_engine` too for tests (it already exists and just writes silent audio proportional to text length, regardless of language — no change needed there, it accepts any text/voice_role).

In `dorosak_factory/cli.py`, add these imports near the top (alongside the existing course-unrelated imports):

```python
from dorosak_factory.course.assembly import (
    assemble_article_lesson,
    assemble_dialogue_lesson,
    synthesize_bilingual_item,
)
from dorosak_factory.course.course_manifest import CourseItemRecord, CourseManifest
from dorosak_factory.course.csv_parser import (
    parse_articles_csv,
    parse_dialogues_csv,
    parse_examples_csv,
    parse_useful_phrases_csv,
    parse_vocabulary_csv,
)
```

In `build_arg_parser()`, right before the final `return parser` line, add:

```python
    course_parser = subparsers.add_parser("course-run", help="Process the course CSV audio pipeline")
    course_parser.add_argument(
        "--content",
        choices=["dialogues", "examples", "vocabulary", "useful_phrases", "articles", "all"],
        default="all",
    )
    course_parser.add_argument("--english-engine", default=None, help="Override auto-detected English engine")
    course_parser.add_argument("--arabic-engine", default="piper", help="Arabic TTS engine name")
    course_parser.add_argument("--only-lesson", type=int, default=None, help="Scope to one lesson_id")
    course_parser.add_argument("--dry-run", action="store_true")
    course_parser.add_argument("--force", action="store_true")
```

In `main()`, add the dispatch line alongside the existing `if args.command == ...` chain:

```python
    if args.command == "course-run":
        return _cmd_course_run(args, config)
```

Append these new functions at the end of `dorosak_factory/cli.py`:

```python
_CONTENT_FILENAMES = {
    "dialogues": "dialogues.csv",
    "examples": "examples.csv",
    "vocabulary": "vocabulary.csv",
    "useful_phrases": "useful_phrases.csv",
    "articles": "articles.csv",
}


def _cmd_course_run(args: argparse.Namespace, config: Config) -> int:
    content_types = list(_CONTENT_FILENAMES) if args.content == "all" else [args.content]

    english_engine_name = args.english_engine or config.tts.engine
    try:
        english_engine_cls = resolve_engine_class(explicit=english_engine_name)
    except EngineResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    english_engine = english_engine_cls.from_config(config)

    try:
        arabic_engine_cls = resolve_engine_class(explicit=args.arabic_engine)
    except EngineResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    arabic_engine = arabic_engine_cls.from_config(config)

    cache = LineCache(cache_dir=config.audio.cache_dir)
    course_manifest = CourseManifest(db_path=config.manifest.db_path)
    try:
        plan_lines: list[str] = []
        produced = 0
        for content_type in content_types:
            csv_path = config.course.csv_dir / _CONTENT_FILENAMES[content_type]
            if not csv_path.exists():
                print(f"COURSE CSV NOT FOUND: {csv_path}", file=sys.stderr)
                continue
            produced += _process_content_type(
                content_type, csv_path, args, config, english_engine, arabic_engine,
                cache, course_manifest, plan_lines,
            )

        if args.dry_run:
            print("\n".join(plan_lines) if plan_lines else "Nothing to process.")
            return 0

        print(f"Course run complete: {produced} item(s) produced.")
        return 0
    finally:
        course_manifest.close()


def _process_content_type(
    content_type, csv_path, args, config, english_engine, arabic_engine, cache, course_manifest, plan_lines
) -> int:
    produced = 0
    if content_type == "dialogues":
        for section in parse_dialogues_csv(csv_path):
            if args.only_lesson is not None and section.lesson.lesson_id != args.only_lesson:
                continue
            produced += _run_dialogue_section(
                section, args, config, english_engine, cache, course_manifest, plan_lines
            )
    elif content_type in ("examples", "vocabulary"):
        parse_fn = parse_examples_csv if content_type == "examples" else parse_vocabulary_csv
        for section in parse_fn(csv_path):
            if args.only_lesson is not None and section.lesson.lesson_id != args.only_lesson:
                continue
            for item in section.items:
                produced += _run_bilingual_item(
                    content_type, section, item, args, config, english_engine, arabic_engine,
                    cache, course_manifest, plan_lines,
                )
    elif content_type == "useful_phrases":
        for section in parse_useful_phrases_csv(csv_path):
            if args.only_lesson is not None and section.lesson.lesson_id != args.only_lesson:
                continue
            for item in section.items:
                produced += _run_phrase_item(
                    section, item, args, config, english_engine, cache, course_manifest, plan_lines
                )
    elif content_type == "articles":
        for section in parse_articles_csv(csv_path):
            if args.only_lesson is not None and section.lesson.lesson_id != args.only_lesson:
                continue
            produced += _run_article_section(
                section, args, config, english_engine, cache, course_manifest, plan_lines
            )
    return produced


def _lesson_dir(config: Config, section) -> Path:
    book_slug = section.book.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
    return config.course.output_dir / book_slug / f"unit{section.unit.unit_id}" / f"lesson{section.lesson.lesson_id}"


def _run_dialogue_section(section, args, config, english_engine, cache, course_manifest, plan_lines) -> int:
    section_key = ("dialogues", str(section.lesson.lesson_id), 0)
    if not args.dry_run and course_manifest.needs_processing(*section_key, force=args.force) is False:
        return 0
    plan_lines.append(f"dialogues lesson {section.lesson.lesson_id}: {section.lesson.name}")
    if args.dry_run:
        return 0

    output_path = _lesson_dir(config, section) / "dialogue" / "episode.mp3"
    work_dir = config.audio.work_dir / f"course_dialogue_{section.lesson.lesson_id}"
    student_role = config.course.student_voice_by_book.get(section.book.name, "female_1")
    try:
        assemble_dialogue_lesson(
            section, teacher_engine=english_engine, student_engine=english_engine, cache=cache,
            audio_config=config.audio, output_mp3_path=output_path, work_dir=work_dir,
            teacher_voice_role=config.course.teacher_voice_role, student_voice_role=student_role,
        )
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="dialogues", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=str(section.lesson.lesson_id), item_no=0,
                output_path=str(output_path), status="success", failure_reason=None,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - one lesson's failure must never crash the run
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="dialogues", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=str(section.lesson.lesson_id), item_no=0,
                output_path=None, status="failed", failure_reason=str(exc),
            )
        )
        return 0


def _run_bilingual_item(
    content_type, section, item, args, config, english_engine, arabic_engine, cache, course_manifest, plan_lines
) -> int:
    section_key = str(section.lesson.lesson_id)
    if not args.dry_run and course_manifest.needs_processing(content_type, section_key, item.item_no, force=args.force) is False:
        return 0
    plan_lines.append(f"{content_type} lesson {section.lesson.lesson_id} item {item.item_no}: {item.english}")
    if args.dry_run:
        return 0

    slug = item.english.lower().replace(" ", "_")[:40]
    output_path = _lesson_dir(config, section) / content_type / f"{item.item_no}_{slug}.mp3"
    work_dir = config.audio.work_dir / f"course_{content_type}_{section.lesson.lesson_id}"
    try:
        synthesize_bilingual_item(
            item, english_engine=english_engine, arabic_engine=arabic_engine, cache=cache,
            audio_config=config.audio, course_config=config.course, output_mp3_path=output_path,
            work_dir=work_dir, narrator_voice_role=config.course.narrator_voice_role,
        )
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source=content_type, book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=item.item_no,
                output_path=str(output_path), status="success", failure_reason=None,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source=content_type, book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=item.item_no,
                output_path=None, status="failed", failure_reason=str(exc),
            )
        )
        return 0


def _run_phrase_item(section, item, args, config, english_engine, cache, course_manifest, plan_lines) -> int:
    section_key = str(section.lesson.lesson_id)
    if not args.dry_run and course_manifest.needs_processing("useful_phrases", section_key, item.item_no, force=args.force) is False:
        return 0
    plan_lines.append(f"useful_phrases lesson {section.lesson.lesson_id} item {item.item_no}: {item.text}")
    if args.dry_run:
        return 0

    output_path = _lesson_dir(config, section) / "useful_phrases" / f"{item.item_no}.mp3"
    work_dir = config.audio.work_dir / f"course_phrases_{section.lesson.lesson_id}"
    try:
        result = cache.get_or_synthesize(
            english_engine, item.text, voice_role=config.course.narrator_voice_role,
            model="default", voice_id=config.course.narrator_voice_role,
        )
        from dorosak_factory.audio.loudness import normalize_loudness
        from dorosak_factory.audio.mp3_export import ID3Tags, export_mp3

        normalized_path = work_dir / f"normalized_{item.item_no}.wav"
        work_dir.mkdir(parents=True, exist_ok=True)
        normalize_loudness(
            result.wav_path, normalized_path,
            target_lufs=config.audio.loudness.target_lufs, target_tp=config.audio.loudness.true_peak_dbtp,
        )
        tags = ID3Tags(title=item.text, artist=config.audio.mp3.artist, album="Dorosak Course Audio", track_number=item.item_no)
        export_mp3(normalized_path, output_path, bitrate_kbps=config.audio.mp3.bitrate_kbps, tags=tags)

        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="useful_phrases", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=item.item_no,
                output_path=str(output_path), status="success", failure_reason=None,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="useful_phrases", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=item.item_no,
                output_path=None, status="failed", failure_reason=str(exc),
            )
        )
        return 0


def _run_article_section(section, args, config, english_engine, cache, course_manifest, plan_lines) -> int:
    section_key = str(section.lesson.lesson_id)
    if not args.dry_run and course_manifest.needs_processing("articles", section_key, 0, force=args.force) is False:
        return 0
    plan_lines.append(f"articles lesson {section.lesson.lesson_id}: {section.lesson.name}")
    if args.dry_run:
        return 0

    output_path = _lesson_dir(config, section) / "article" / "narration.mp3"
    work_dir = config.audio.work_dir / f"course_article_{section.lesson.lesson_id}"
    try:
        assemble_article_lesson(
            section, narrator_engine=english_engine, cache=cache, audio_config=config.audio,
            output_mp3_path=output_path, work_dir=work_dir,
            narrator_voice_role=config.course.narrator_voice_role,
        )
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="articles", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=0,
                output_path=str(output_path), status="success", failure_reason=None,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="articles", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=0,
                output_path=None, status="failed", failure_reason=str(exc),
            )
        )
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_course_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full existing CLI test suite to confirm no regression**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS, every existing `run`/`status`/`validate`/`cost-report` test unchanged

- [ ] **Step 6: Commit**

```bash
git add dorosak_factory/cli.py tests/test_course_cli.py
git commit -m "feat: add course-run CLI subcommand wiring parser/engines/assembly/manifest together"
```

---

### Task 13: Full test suite + `.gitignore` for course CSVs

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add course CSVs and course output to `.gitignore`**

The real CSVs (currently in `~/Downloads/`) contain Dorosak's proprietary course catalog and should not be committed, mirroring how `output/`, `kokoro_model/`, `.env` are already excluded. Append to `.gitignore`:

```
# Course CSV audio pipeline (see docs/superpowers/specs/2026-07-19-course-audio-pipeline-design.md)
input/course_csv/
output/course/
```

- [ ] **Step 2: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all tests pass — existing `cat*` pipeline tests (unchanged) plus every new course test from Tasks 1-12

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore course CSVs and course output (proprietary catalog data)"
```

---

### Task 14: Real-world setup — Piper Arabic voice + real CSVs in place

This task has no automated test — it's getting real assets in place for the pilot run in Task 15.

- [ ] **Step 1: Install `piper-tts`**

```bash
pip install piper-tts
```

- [ ] **Step 2: Download the Arabic voice**

```bash
mkdir -p ~/.local/share/piper-voices/ar_JO
curl -L -o ~/.local/share/piper-voices/ar_JO/ar_JO-kareem-medium.onnx \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx"
curl -L -o ~/.local/share/piper-voices/ar_JO/ar_JO-kareem-medium.onnx.json \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json"
```

If either URL 404s (Hugging Face occasionally reorganizes voice paths), browse `https://huggingface.co/rhasspy/piper-voices/tree/main/ar` directly and update the two paths above to match.

- [ ] **Step 3: Add `PIPER_AR_VOICE_PATH` to `.env`**

Append to `.env` (create it from `.env.example` first if it doesn't exist yet):

```
PIPER_AR_VOICE_PATH=/home/cygon/.local/share/piper-voices/ar_JO/ar_JO-kareem-medium.onnx
```

- [ ] **Step 4: Copy the real CSVs into the repo's gitignored `input/course_csv/`**

```bash
mkdir -p input/course_csv
cp ~/Downloads/dialogues.csv ~/Downloads/examples.csv ~/Downloads/vocabulary.csv \
   ~/Downloads/useful_phrases.csv ~/Downloads/articles.csv input/course_csv/
```

(Copy, not move — leaves the originals in `~/Downloads/` untouched.)

- [ ] **Step 5: Verify Piper is detected**

```bash
python -c "
from dorosak_factory.tts.engines.piper_engine import PiperEngine
import os
print(PiperEngine.is_available(os.environ))
"
```

Expected: `True`. If `False`, re-check the `.env` path and that both the `.onnx` and `.onnx.json` files exist at that exact path.

---

### Task 15: Pilot run — Lesson 1 (Alphabet Basics), all 5 content types

- [ ] **Step 1: Dry-run first to see the plan without producing anything**

```bash
python -m dorosak_factory course-run --content all --only-lesson 20 --english-engine kokoro --arabic-engine piper --dry-run
```

Expected output: a list of what would be produced for lesson_id 20 (Lesson 1: Alphabet Basics) — some vocabulary/examples/useful_phrases items will be *absent* from this list if they already have real recorded audio (that's the skip-existing-audio logic working correctly, not a bug).

- [ ] **Step 2: Run for real**

```bash
python -m dorosak_factory course-run --content all --only-lesson 20 --english-engine kokoro --arabic-engine piper
```

- [ ] **Step 3: Inspect the output**

```bash
find output/course -name "*.mp3" | sort
```

Expected: one `dialogue/episode.mp3`, one `article/narration.mp3`, and one `.mp3` per not-already-recorded vocabulary/example/useful_phrase item for Lesson 1.

Listen to a few, in particular:
- One vocabulary item — confirm English word, ~1s pause, Arabic translation, in that order.
- The dialogue episode — confirm Teacher and Student sound like two distinct, consistent voices.
- The article — confirm it reads the full passage, not just the title.

- [ ] **Step 4: Report back to the user**

Summarize: which files were produced, their location, total count, and any items that failed (check `python -m dorosak_factory course-run --content all --only-lesson 20 ... ` output text, or query `CourseManifest.all_records()` for `status == "failed"`). This pilot output is what goes to the team for feedback before any full batch run, per the approved rollout plan — do not proceed to processing the other ~199 lessons without that feedback.

---

## Self-Review Notes

- **Spec coverage**: every section of the design spec has a corresponding task — models (Task 2), CSV parser + skip-existing-audio logic (Tasks 4-6), Piper adapter + licensing (Task 7), bilingual/dialogue/article assembly (Tasks 8-10), new manifest table (Task 11), CLI (Task 12), rollout plan's "build everything, then pilot one lesson" sequencing (Tasks 13-15).
- **Existing-pipeline safety**: Tasks 7, 11, and 12 explicitly include a step re-running the pre-existing test suites they sit closest to (`test_kokoro_engine.py`/registry tests, `test_manifest.py`, `test_cli.py`) to catch any accidental regression before committing.
- **Type consistency checked**: `CourseItemRecord` field names (`csv_source`, `section_id`, `item_no`) are used identically in `course_manifest.py` and every call site in `cli.py`. `CourseConfig` field names (`teacher_voice_role`, `narrator_voice_role`, `arabic_voice_role`, `bilingual_gap_ms`, `student_voice_by_book`) match between Task 3's definition and their usage in Task 12's `_cmd_course_run` and Task 8/9/10's assembly functions.
