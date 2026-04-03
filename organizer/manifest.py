from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import FolderSummary, PlannedAction, RunStats


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
    json_path = manifest_dir / f"folder_rename_{run_id}.json"
    rows = [
        {
            "source_folder": s.source_folder.as_posix(),
            "proposed_name": s.proposed_name,
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


def build_summary(stats: RunStats) -> dict[str, int]:
    return {
        "total_scanned": stats.total_scanned,
        "supported_files": stats.supported_files,
        "extracted_successfully": stats.extracted_successfully,
        "classified_successfully": stats.classified_successfully,
        "low_confidence_files": stats.low_confidence_files,
        "duplicates": stats.duplicates,
        "renamed": stats.renamed,
        "copied": stats.copied,
        "moved": stats.moved,
        "skipped": stats.skipped,
        "errors": stats.errors,
    }
