from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .models import Config, FolderSummary, PlannedAction, RunStats
from .progress import ProgressReporter, emit


def _validate_destination(path: Path, skip_existing: bool) -> tuple[bool, str]:
    if path.exists():
        if skip_existing:
            return False, "Destination exists"
        return False, "Destination collision"
    return True, ""


def apply_actions(
    actions: list[PlannedAction],
    config: Config,
    stats: RunStats,
    reporter: ProgressReporter | None = None,
) -> None:
    created_dirs = 0

    for idx, action in enumerate(actions, start=1):
        if action.action_type in {"analyze", "folder-rename", "skip"}:
            action.status = "skipped" if action.action_type == "skip" else "planned"
            if action.action_type == "skip":
                stats.skipped += 1
            emit(
                reporter,
                phase="moving",
                completed=idx,
                total=len(actions),
                current_path=action.source_path.as_posix(),
                topic_label=action.normalized_topic,
                moved=stats.moved + stats.copied,
                skipped=stats.skipped,
                errors=stats.errors,
            )
            continue

        if action.final_destination_path is None:
            action.status = "error"
            action.error_message = "Missing destination"
            stats.errors += 1
            emit(
                reporter,
                phase="moving",
                completed=idx,
                total=len(actions),
                current_path=action.source_path.as_posix(),
                topic_label=action.normalized_topic,
                moved=stats.moved + stats.copied,
                skipped=stats.skipped,
                errors=stats.errors,
            )
            continue

        phase = "renaming" if action.action_type == "rename" else "moving"

        if config.dry_run:
            action.status = "dry-run"
            emit(
                reporter,
                phase=phase,
                completed=idx,
                total=len(actions),
                current_path=action.source_path.as_posix(),
                topic_label=action.normalized_topic,
                moved=stats.moved + stats.copied,
                renamed=stats.renamed,
                skipped=stats.skipped,
                errors=stats.errors,
            )
            continue

        ok, msg = _validate_destination(action.final_destination_path, config.skip_existing_in_output)
        if not ok:
            action.status = "skipped"
            action.error_message = msg
            stats.skipped += 1
            emit(
                reporter,
                phase=phase,
                completed=idx,
                total=len(actions),
                current_path=action.source_path.as_posix(),
                topic_label=action.normalized_topic,
                moved=stats.moved + stats.copied,
                renamed=stats.renamed,
                skipped=stats.skipped,
                errors=stats.errors,
            )
            continue

        if not action.final_destination_path.parent.exists():
            action.final_destination_path.parent.mkdir(parents=True, exist_ok=True)
            created_dirs += 1
            emit(
                reporter,
                phase="mkdir",
                completed=created_dirs,
                current_path=action.final_destination_path.parent.as_posix(),
                created_dirs=created_dirs,
                errors=stats.errors,
            )

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

        emit(
            reporter,
            phase=phase,
            completed=idx,
            total=len(actions),
            current_path=action.source_path.as_posix(),
            topic_label=action.normalized_topic,
            moved=stats.moved + stats.copied,
            renamed=stats.renamed,
            skipped=stats.skipped,
            errors=stats.errors,
        )


def apply_folder_renames(
    summaries: list[FolderSummary],
    config: Config,
    stats: RunStats,
    reporter: ProgressReporter | None = None,
) -> None:
    for idx, summary in enumerate(summaries, start=1):
        target = summary.source_folder.with_name(summary.proposed_name)

        if target == summary.source_folder:
            summary.status = "skipped"
            emit(reporter, phase="renaming", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
            continue

        if target.exists():
            summary.status = "skipped"
            summary.error_message = "Target folder already exists"
            stats.skipped += 1
            emit(reporter, phase="renaming", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
            continue

        if config.dry_run:
            summary.status = "dry-run"
            emit(reporter, phase="renaming", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
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

        emit(reporter, phase="renaming", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
