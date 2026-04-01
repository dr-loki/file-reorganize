from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .classify import classify_records, from_jsonable, to_jsonable
from .config import ConfigError, load_config
from .executor import apply_actions, apply_folder_renames
from .extractors import extract_records
from .manifest import build_summary, write_action_manifest, write_folder_manifest
from .models import FileRecord, RunStats
from .planner import build_folder_rename_plan, plan_actions
from .scanner import discover_files
from .utils import load_state, save_state, setup_logging

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organizer",
        description="Disk ReOrganizer: content-aware local LLM disk organizer",
    )
    parser.add_argument("mode", choices=["analyze", "apply-copy", "apply-move", "rename-in-place", "folder-rename-only"])
    parser.add_argument("source_root", type=str)
    parser.add_argument("output_root", nargs="?", default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--ollama-url", type=str, default=None)
    parser.add_argument("--workers-extract", type=int, default=None)
    parser.add_argument("--workers-llm", type=int, default=None)
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
        "model": args.model,
        "ollama_url": args.ollama_url,
        "workers_extract": args.workers_extract,
        "workers_llm": args.workers_llm,
        "dry_run": dry_run,
    }


def _use_cache(record: FileRecord, state: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    key = record.rel_path.as_posix()
    cached = state.get("files", {}).get(key)
    if not isinstance(cached, dict):
        return False, None
    if cached.get("fingerprint") != record.fingerprint:
        return False, None
    return True, cached


def _print_summary(summary: dict[str, int]) -> None:
    table = Table(title="Run Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, val in summary.items():
        table.add_row(key, str(val))
    console.print(table)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        cfg = load_config(Path(args.config) if args.config else None, _build_cli_overrides(args))
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        return 2

    if cfg.mode == "rename-in-place" and not args.yes_i_understand:
        console.print("[red]rename-in-place requires --yes-i-understand[/red]")
        return 2

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    setup_logging(cfg.manifest_dir / f"run_{run_id}.log")

    if cfg.mode in {"analyze", "folder-rename-only"} and args.no_dry_run:
        console.print("[yellow]Warning:[/yellow] no-dry-run requested in a non-destructive mode")

    state = load_state(cfg.state_file)
    stats = RunStats()

    logging.info("Starting mode=%s source=%s", cfg.mode, cfg.source_root)

    records = discover_files(cfg)
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
        extract_records(extract_targets, cfg)
    stats.extracted_successfully = sum(1 for r in records if r.extraction_ok)

    classify_targets = [r for r in records if r.rel_path.as_posix() not in classifications]
    if classify_targets:
        classified = classify_records(classify_targets, cfg)
        classifications.update(classified)

    for rec in records:
        cls = classifications[rec.rel_path.as_posix()]
        if cls.confidence >= cfg.min_confidence:
            stats.classified_successfully += 1
        else:
            stats.low_confidence_files += 1

        state["files"][rec.rel_path.as_posix()] = {
            "fingerprint": rec.fingerprint,
            "snippet": rec.extracted_snippet,
            "classification": to_jsonable(cls),
        }

    actions = plan_actions(records, classifications, cfg)
    stats.duplicates = sum(1 for a in actions if a.duplicate_of is not None)

    if cfg.mode == "folder-rename-only":
        folder_plan = build_folder_rename_plan(actions, cfg)
        apply_folder_renames(folder_plan, cfg, stats)
        folder_manifest = write_folder_manifest(folder_plan, cfg.manifest_dir, run_id)
        console.print(f"Folder rename manifest: {folder_manifest}")

    if cfg.mode != "folder-rename-only":
        apply_actions(actions, cfg, stats)
        csv_path, json_path = write_action_manifest(actions, cfg.manifest_dir, run_id)
        console.print(f"CSV manifest: {csv_path}")
        console.print(f"JSON manifest: {json_path}")

        if cfg.folder_rename_enabled and cfg.mode in {"rename-in-place", "apply-move"}:
            folder_plan = build_folder_rename_plan(actions, cfg)
            apply_folder_renames(folder_plan, cfg, stats)
            folder_manifest = write_folder_manifest(folder_plan, cfg.manifest_dir, run_id)
            console.print(f"Folder rename manifest: {folder_manifest}")

    save_state(cfg.state_file, state)
    summary = build_summary(stats)
    _print_summary(summary)

    summary_path = cfg.manifest_dir / f"summary_{run_id}.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    console.print(f"Summary: {summary_path}")

    logging.info("Completed run with errors=%s", stats.errors)
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
