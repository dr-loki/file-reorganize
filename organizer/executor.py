from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .models import Config, FolderSummary, PlannedAction, RunStats


def _safe_prepare_destination(path: Path, skip_existing: bool) -> tuple[bool, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if skip_existing:
            return False, "Destination exists"
        return False, "Destination collision"
    return True, ""


def apply_actions(actions: list[PlannedAction], config: Config, stats: RunStats) -> None:
    for action in actions:
        if action.action_type in {"analyze", "folder-rename", "skip"}:
            action.status = "skipped" if action.action_type == "skip" else "planned"
            if action.action_type == "skip":
                stats.skipped += 1
            continue

        if action.final_destination_path is None:
            action.status = "error"
            action.error_message = "Missing destination"
            stats.errors += 1
            continue

        ok, msg = _safe_prepare_destination(action.final_destination_path, config.skip_existing_in_output)
        if not ok:
            action.status = "skipped"
            action.error_message = msg
            stats.skipped += 1
            continue

        if config.dry_run:
            action.status = "dry-run"
            continue

        try:
            if action.action_type == "copy":
                shutil.copy2(action.source_path, action.final_destination_path)
                stats.copied += 1
            elif action.action_type == "move":
                shutil.move(str(action.source_path), str(action.final_destination_path))
                stats.moved += 1
            elif action.action_type == "rename":
                if action.source_path.resolve() == action.final_destination_path.resolve():
                    action.status = "skipped"
                    continue
                shutil.move(str(action.source_path), str(action.final_destination_path))
                stats.renamed += 1
            action.status = "applied"
        except Exception as exc:
            action.status = "error"
            action.error_message = str(exc)
            stats.errors += 1
            logging.exception("Action failed for %s", action.source_path)


def apply_folder_renames(summaries: list[FolderSummary], config: Config, stats: RunStats) -> None:
    for summary in summaries:
        target = summary.source_folder.with_name(summary.proposed_name)

        if target == summary.source_folder:
            summary.status = "skipped"
            continue

        if target.exists():
            summary.status = "skipped"
            summary.error_message = "Target folder already exists"
            stats.skipped += 1
            continue

        if config.dry_run:
            summary.status = "dry-run"
            continue

        try:
            summary.source_folder.rename(target)
            summary.status = "applied"
            stats.renamed += 1
        except Exception as exc:
            summary.status = "error"
            summary.error_message = str(exc)
            stats.errors += 1
            logging.exception("Folder rename failed for %s", summary.source_folder)
