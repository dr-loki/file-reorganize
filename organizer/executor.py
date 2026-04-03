from __future__ import annotations

import csv
import logging
import shutil
from pathlib import Path

from .models import Config, EmptyDirTrashAction, FolderSummary, PlannedAction, RunStats
from .progress import ProgressReporter, emit


def _validate_destination(path: Path, skip_existing: bool) -> tuple[bool, str]:
    if path.exists():
        if skip_existing:
            return False, "Destination exists"
        return False, "Destination collision"
    return True, ""


def _relative_path(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def append_rename_trace_row(csv_path: Path, row: list[object]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                [
                    "run_id",
                    "action_type",
                    "old_rel_path",
                    "new_rel_path",
                    "old_filename",
                    "new_filename",
                    "old_parent",
                    "new_parent",
                    "confidence",
                    "parent_topic",
                    "subtopic",
                    "rename_policy",
                    "status",
                    "reason",
                    "duplicate_of",
                    "preserved_original_name",
                ]
            )
        writer.writerow(row)


def apply_actions(
    actions: list[PlannedAction],
    config: Config,
    stats: RunStats,
    run_id: str,
    reporter: ProgressReporter | None = None,
) -> None:
    created_dirs = 0
    trace_csv = config.rename_trace_file if not config.dry_run else config.rename_trace_file.with_name("rename_trace_preview.csv")

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
            if action.final_destination_path is not None and action.final_destination_path != action.source_path:
                append_rename_trace_row(
                    trace_csv,
                    [
                        run_id,
                        action.action_type,
                        _relative_path(action.source_path, config.source_root),
                        _relative_path(action.final_destination_path, config.output_root if config.mode in {"analyze", "apply-copy", "apply-move"} else config.source_root),
                        action.source_path.name,
                        action.final_destination_path.name,
                        _relative_path(action.source_path.parent, config.source_root),
                        _relative_path(action.final_destination_path.parent, config.output_root if config.mode in {"analyze", "apply-copy", "apply-move"} else config.source_root),
                        f"{action.confidence:.3f}",
                        action.parent_topic,
                        action.subtopic or "",
                        action.rename_policy,
                        "preview",
                        "dry-run",
                        action.duplicate_of.as_posix() if action.duplicate_of else "",
                        str(action.preserve_original_name).lower(),
                    ],
                )
                stats.rename_trace_rows += 1
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
            if action.final_destination_path != action.source_path:
                append_rename_trace_row(
                    trace_csv,
                    [
                        run_id,
                        action.action_type,
                        _relative_path(action.source_path, config.source_root),
                        _relative_path(action.final_destination_path, config.output_root if config.mode in {"analyze", "apply-copy", "apply-move"} else config.source_root),
                        action.source_path.name,
                        action.final_destination_path.name,
                        _relative_path(action.source_path.parent, config.source_root),
                        _relative_path(action.final_destination_path.parent, config.output_root if config.mode in {"analyze", "apply-copy", "apply-move"} else config.source_root),
                        f"{action.confidence:.3f}",
                        action.parent_topic,
                        action.subtopic or "",
                        action.rename_policy,
                        "applied",
                        "",
                        action.duplicate_of.as_posix() if action.duplicate_of else "",
                        str(action.preserve_original_name).lower(),
                    ],
                )
                stats.rename_trace_rows += 1
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
        target = summary.new_path or summary.source_folder.with_name(summary.proposed_name)

        if summary.action in {"preserve_with_reason", "trash_if_empty"}:
            summary.status = "skipped"
            emit(reporter, phase="folder_audit", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
            continue

        if target == summary.source_folder:
            summary.status = "skipped"
            emit(reporter, phase="folder_audit", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
            continue

        if target.exists():
            summary.status = "skipped"
            summary.error_message = "Target folder already exists"
            stats.skipped += 1
            emit(reporter, phase="folder_audit", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
            continue

        if config.dry_run:
            summary.status = "dry-run"
            emit(reporter, phase="folder_audit", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)
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

        emit(reporter, phase="folder_audit", completed=idx, total=len(summaries), current_path=summary.source_folder.as_posix(), renamed=stats.renamed, skipped=stats.skipped, errors=stats.errors)


def garbage_collect_empty_dirs(
    root: Path,
    config: Config,
    stats: RunStats,
    reporter: ProgressReporter | None = None,
) -> list[EmptyDirTrashAction]:
    trash_root = root / config.trash_empty_dir_name
    protected = {
        trash_root.resolve(),
        config.manifest_dir.resolve(),
        config.log_dir.resolve(),
    }

    actions: list[EmptyDirTrashAction] = []
    candidates = [p for p in root.rglob("*") if p.is_dir()]
    candidates.sort(key=lambda p: len(p.parts), reverse=True)

    for idx, folder in enumerate(candidates, start=1):
        resolved = folder.resolve()
        if resolved in protected:
            continue
        if any(str(resolved).startswith(str(pp)) for pp in protected):
            continue
        if folder == root:
            continue
        if any(folder.iterdir()):
            continue

        relative = folder.relative_to(root)
        target = trash_root / relative
        action = EmptyDirTrashAction(old_path=folder, new_path=target)

        if config.dry_run:
            action.status = "dry-run"
            actions.append(action)
            emit(reporter, phase="garbage_collect", completed=idx, total=len(candidates), current_path=folder.as_posix(), skipped=stats.skipped, errors=stats.errors)
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(target))
            action.status = "applied"
            stats.empty_dirs_trashed += 1
        except Exception as exc:
            action.status = "error"
            action.error_message = str(exc)
            stats.errors += 1
            logging.exception("Failed to trash empty directory %s", folder)

        actions.append(action)
        emit(reporter, phase="garbage_collect", completed=idx, total=len(candidates), current_path=folder.as_posix(), skipped=stats.skipped, errors=stats.errors)

    return actions
