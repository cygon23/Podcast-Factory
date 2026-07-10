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

import dorosak_factory.tts.engines  # noqa: F401 - import side-effect registers built-in engines
from dorosak_factory.audio.cache import LineCache
from dorosak_factory.config import Config, load_config
from dorosak_factory.manifest.store import Manifest
from dorosak_factory.parser.markdown_parser import parse_category_file
from dorosak_factory.parser.models import Category
from dorosak_factory.pipeline import estimate_characters, process_lesson, record_result
from dorosak_factory.report.run_report import LessonOutcome, RunReport
from dorosak_factory.tts.registry import EngineResolutionError, resolve_engine_class


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
    run_parser.add_argument("--force", action="store_true", help="Reprocess every lesson")
    run_parser.add_argument("--only", default=None, help='One lesson ("cat31:5") or category ("cat31")')
    run_parser.add_argument("--formats", choices=["audio", "video", "both"], default="both")
    run_parser.add_argument("--dry-run", action="store_true", help="Print the plan; synthesize nothing")

    subparsers.add_parser("status", help="Show manifest summary")

    subparsers.add_parser(
        "validate", help="Spot-check that recorded outputs still exist and are playable"
    )

    subparsers.add_parser("cost-report", help="Show characters synthesized and estimated cost by engine")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config, base_dir=args.base_dir)

    if args.command == "run":
        return _cmd_run(args, config)
    if args.command == "status":
        return _cmd_status(config)
    if args.command == "validate":
        return _cmd_validate(config)
    if args.command == "cost-report":
        return _cmd_cost_report(config)
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

    manifest = Manifest(db_path=config.manifest.db_path)
    try:
        plan = manifest.plan_run(
            categories,
            engine=engine_name,
            force=args.force,
            only_category=only_category,
            only_lesson=only_lesson,
        )
        to_process = [item for item in plan if item.needs_processing]

        if args.dry_run:
            _print_dry_run(plan, to_process, engine_name, config, log_path)
            return 0

        exit_code, report_text = _execute_run(
            plan, to_process, categories, engine_cls, engine_name, config, manifest, args.formats
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
    plan, to_process, categories, engine_cls, engine_name, config, manifest, formats
) -> tuple[int, str]:
    engine = engine_cls.from_config(config)
    cache = LineCache(cache_dir=config.audio.cache_dir)
    categories_by_number = {c.number: c for c in categories}

    report = RunReport()
    start_time = time.monotonic()

    for item in plan:
        if not item.needs_processing:
            report.outcomes.append(LessonOutcome(item.category_number, item.lesson.number, "skipped"))

    def run_one(item):
        category = categories_by_number[item.category_number]
        result = process_lesson(
            category, item.lesson, engine, engine_name, cache, config, formats=formats
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
