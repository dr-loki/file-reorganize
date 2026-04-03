from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

PhaseName = Literal[
    "startup",
    "scanning",
    "extracting",
    "classifying",
    "topic_clustering",
    "planning",
    "mkdir",
    "renaming",
    "moving",
    "manifest",
    "state",
    "done",
]


@dataclass(slots=True)
class ProgressEvent:
    phase: PhaseName
    message: str | None = None
    current_path: str | None = None
    ontology: str | None = None
    topic_label: str | None = None
    completed: int | None = None
    total: int | None = None
    files_seen: int | None = None
    moved: int | None = None
    renamed: int | None = None
    created_dirs: int | None = None
    skipped: int | None = None
    errors: int | None = None


class ProgressReporter(Protocol):
    def emit(self, event: ProgressEvent) -> None: ...

    def close(self) -> None: ...


def emit(reporter: ProgressReporter | None, **kwargs: object) -> None:
    if reporter is None:
        return
    reporter.emit(ProgressEvent(**kwargs))
