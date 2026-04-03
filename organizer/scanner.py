from __future__ import annotations

from pathlib import Path

from .models import Config, FileRecord
from .progress import ProgressReporter, emit
from .utils import fingerprint_for_file


def discover_files(config: Config, reporter: ProgressReporter | None = None) -> list[FileRecord]:
    source_root = config.source_root
    excluded_roots = [(source_root / p).resolve() for p in config.exclude_paths]
    records: list[FileRecord] = []
    files_seen = 0

    emit(reporter, phase="scanning", message="Walking source tree", current_path=source_root.as_posix(), files_seen=0)

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue

        files_seen += 1

        resolved = path.resolve()
        if any(str(resolved).startswith(str(ex)) for ex in excluded_roots):
            emit(reporter, phase="scanning", files_seen=files_seen, current_path=path.as_posix())
            continue

        ext = path.suffix.lower()
        if ext in config.exclude_extensions:
            emit(reporter, phase="scanning", files_seen=files_seen, current_path=path.as_posix())
            continue
        if ext not in config.supported_extensions:
            emit(reporter, phase="scanning", files_seen=files_seen, current_path=path.as_posix())
            continue

        stat = path.stat()
        rel_path = path.relative_to(source_root)
        records.append(
            FileRecord(
                source_path=path,
                rel_path=rel_path,
                extension=ext,
                size_bytes=stat.st_size,
                modified_ts=stat.st_mtime,
                fingerprint=fingerprint_for_file(rel_path, stat.st_size, stat.st_mtime),
            )
        )
        emit(reporter, phase="scanning", files_seen=files_seen, current_path=path.as_posix(), completed=len(records))

    return records
