from __future__ import annotations

from pathlib import Path

from .models import Config, FileRecord
from .utils import fingerprint_for_file


def discover_files(config: Config) -> list[FileRecord]:
    source_root = config.source_root
    excluded_roots = [(source_root / p).resolve() for p in config.exclude_paths]
    records: list[FileRecord] = []

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue

        resolved = path.resolve()
        if any(str(resolved).startswith(str(ex)) for ex in excluded_roots):
            continue

        ext = path.suffix.lower()
        if ext in config.exclude_extensions:
            continue
        if ext not in config.supported_extensions:
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

    return records
