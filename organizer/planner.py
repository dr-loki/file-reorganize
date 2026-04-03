from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .models import ClassificationResult, Config, FileRecord, FolderSummary, PlannedAction
from .progress import ProgressReporter, emit
from .utils import hash_file, sanitize_token, stable_collision_suffix, stem_for_name


def _normalize_topic_label(raw: str) -> str:
    base = sanitize_token(raw, max_words=4, max_length=42)
    for suffix in ("_misc", "_other", "_notes", "_files"):
        if base.endswith(suffix):
            return base[: -len(suffix)] or base
    return base


def plan_actions(
    records: list[FileRecord],
    classifications: dict[str, ClassificationResult],
    config: Config,
    reporter: ProgressReporter | None = None,
) -> tuple[list[PlannedAction], dict[str, dict[str, Any]]]:
    staged: list[tuple[FileRecord, ClassificationResult, str, str | None, str, str]] = []
    duplicate_map: dict[str, Path] = {}

    emit(reporter, phase="planning", message="Preparing semantic topic plan")

    for rec in records:
        cls = classifications[rec.rel_path.as_posix()]
        descriptor = sanitize_token(
            cls.normalized_descriptor,
            max_words=config.max_file_name_words,
            max_length=config.max_filename_length,
        )
        date = cls.document_date if (config.include_dates and cls.date_relevant) else None
        parent = _normalize_topic_label(cls.parent_topic or "misc_topics")
        subtopic = _normalize_topic_label(cls.subtopic or "") if cls.subtopic else None
        if parent in {"", "unclear", "needs_review"}:
            parent = "misc_topics"

        if config.detect_duplicates:
            try:
                rec.content_hash = hash_file(rec.source_path)
            except Exception:
                rec.content_hash = None

        staged.append((rec, cls, parent, subtopic, date or "", descriptor))

    staged.sort(
        key=lambda x: (
            x[2],
            x[3],
            x[4],
            x[5],
            x[0].rel_path.as_posix(),
        )
    )

    parent_counts = Counter(parent for _, _, parent, _, _, _ in staged)
    subtopic_counts = Counter((parent, sub or "") for _, _, parent, sub, _, _ in staged if sub)
    large_parents = {topic for topic, count in parent_counts.items() if count >= config.min_topic_size}
    eligible_subtopics = {
        key for key, count in subtopic_counts.items() if count >= config.min_subtopic_size and key[0] in large_parents
    }

    emit(reporter, phase="topic_clustering", message="Building parent/subtopic histogram", completed=0, total=len(parent_counts))

    examples_by_parent: dict[str, list[str]] = defaultdict(list)
    for rec, _, parent, _, _, _ in staged:
        if len(examples_by_parent[parent]) < 3:
            examples_by_parent[parent].append(rec.source_path.as_posix())

    topic_plan: dict[str, dict[str, Any]] = {}
    for idx, (parent, count) in enumerate(sorted(parent_counts.items()), start=1):
        folder = parent if parent in large_parents else "misc_topics"
        planned_subtopics = sorted(
            sub for p, sub in eligible_subtopics if p == parent and sub
        )
        topic_plan[parent] = {
            "folder": folder,
            "parent_topic": parent,
            "subtopics": planned_subtopics,
            "count": count,
            "examples": examples_by_parent[parent],
        }
        emit(
            reporter,
            phase="topic_clustering",
            completed=idx,
            total=len(parent_counts),
            topic_label=parent,
            message=f"count={count}",
        )

    emit(reporter, phase="topic_normalization", message="Collapsing topic variants and pruning weak subtopics")
    emit(
        reporter,
        phase="planning",
        message=f"Parents={len(parent_counts)} dedicated={len(large_parents)} subtopics={len(eligible_subtopics)}",
    )

    groups: dict[tuple[str, str, str | None, str, str, str], list[tuple[FileRecord, ClassificationResult]]] = defaultdict(list)
    for rec, cls, parent, subtopic, date, descriptor in staged:
        ext = rec.extension.lower().lstrip(".")
        folder_parent = parent if parent in large_parents else "misc_topics"
        folder_sub = subtopic if (folder_parent == parent and (parent, subtopic or "") in eligible_subtopics) else None
        folder = f"{folder_parent}/{folder_sub}" if folder_sub else folder_parent
        groups[(folder, folder_parent, folder_sub, descriptor, date, ext)].append((rec, cls))

    actions: list[PlannedAction] = []

    group_items = sorted(groups.items(), key=lambda item: item[0])
    for group_index, ((folder, folder_parent, folder_sub, descriptor, date, ext), members) in enumerate(group_items, start=1):
        add_seq = len(members) > 1
        for idx, (rec, cls) in enumerate(members, start=1):
            if cls.rename_policy == "preserve_original" or cls.confidence < config.min_confidence:
                filename = rec.source_path.name
                preserve_original = True
            elif cls.rename_policy == "hybrid":
                base = sanitize_token(rec.source_path.stem, max_words=4, max_length=config.max_filename_length)
                stem = stem_for_name(date or None, base or descriptor)
                if add_seq:
                    stem = f"{stem}_{idx:03d}"
                filename = f"{stem}.{ext}"
                preserve_original = False
            else:
                stem = stem_for_name(date or None, descriptor)
                if folder_parent == "misc_topics":
                    stem = f"{(cls.subtopic or cls.parent_topic or 'misc')}_{stem}"[: config.max_filename_length].strip("_")
                if add_seq:
                    stem = f"{stem}_{idx:03d}"
                filename = f"{stem}.{ext}"
                preserve_original = False

            if config.mode in {"analyze", "apply-copy", "apply-move"}:
                assert config.output_root is not None
                destination = (config.output_root / folder / filename).resolve()
            elif config.mode in {"rename-in-place", "folder-rename-only"}:
                destination = (config.source_root / folder / filename).resolve()
            else:
                destination = (config.output_root / folder / filename).resolve()

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
                    parent_topic=folder_parent,
                    subtopic=folder_sub,
                    rename_policy=cls.rename_policy,
                    preserve_original_name=preserve_original,
                    topic_label=cls.topic_label or (folder_sub or folder_parent),
                    normalized_topic=cls.normalized_topic,
                    duplicate_of=duplicate_of,
                )
            )

        emit(
            reporter,
            phase="planning",
            completed=group_index,
            total=len(group_items),
            topic_label=f"{folder_parent}/{folder_sub}" if folder_sub else folder_parent,
            message=f"folder={folder}",
        )

    _dedupe_destinations(actions)
    return actions, topic_plan


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

    all_folders = [p for p in config.source_root.rglob("*") if p.is_dir()]
    all_folders.sort(key=lambda p: len(p.parts), reverse=True)

    summaries: list[FolderSummary] = []
    for folder in all_folders:
        members = by_folder.get(folder, [])
        if folder == config.source_root:
            summaries.append(
                FolderSummary(
                    source_folder=folder,
                    proposed_name=folder.name,
                    normalized_name=folder.name,
                    semantic_name=folder.name,
                    action="preserve_with_reason",
                    confidence=1.0,
                    reason="Root folder is preserved",
                    new_path=folder,
                )
            )
            continue

        if not members:
            normalized_name = sanitize_token(folder.name, max_words=config.max_folder_name_words, max_length=42)
            action = "normalize" if normalized_name != folder.name.lower() else "trash_if_empty"
            summaries.append(
                FolderSummary(
                    source_folder=folder,
                    proposed_name=normalized_name if action == "normalize" else folder.name,
                    normalized_name=normalized_name,
                    semantic_name=normalized_name,
                    action=action,
                    confidence=0.6 if action == "normalize" else 0.55,
                    reason="No supported files in folder",
                    new_path=folder.with_name(normalized_name) if action == "normalize" else folder,
                )
            )
            continue

        descriptors: dict[str, int] = defaultdict(int)
        for m in members:
            descriptors[m.descriptor] += 1

        top = sorted(descriptors.items(), key=lambda x: (-x[1], x[0]))
        if not top:
            continue

        best_name, count = top[0]
        confidence = count / max(1, len(members))

        normalized_name = sanitize_token(folder.name, max_words=config.max_folder_name_words, max_length=42)
        safe_name = sanitize_token(best_name, max_words=config.max_folder_name_words, max_length=42)

        action = "preserve_with_reason"
        proposed_name = folder.name
        reason = "Folder already normalized"
        final_confidence = confidence
        if normalized_name != folder.name.lower():
            action = "normalize"
            proposed_name = normalized_name
            reason = "Normalize naming convention"

        if confidence >= config.folder_rename_min_confidence and safe_name and safe_name != normalized_name:
            action = "semantic_rename"
            proposed_name = safe_name
            reason = f"Top descriptor {best_name} in {count}/{len(members)} files"
            final_confidence = confidence

        if proposed_name == folder.name:
            action = "preserve_with_reason"
            reason = "No justified rename"

        summaries.append(
            FolderSummary(
                source_folder=folder,
                proposed_name=proposed_name,
                normalized_name=normalized_name,
                semantic_name=safe_name,
                action=action,
                confidence=final_confidence,
                reason=reason,
                new_path=folder.with_name(proposed_name),
            )
        )

    summaries.sort(key=lambda s: len(s.source_folder.parts), reverse=True)
    return summaries
