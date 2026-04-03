from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import EmptyDirTrashAction, FolderSummary, PlannedAction, RunStats


def write_action_manifest(actions: list[PlannedAction], manifest_dir: Path, run_id: str) -> tuple[Path, Path]:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = manifest_dir / f"manifest_{run_id}.csv"
    json_path = manifest_dir / f"manifest_{run_id}.json"

    fields = [
        "source_path",
        "relative_source_path",
        "file_type",
        "extracted_snippet",
        "descriptor",
        "parent_topic",
        "subtopic",
        "rename_policy",
        "preserve_original_name",
        "topic_label",
        "normalized_topic",
        "date_relevant",
        "normalized_date",
        "folder_path",
        "confidence",
        "final_proposed_filename",
        "final_destination_path",
        "action_type",
        "status",
        "error_message",
    ]

    rows = []
    for a in actions:
        rows.append(
            {
                "source_path": a.source_path.as_posix(),
                "relative_source_path": a.rel_source_path.as_posix(),
                "file_type": a.file_type,
                "extracted_snippet": a.extracted_snippet,
                "descriptor": a.descriptor,
                "parent_topic": a.parent_topic,
                "subtopic": a.subtopic,
                "rename_policy": a.rename_policy,
                "preserve_original_name": a.preserve_original_name,
                "topic_label": a.topic_label,
                "normalized_topic": a.normalized_topic,
                "date_relevant": a.date_relevant,
                "normalized_date": a.normalized_date,
                "folder_path": a.folder_path,
                "confidence": a.confidence,
                "final_proposed_filename": a.final_filename,
                "final_destination_path": a.final_destination_path.as_posix() if a.final_destination_path else "",
                "action_type": a.action_type,
                "status": a.status,
                "error_message": a.error_message,
            }
        )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=True)

    return csv_path, json_path


def write_topic_plan_manifest(topic_plan: dict[str, dict[str, object]], manifest_dir: Path, run_id: str) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    json_path = manifest_dir / f"topic_plan_{run_id}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(topic_plan, f, indent=2, ensure_ascii=True)
    return json_path


def write_folder_manifest(summaries: list[FolderSummary], manifest_dir: Path, run_id: str) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    json_path = manifest_dir / f"folder_audit_{run_id}.json"
    rows = [
        {
            "source_folder": s.source_folder.as_posix(),
            "action": s.action,
            "normalized_name": s.normalized_name,
            "semantic_name": s.semantic_name,
            "proposed_name": s.proposed_name,
            "new_path": s.new_path.as_posix() if s.new_path else "",
            "confidence": s.confidence,
            "reason": s.reason,
            "status": s.status,
            "error_message": s.error_message,
        }
        for s in summaries
    ]

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=True)

    return json_path


def write_empty_dir_manifest(actions: list[EmptyDirTrashAction], manifest_dir: Path, run_id: str) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    json_path = manifest_dir / f"empty_dirs_{run_id}.json"
    rows = [
        {
            "old_path": a.old_path.as_posix(),
            "new_path": a.new_path.as_posix(),
            "status": a.status,
            "error_message": a.error_message,
        }
        for a in actions
    ]
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=True)
    return json_path


def build_summary(stats: RunStats) -> dict[str, int]:
    return {
        "total_scanned": stats.total_scanned,
        "supported_files": stats.supported_files,
        "extracted_successfully": stats.extracted_successfully,
        "classified_successfully": stats.classified_successfully,
        "low_confidence_files": stats.low_confidence_files,
        "low_confidence_preserved_names": stats.low_confidence_preserved_names,
        "cache_hits": stats.cache_hits,
        "cache_misses": stats.cache_misses,
        "duplicates": stats.duplicates,
        "topic_folders_created": stats.topic_folders_created,
        "subtopic_folders_created": stats.subtopic_folders_created,
        "files_routed_to_misc": stats.files_routed_to_misc,
        "empty_dirs_trashed": stats.empty_dirs_trashed,
        "rename_trace_rows": stats.rename_trace_rows,
        "renamed": stats.renamed,
        "copied": stats.copied,
        "moved": stats.moved,
        "skipped": stats.skipped,
        "errors": stats.errors,
    }
