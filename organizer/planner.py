from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import ClassificationResult, Config, FileRecord, FolderSummary, PlannedAction
from .utils import hash_file, sanitize_token, stable_collision_suffix, stem_for_name


def plan_actions(
    records: list[FileRecord],
    classifications: dict[str, ClassificationResult],
    config: Config,
) -> list[PlannedAction]:
    staged: list[tuple[FileRecord, ClassificationResult, str, str, str]] = []
    duplicate_map: dict[str, Path] = {}

    for rec in records:
        cls = classifications[rec.rel_path.as_posix()]
        descriptor = sanitize_token(
            cls.normalized_descriptor,
            max_words=config.max_file_name_words,
            max_length=config.max_filename_length,
        )
        date = cls.document_date if (config.include_dates and cls.date_relevant) else None
        folder = cls.normalized_folder_path

        if config.detect_duplicates:
            try:
                rec.content_hash = hash_file(rec.source_path)
            except Exception:
                rec.content_hash = None

        staged.append((rec, cls, descriptor, date or "", folder))

    staged.sort(
        key=lambda x: (
            x[4],
            x[2],
            x[3],
            x[0].rel_path.as_posix(),
        )
    )

    groups: dict[tuple[str, str, str, str], list[tuple[FileRecord, ClassificationResult]]] = defaultdict(list)
    for rec, cls, descriptor, date, folder in staged:
        ext = rec.extension.lower().lstrip(".")
        groups[(folder, descriptor, date, ext)].append((rec, cls))

    actions: list[PlannedAction] = []

    for (folder, descriptor, date, ext), members in sorted(groups.items()):
        add_seq = len(members) > 1
        for idx, (rec, cls) in enumerate(members, start=1):
            stem = stem_for_name(date or None, descriptor)
            if add_seq:
                stem = f"{stem}_{idx:03d}"
            filename = f"{stem}.{ext}"

            if config.mode in {"apply-copy", "apply-move"}:
                assert config.output_root is not None
                destination = (config.output_root / folder / filename).resolve()
            elif config.mode in {"rename-in-place", "folder-rename-only"}:
                destination = (config.source_root / folder / filename).resolve()
            else:
                destination = (config.source_root / "_plan_preview" / folder / filename).resolve()

            action_type = "analyze"
            if config.mode == "apply-copy":
                action_type = "copy"
            elif config.mode == "apply-move":
                action_type = "move"
            elif config.mode == "rename-in-place":
                action_type = "rename"
            elif config.mode == "folder-rename-only":
                action_type = "folder-rename"

            duplicate_of = None
            if config.detect_duplicates and rec.content_hash:
                if rec.content_hash in duplicate_map:
                    duplicate_of = duplicate_map[rec.content_hash]
                    if config.skip_duplicates and action_type in {"copy", "move", "rename"}:
                        action_type = "skip"
                else:
                    duplicate_map[rec.content_hash] = rec.source_path

            actions.append(
                PlannedAction(
                    source_path=rec.source_path,
                    rel_source_path=rec.rel_path,
                    action_type=action_type,
                    file_type=rec.extension,
                    extracted_snippet=rec.extracted_snippet[:400],
                    descriptor=descriptor,
                    date_relevant=cls.date_relevant,
                    normalized_date=date or None,
                    folder_path=folder,
                    confidence=cls.confidence,
                    final_filename=filename,
                    final_destination_path=destination,
                    duplicate_of=duplicate_of,
                )
            )

    _dedupe_destinations(actions)
    return actions


def _dedupe_destinations(actions: list[PlannedAction]) -> None:
    seen: dict[str, PlannedAction] = {}

    for action in actions:
        if action.final_destination_path is None:
            continue

        key = action.final_destination_path.as_posix()
        if key not in seen:
            seen[key] = action
            continue

        suffix = stable_collision_suffix(action.rel_source_path)
        stem = Path(action.final_filename).stem
        ext = Path(action.final_filename).suffix
        action.final_filename = f"{stem}_{suffix}{ext}"
        action.final_destination_path = action.final_destination_path.with_name(action.final_filename)


def build_folder_rename_plan(
    actions: list[PlannedAction],
    config: Config,
) -> list[FolderSummary]:
    by_folder: dict[Path, list[PlannedAction]] = defaultdict(list)
    for action in actions:
        by_folder[action.source_path.parent].append(action)

    summaries: list[FolderSummary] = []
    for folder, members in by_folder.items():
        descriptors: dict[str, int] = defaultdict(int)
        for m in members:
            descriptors[m.descriptor] += 1

        top = sorted(descriptors.items(), key=lambda x: (-x[1], x[0]))
        if not top:
            continue

        best_name, count = top[0]
        confidence = count / max(1, len(members))

        if confidence < config.folder_rename_min_confidence:
            continue

        safe_name = sanitize_token(best_name, max_words=config.max_folder_name_words, max_length=42)
        if safe_name == folder.name.lower():
            continue

        summaries.append(
            FolderSummary(
                source_folder=folder,
                proposed_name=safe_name,
                confidence=confidence,
                reason=f"Top descriptor {best_name} in {count}/{len(members)} files",
            )
        )

    summaries.sort(key=lambda s: len(s.source_folder.parts), reverse=True)
    return summaries
