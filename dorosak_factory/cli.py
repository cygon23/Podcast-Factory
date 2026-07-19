"""Single-entry-point CLI: `python -m dorosak_factory <command>` (INSTRUCTIONS.md 4.8).

Commands: `run` (process new/changed lessons), `status` (manifest summary),
`validate` (spot-check existing outputs), `cost-report` (estimated spend by engine).
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

import dorosak_factory.tts.engines  # noqa: F401 - import side-effect registers built-in engines
import dorosak_factory.video.renderers  # noqa: F401 - import side-effect registers built-in renderers
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import Config, load_config
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
from dorosak_factory.manifest.store import Manifest
from dorosak_factory.parser.markdown_parser import parse_category_file
from dorosak_factory.parser.models import Category
from dorosak_factory.pipeline import estimate_characters, process_lesson, record_result
from dorosak_factory.report.run_report import LessonOutcome, RunReport
from dorosak_factory.report.status_sync import render_status_markdown, write_and_push_status
from dorosak_factory.tts.registry import EngineResolutionError, resolve_engine_class
from dorosak_factory.video.renderer_registry import RendererResolutionError, resolve_renderer_class


def discover_categories(input_dir: Path) -> tuple[list[Category], list[str]]:
    """Parses every *.md file in `input_dir`; returns categories plus any parse-error messages."""
    categories: list[Category] = []
    parse_error_messages: list[str] = []
    if not input_dir.exists():
        return categories, parse_error_messages
    for md_file in sorted(input_dir.glob("*.md")):
        category = parse_category_file(md_file)
        categories.append(category)
        for err in category.parse_errors:
            parse_error_messages.append(f"{err.file} — {err.lesson_header}: {err.message}")
    return categories, parse_error_messages


def parse_only(only: str | None) -> tuple[int | None, int | None]:
    """Parses `--only cat31:5` (one lesson) or `--only cat31` (one category)."""
    if only is None:
        return None, None
    only = only.strip()
    if ":" in only:
        category_part, lesson_part = only.split(":", 1)
        return _parse_category_number(category_part), int(lesson_part)
    return _parse_category_number(only), None


def _parse_category_number(text: str) -> int:
    text = text.strip()
    if text.lower().startswith("cat"):
        text = text[3:]
    return int(text)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dorosak_factory")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument(
        "--base-dir", type=Path, default=Path("."), help="Base directory for relative config paths"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Process new/changed/failed lessons")
    run_parser.add_argument("--engine", default=None, help="Override auto-detected engine")
    run_parser.add_argument("--renderer", default=None, help="Override auto-detected video renderer")
    run_parser.add_argument("--force", action="store_true", help="Reprocess every lesson")
    run_parser.add_argument("--only", default=None, help='One lesson ("cat31:5") or category ("cat31")')
    run_parser.add_argument("--formats", choices=["audio", "video", "both"], default="both")
    run_parser.add_argument("--dry-run", action="store_true", help="Print the plan; synthesize nothing")
    run_parser.add_argument(
        "--live-status",
        action="store_true",
        help="After each lesson, commit+push a STATUS.md progress file to git (code/status only, never audio/video)",
    )

    subparsers.add_parser("status", help="Show manifest summary")

    subparsers.add_parser(
        "validate", help="Spot-check that recorded outputs still exist and are playable"
    )

    subparsers.add_parser("cost-report", help="Show characters synthesized and estimated cost by engine")

    course_parser = subparsers.add_parser("course-run", help="Process the course CSV audio pipeline")
    course_parser.add_argument(
        "--content",
        choices=["dialogues", "examples", "vocabulary", "useful_phrases", "articles", "all"],
        default="all",
    )
    course_parser.add_argument(
        "--english-engine", default=None, help="Override auto-detected English engine"
    )
    course_parser.add_argument("--arabic-engine", default="piper", help="Arabic TTS engine name")
    course_parser.add_argument("--only-lesson", type=int, default=None, help="Scope to one lesson_id")
    course_parser.add_argument("--dry-run", action="store_true")
    course_parser.add_argument("--force", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Load .env into the process environment before anything reads
    # os.environ (engine credential detection, is_available() checks).
    # Does not override variables already set in the real shell environment.
    env_path = Path(args.base_dir) / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    config = load_config(args.config, base_dir=args.base_dir)

    if args.command == "run":
        return _cmd_run(args, config)
    if args.command == "status":
        return _cmd_status(config)
    if args.command == "validate":
        return _cmd_validate(config)
    if args.command == "cost-report":
        return _cmd_cost_report(config)
    if args.command == "course-run":
        return _cmd_course_run(args, config)
    parser.error(f"Unknown command: {args.command}")
    return 2  # pragma: no cover - argparse exits before this


def _start_run_log(output_dir: Path) -> Path:
    """Creates output/logs/run_{timestamp}.log and returns its path (INSTRUCTIONS.md 4.8)."""
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = logs_dir / f"run_{timestamp}.log"
    log_path.write_text(f"Dorosak Factory run started at {timestamp}\n", encoding="utf-8")
    return log_path


def _append_run_log(log_path: Path, text: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def _cmd_run(args: argparse.Namespace, config: Config) -> int:
    log_path = _start_run_log(config.pipeline.output_dir)

    categories, parse_errors = discover_categories(config.pipeline.input_dir)
    for message in parse_errors:
        print(f"PARSE ERROR: {message}", file=sys.stderr)
        _append_run_log(log_path, f"PARSE ERROR: {message}")

    only_category, only_lesson = parse_only(args.only)
    engine_name_explicit = args.engine or config.tts.engine
    try:
        engine_cls = resolve_engine_class(explicit=engine_name_explicit)
    except EngineResolutionError as exc:
        print(str(exc), file=sys.stderr)
        _append_run_log(log_path, f"ENGINE RESOLUTION ERROR: {exc}")
        return 1
    engine_name = engine_cls.name
    _append_run_log(log_path, f"Engine resolved: {engine_name}")

    renderer_name_explicit = args.renderer or config.video.renderer
    try:
        renderer_cls = resolve_renderer_class(explicit=renderer_name_explicit)
    except RendererResolutionError as exc:
        print(str(exc), file=sys.stderr)
        _append_run_log(log_path, f"RENDERER RESOLUTION ERROR: {exc}")
        return 1
    _append_run_log(log_path, f"Renderer resolved: {renderer_cls.name}")

    manifest = Manifest(db_path=config.manifest.db_path)
    try:
        plan = manifest.plan_run(
            categories,
            engine=engine_name,
            force=args.force,
            only_category=only_category,
            only_lesson=only_lesson,
            formats=args.formats,
        )
        to_process = [item for item in plan if item.needs_processing]

        if args.dry_run:
            _print_dry_run(plan, to_process, engine_name, config, log_path)
            return 0

        exit_code, report_text = _execute_run(
            plan,
            to_process,
            categories,
            engine_cls,
            engine_name,
            renderer_cls,
            config,
            manifest,
            args.formats,
            live_status=args.live_status,
            base_dir=args.base_dir,
            only_category=only_category,
        )
        _append_run_log(log_path, report_text)
        return exit_code
    finally:
        manifest.close()


def _print_dry_run(plan, to_process, engine_name: str, config: Config, log_path: Path) -> None:
    lines = [f"Engine resolved: {engine_name}"]
    lines.append(f"Lessons to process: {len(to_process)} (of {len(plan)} matched by selection)")
    total_chars = 0
    for item in to_process:
        chars = estimate_characters(item.lesson)
        total_chars += chars
        lines.append(f"  cat{item.category_number}:{item.lesson.number} [{item.reason}] ~{chars} chars")
    price = config.tts.price_per_char.get(engine_name, 0.0)
    lines.append(f"Estimated total characters: {total_chars}")
    lines.append(f"Estimated cost ({engine_name}): ${total_chars * price:.4f}")

    text = "\n".join(lines)
    print(text)
    _append_run_log(log_path, text)


def _execute_run(
    plan,
    to_process,
    categories,
    engine_cls,
    engine_name,
    renderer_cls,
    config,
    manifest,
    formats,
    live_status: bool = False,
    base_dir: Path | None = None,
    only_category: int | None = None,
) -> tuple[int, str]:
    engine = engine_cls.from_config(config)
    renderer = renderer_cls.from_config(config)
    cache = LineCache(cache_dir=config.audio.cache_dir)
    categories_by_number = {c.number: c for c in categories}

    report = RunReport()
    start_time = time.monotonic()

    for item in plan:
        if not item.needs_processing:
            report.outcomes.append(LessonOutcome(item.category_number, item.lesson.number, "skipped"))

    status_repo_dir = Path(base_dir) if base_dir is not None else Path(".")
    status_path = status_repo_dir / "STATUS.md"
    if only_category is not None and only_category in categories_by_number:
        status_category_number = only_category
        status_category_title = categories_by_number[only_category].title_en
    else:
        status_category_number = 0
        status_category_title = "All categories"

    def push_status(last_completed: str | None) -> None:
        if not live_status:
            return
        content = render_status_markdown(
            category_number=status_category_number,
            category_title=status_category_title,
            engine_name=engine_name,
            total_lessons=len(plan),
            report=report,
            last_completed=last_completed,
        )
        write_and_push_status(status_repo_dir, status_path, content)

    def run_one(item):
        category = categories_by_number[item.category_number]
        result = process_lesson(
            category, item.lesson, engine, engine_name, cache, config, renderer, formats=formats
        )
        record_result(manifest, item.category_number, item.lesson, engine_name, result)
        return item, result

    with ThreadPoolExecutor(max_workers=config.pipeline.concurrency) as executor:
        futures = [executor.submit(run_one, item) for item in to_process]
        for future in as_completed(futures):
            item, result = future.result()
            status = "processed" if result.success else "failed"
            report.outcomes.append(
                LessonOutcome(
                    item.category_number,
                    item.lesson.number,
                    status,
                    engine=engine_name,
                    characters_synthesized=result.characters_synthesized,
                    failure_reason=result.failure_reason,
                )
            )
            push_status(
                f"cat{item.category_number}:{item.lesson.number} — {item.lesson.title_en} ({status})"
            )

    report.wall_time_seconds = time.monotonic() - start_time
    report_text = report.render_text(price_per_char=config.tts.price_per_char)
    print(report_text)
    return (0 if report.failed_count == 0 else 1), report_text


def _cmd_status(config: Config) -> int:
    manifest = Manifest(db_path=config.manifest.db_path)
    try:
        records = manifest.all_records()
        success = sum(1 for r in records if r.status == "success")
        failed = sum(1 for r in records if r.status != "success")
        print(f"Total recorded lessons: {len(records)}")
        print(f"  Success: {success}")
        print(f"  Failed:  {failed}")
        for record in records:
            if record.status != "success":
                print(
                    f"    cat{record.category_number}:{record.lesson_number} - {record.failure_reason}"
                )
        return 0
    finally:
        manifest.close()


def _cmd_validate(config: Config) -> int:
    """Spot-checks that manifest-recorded outputs still exist and are ffprobe-playable."""
    from dorosak_factory.media_probe import probe_streams

    manifest = Manifest(db_path=config.manifest.db_path)
    try:
        records = manifest.all_records()
        problems = 0
        for record in records:
            for label, path_str in (
                ("audio", record.audio_path),
                ("video_16x9", record.video_16x9_path),
                ("video_9x16", record.video_9x16_path),
            ):
                if path_str is None:
                    continue
                path = Path(path_str)
                if not path.exists():
                    print(f"MISSING cat{record.category_number}:{record.lesson_number} {label}: {path}")
                    problems += 1
                    continue
                try:
                    probe_streams(path)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"UNPLAYABLE cat{record.category_number}:{record.lesson_number} {label}: {exc}"
                    )
                    problems += 1
        print(f"Checked {len(records)} manifest records, {problems} problem(s) found.")
        return 0 if problems == 0 else 1
    finally:
        manifest.close()


def _cmd_cost_report(config: Config) -> int:
    manifest = Manifest(db_path=config.manifest.db_path)
    try:
        records = manifest.all_records()
        totals: dict[str, int] = {}
        for record in records:
            totals[record.engine] = totals.get(record.engine, 0) + record.characters_synthesized
        print("Cost report:")
        grand_total = 0.0
        for engine, chars in sorted(totals.items()):
            price = config.tts.price_per_char.get(engine, 0.0)
            cost = chars * price
            grand_total += cost
            print(f"  {engine}: {chars} chars (~${cost:.4f})")
        print(f"  Total: ~${grand_total:.4f}")
        return 0
    finally:
        manifest.close()


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
    return (
        config.course.output_dir
        / book_slug
        / f"unit{section.unit.unit_id}"
        / f"lesson{section.lesson.lesson_id}"
    )


def _run_dialogue_section(section, args, config, english_engine, cache, course_manifest, plan_lines) -> int:
    section_key = str(section.lesson.lesson_id)
    if not args.dry_run and not course_manifest.needs_processing(
        "dialogues", section_key, 0, force=args.force
    ):
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
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=0,
                output_path=str(output_path), status="success", failure_reason=None,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - one lesson's failure must never crash the run
        course_manifest.upsert_record(
            CourseItemRecord(
                csv_source="dialogues", book_id=section.book.book_id, unit_id=section.unit.unit_id,
                lesson_id=section.lesson.lesson_id, section_id=section_key, item_no=0,
                output_path=None, status="failed", failure_reason=str(exc),
            )
        )
        return 0


def _run_bilingual_item(
    content_type, section, item, args, config, english_engine, arabic_engine, cache, course_manifest, plan_lines
) -> int:
    section_key = str(section.lesson.lesson_id)
    if not args.dry_run and not course_manifest.needs_processing(
        content_type, section_key, item.item_no, force=args.force
    ):
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
    if not args.dry_run and not course_manifest.needs_processing(
        "useful_phrases", section_key, item.item_no, force=args.force
    ):
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

        work_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = work_dir / f"normalized_{item.item_no}.wav"
        normalize_loudness(
            result.wav_path, normalized_path,
            target_lufs=config.audio.loudness.target_lufs, target_tp=config.audio.loudness.true_peak_dbtp,
        )
        tags = ID3Tags(
            title=item.text, artist=config.audio.mp3.artist, album="Dorosak Course Audio",
            track_number=item.item_no,
        )
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
    if not args.dry_run and not course_manifest.needs_processing(
        "articles", section_key, 0, force=args.force
    ):
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
