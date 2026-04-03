from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
except Exception:  # pragma: no cover
    Console = None
    Table = None

from .dependencies import check_runtime_dependencies, run_doctor
from .executor import apply_actions, apply_folder_renames, garbage_collect_empty_dirs
from .manifest import build_summary, write_action_manifest, write_empty_dir_manifest, write_folder_manifest, write_topic_plan_manifest
from .models import FileRecord, RunStats
from .planner import build_folder_rename_plan, plan_actions
from .progress import emit
from .progress_terminal import TerminalProgressReporter
from .scanner import discover_files
from .utils import load_state, save_state, setup_logging

console = Console() if Console is not None else None


def _print(text: str) -> None:
    if console is not None:
        console.print(text)
        return
    print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organizer",
        description="Disk ReOrganizer: content-aware local LLM disk organizer",
    )
    parser.add_argument("mode", choices=["analyze", "apply-copy", "apply-move", "rename-in-place", "folder-rename-only", "doctor"])

    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--source-root", type=str, default=None, help="Source/target folder path")
    parser.add_argument("--output-root", type=str, default=None, help="Output folder path")
    parser.add_argument("--manifest-dir", type=str, default=None, help="Manifest directory path")
    parser.add_argument("--state-file", type=str, default=None, help="State file path")
    parser.add_argument("--log-dir", type=str, default=None, help="Log directory path")
    parser.add_argument("--gui", action="store_true", help="Open folder selection dialogs")

    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--ollama-url", type=str, default=None)
    parser.add_argument("--workers-extract", type=int, default=None)
    parser.add_argument("--workers-llm", type=int, default=None)
    parser.add_argument("--keep-alive", type=str, default=None)
    parser.add_argument("--progress", choices=["off", "basic", "detailed"], default="basic")
    parser.add_argument("--progress-refresh-ms", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument("--no-dry-run", action="store_true")
    parser.add_argument("--yes-i-understand", action="store_true")
    return parser


def _build_cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    dry_run = args.dry_run
    if args.no_dry_run:
        dry_run = False

    return {
        "mode": args.mode,
        "source_root": args.source_root,
        "output_root": args.output_root,
        "manifest_dir": args.manifest_dir,
        "state_file": args.state_file,
        "log_dir": args.log_dir,
        "model": args.model,
        "ollama_url": args.ollama_url,
        "workers_extract": args.workers_extract,
        "workers_llm": args.workers_llm,
        "keep_alive": args.keep_alive,
        "dry_run": dry_run,
    }


def _is_apply_like_mode(mode: str) -> bool:
    return mode in {"apply-copy", "apply-move", "rename-in-place", "folder-rename-only"}


def _build_gui_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    from .gui_select import select_directory

    if args.mode == "analyze":
        src = select_directory("Select SOURCE folder (read-only in ANALYZE mode)")
        if src is None:
            _print("[yellow]No source folder selected; exiting.[/yellow]")
            return None

        suggested_out = src.parent / f"{src.name}_out"
        out = select_directory(
            "Select OUTPUT folder for manifests/logs (Cancel to use '<source>_out').",
            initialdir=str(suggested_out.parent),
        )
        if out is None:
            out = suggested_out

        return {
            "source_root": str(src),
            "output_root": str(out),
        }

    if _is_apply_like_mode(args.mode):
        src = select_directory("Select TARGET folder (files may be reorganized in apply-like modes)")
        if src is None:
            _print("[yellow]No target folder selected; exiting.[/yellow]")
            return None

        suggested_out = src.parent / f"{src.name}_out"
        out = select_directory(
            "Select OUTPUT/BACKUP folder (Cancel to use '<target>_out').",
            initialdir=str(suggested_out.parent),
        )
        if out is None:
            out = suggested_out

        return {
            "source_root": str(src),
            "output_root": str(out),
        }

    src = select_directory("Select source folder")
    if src is None:
        _print("[yellow]No source folder selected; exiting.[/yellow]")
        return None
    return {"source_root": str(src)}


def build_reporter(args: argparse.Namespace) -> TerminalProgressReporter | None:
    if args.progress == "off":
        return None
    return TerminalProgressReporter(
        min_interval=max(args.progress_refresh_ms, 50) / 1000.0,
        detailed=(args.progress == "detailed"),
    )


def _use_cache(record: FileRecord, state: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    key = record.rel_path.as_posix()
    cached = state.get("files", {}).get(key)
    if not isinstance(cached, dict):
        return False, None
    if cached.get("fingerprint") != record.fingerprint:
        return False, None
    return True, cached


def _print_summary(summary: dict[str, int]) -> None:
    if Table is None or console is None:
        _print("Run Summary")
        for key, val in summary.items():
            _print(f"- {key}: {val}")
        return

    table = Table(title="Run Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, val in summary.items():
        table.add_row(key, str(val))
    console.print(table)


def _print_doctor_report(results: list[tuple[str, bool, str]]) -> None:
    if Table is None or console is None:
        for name, ok, detail in results:
            status = "PASS" if ok else "FAIL"
            _print(f"{status} {name}: {detail}")
        return

    table = Table(title="Doctor Report")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for name, ok, detail in results:
        table.add_row(name, "pass" if ok else "fail", detail)
    console.print(table)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    reporter = build_reporter(args)

    try:
        try:
            check_runtime_dependencies(gui_requested=args.gui, ocr_enabled=False)
        except RuntimeError as exc:
            _print(f"[red]Dependency error:[/red]\n{exc}")
            return 2

        if args.mode == "doctor":
            results = run_doctor(
                gui_requested=True,
                ocr_enabled=False,
                ollama_url=args.ollama_url or "http://localhost:11434",
            )
            _print_doctor_report(results)
            return 0 if all(ok for _, ok, _ in results) else 1

        from .classify import classify_records, from_jsonable, to_jsonable
        from .config import ConfigError, load_config
        from .extractors import extract_records

        overrides = _build_cli_overrides(args)
        if args.gui:
            gui_overrides = _build_gui_overrides(args)
            if gui_overrides is None:
                return 1
            overrides.update(gui_overrides)

        try:
            cfg = load_config(Path(args.config) if args.config else None, overrides)
        except ConfigError as exc:
            _print(f"[red]Config error:[/red] {exc}")
            return 2

        try:
            check_runtime_dependencies(gui_requested=args.gui, ocr_enabled=cfg.ocr_enabled)
        except RuntimeError as exc:
            _print(f"[red]Dependency error:[/red]\n{exc}")
            return 2

        emit(
            reporter,
            phase="startup",
            message=(
                f"mode={cfg.mode} model={cfg.model} workers_llm={cfg.workers_llm} "
                f"keep_alive={cfg.keep_alive} cache={'on' if cfg.cache_enabled else 'off'} "
                f"ocr={'on' if cfg.ocr_enabled else 'off'}"
            ),
            current_path=cfg.source_root.as_posix(),
        )

        if cfg.mode == "rename-in-place" and not args.yes_i_understand:
            _print("[red]rename-in-place requires --yes-i-understand[/red]")
            return 2

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        setup_logging(cfg.log_dir / f"run_{run_id}.log")

        if cfg.mode in {"analyze", "folder-rename-only"} and args.no_dry_run:
            _print("[yellow]Warning:[/yellow] no-dry-run requested in a non-destructive mode")

        state = load_state(cfg.state_file)
        if "classification_cache" not in state or not isinstance(state.get("classification_cache"), dict):
            state["classification_cache"] = {}
        if "concept_cache" not in state or not isinstance(state.get("concept_cache"), dict):
            state["concept_cache"] = {}
        stats = RunStats()

        logging.info("Starting mode=%s source=%s output=%s", cfg.mode, cfg.source_root, cfg.output_root)

        records = discover_files(cfg, reporter=reporter)
        stats.total_scanned = len(records)
        stats.supported_files = len(records)

        extract_targets: list[FileRecord] = []
        classifications: dict[str, Any] = {}

        for rec in records:
            cached_ok, cached_data = _use_cache(rec, state)
            if cached_ok and cached_data is not None:
                rec.extracted_snippet = str(cached_data.get("snippet", ""))
                rec.extraction_ok = bool(rec.extracted_snippet)
                cls_raw = cached_data.get("classification")
                if isinstance(cls_raw, dict):
                    classifications[rec.rel_path.as_posix()] = from_jsonable(cls_raw, cfg.review_bucket)
                else:
                    extract_targets.append(rec)
            else:
                extract_targets.append(rec)

        if extract_targets:
            extract_records(extract_targets, cfg, reporter=reporter)
        stats.extracted_successfully = sum(1 for r in records if r.extraction_ok)

        classify_targets = [r for r in records if r.rel_path.as_posix() not in classifications]
        if classify_targets:
            classified = classify_records(
                classify_targets,
                cfg,
                reporter=reporter,
                classification_cache=state["classification_cache"] if cfg.cache_enabled else None,
                concept_cache=state["concept_cache"] if cfg.cache_enabled else None,
            )
            classifications.update(classified)

        for rec in records:
            cls = classifications[rec.rel_path.as_posix()]
            if cls.confidence >= cfg.min_confidence:
                stats.classified_successfully += 1
            else:
                stats.low_confidence_files += 1
            if cls.cache_hit:
                stats.cache_hits += 1
            else:
                stats.cache_misses += 1

            state["files"][rec.rel_path.as_posix()] = {
                "fingerprint": rec.fingerprint,
                "snippet": rec.extracted_snippet,
                "classification": to_jsonable(cls),
            }

        actions, topic_plan = plan_actions(records, classifications, cfg, reporter=reporter)
        stats.duplicates = sum(1 for a in actions if a.duplicate_of is not None)
        stats.files_routed_to_misc = sum(1 for a in actions if a.folder_path.startswith("misc_topics"))
        stats.low_confidence_preserved_names = sum(
            1 for a in actions if a.preserve_original_name and a.confidence < cfg.min_confidence
        )
        stats.topic_folders_created = sum(
            1 for v in topic_plan.values() if isinstance(v, dict) and v.get("folder") != "misc_topics"
        )
        stats.subtopic_folders_created = sum(
            len(v.get("subtopics", [])) for v in topic_plan.values() if isinstance(v, dict)
        )

        emit(reporter, phase="manifest", message="Writing topic plan manifest")
        topic_plan_path = write_topic_plan_manifest(topic_plan, cfg.manifest_dir, run_id)
        _print(f"Topic plan manifest: {topic_plan_path}")

        if cfg.mode == "folder-rename-only":
            folder_plan = build_folder_rename_plan(actions, cfg)
            apply_folder_renames(folder_plan, cfg, stats, reporter=reporter)
            emit(reporter, phase="manifest", message="Writing folder rename manifest")
            folder_manifest = write_folder_manifest(folder_plan, cfg.manifest_dir, run_id)
            _print(f"Folder audit manifest: {folder_manifest}")

            if cfg.garbage_collect_empty_dirs:
                trashed = garbage_collect_empty_dirs(cfg.source_root, cfg, stats, reporter=reporter)
                emit(reporter, phase="manifest", message="Writing empty-dir trash manifest")
                trash_manifest = write_empty_dir_manifest(trashed, cfg.manifest_dir, run_id)
                _print(f"Empty-dir manifest: {trash_manifest}")

        if cfg.mode != "folder-rename-only":
            apply_actions(actions, cfg, stats, run_id=run_id, reporter=reporter)
            emit(reporter, phase="manifest", message="Writing action manifests")
            csv_path, json_path = write_action_manifest(actions, cfg.manifest_dir, run_id)
            _print(f"CSV manifest: {csv_path}")
            _print(f"JSON manifest: {json_path}")
            trace_path = cfg.rename_trace_file if not cfg.dry_run else cfg.rename_trace_file.with_name("rename_trace_preview.csv")
            _print(f"Rename trace: {trace_path}")

            if cfg.folder_rename_enabled and cfg.mode in {"rename-in-place", "apply-move"}:
                folder_plan = build_folder_rename_plan(actions, cfg)
                apply_folder_renames(folder_plan, cfg, stats, reporter=reporter)
                emit(reporter, phase="manifest", message="Writing folder rename manifest")
                folder_manifest = write_folder_manifest(folder_plan, cfg.manifest_dir, run_id)
                _print(f"Folder audit manifest: {folder_manifest}")

            if cfg.garbage_collect_empty_dirs and cfg.mode in {"apply-move", "rename-in-place"}:
                trashed = garbage_collect_empty_dirs(cfg.source_root, cfg, stats, reporter=reporter)
                emit(reporter, phase="manifest", message="Writing empty-dir trash manifest")
                trash_manifest = write_empty_dir_manifest(trashed, cfg.manifest_dir, run_id)
                _print(f"Empty-dir manifest: {trash_manifest}")

        emit(reporter, phase="state", message="Saving run state")
        save_state(cfg.state_file, state)
        summary = build_summary(stats)
        _print_summary(summary)

        summary_path = cfg.manifest_dir / f"summary_{run_id}.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        _print(f"Summary: {summary_path}")

        emit(reporter, phase="done", message="Run complete", errors=stats.errors, moved=stats.moved + stats.copied, renamed=stats.renamed, skipped=stats.skipped)
        logging.info("Completed run with errors=%s", stats.errors)
        return 0 if stats.errors == 0 else 1
    finally:
        if reporter is not None:
            reporter.close()


if __name__ == "__main__":
    raise SystemExit(main())
