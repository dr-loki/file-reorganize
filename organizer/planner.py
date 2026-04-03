from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .models import ClassificationResult, Config, FileRecord, FolderSummary, PlannedAction
from .progress import ProgressReporter, emit
from .utils import hash_file, sanitize_token, stable_collision_suffix, stem_for_name

MIN_TOPIC_SIZE = 3


def plan_actions(
    records: list[FileRecord],
    classifications: dict[str, ClassificationResult],
    config: Config,
    reporter: ProgressReporter | None = None,
) -> tuple[list[PlannedAction], dict[str, dict[str, Any]]]:
    staged: list[tuple[FileRecord, ClassificationResult, str, str, str]] = []
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
        topic = cls.normalized_topic or cls.normalized_descriptor or "needs_review"

        if config.detect_duplicates:
            try:
                rec.content_hash = hash_file(rec.source_path)
            except Exception:
                rec.content_hash = None

        staged.append((rec, cls, topic, date or "", descriptor))

    staged.sort(
        key=lambda x: (
            x[2],
            x[3],
            x[4],
            x[0].rel_path.as_posix(),
        )
    )

    topic_counts = Counter(topic for _, _, topic, _, _ in staged)
    large_topics = {topic for topic, count in topic_counts.items() if count >= MIN_TOPIC_SIZE}
    small_topics = {topic for topic, count in topic_counts.items() if count < MIN_TOPIC_SIZE}

    emit(reporter, phase="topic_clustering", message="Building topic histogram", completed=0, total=len(topic_counts))

    examples_by_topic: dict[str, list[str]] = defaultdict(list)
    for rec, _, topic, _, _ in staged:
        if len(examples_by_topic[topic]) < 3:
            examples_by_topic[topic].append(rec.source_path.as_posix())

    topic_plan: dict[str, dict[str, Any]] = {}
    for idx, (topic, count) in enumerate(sorted(topic_counts.items()), start=1):
        folder = topic if topic in large_topics else "misc_topics"
        topic_plan[topic] = {
            "folder": folder,
            "count": count,
            "examples": examples_by_topic[topic],
        }
        emit(
            reporter,
            phase="topic_clustering",
            completed=idx,
            total=len(topic_counts),
            topic_label=topic,
            message=f"count={count}",
        )

    emit(
        reporter,
        phase="planning",
        message=f"Topics={len(topic_counts)} large={len(large_topics)} misc={len(small_topics)}",
    )

    groups: dict[tuple[str, str, str, str, str], list[tuple[FileRecord, ClassificationResult]]] = defaultdict(list)
    for rec, cls, topic, date, descriptor in staged:
        ext = rec.extension.lower().lstrip(".")
        folder = topic if topic in large_topics else "misc_topics"
        groups[(folder, topic, descriptor, date, ext)].append((rec, cls))

    actions: list[PlannedAction] = []

    group_items = sorted(groups.items(), key=lambda item: item[0])
    for group_index, ((folder, topic, descriptor, date, ext), members) in enumerate(group_items, start=1):
        add_seq = len(members) > 1
        for idx, (rec, cls) in enumerate(members, start=1):
            stem = stem_for_name(date or None, descriptor)
            if topic in small_topics:
                stem = f"{topic}_{stem}"[: config.max_filename_length].strip("_")
            if add_seq:
                stem = f"{stem}_{idx:03d}"
            filename = f"{stem}.{ext}"

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
                    topic_label=cls.topic_label or topic,
                    normalized_topic=topic,
                    duplicate_of=duplicate_of,
                )
            )

        emit(
            reporter,
            phase="planning",
            completed=group_index,
            total=len(group_items),
            topic_label=topic,
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
