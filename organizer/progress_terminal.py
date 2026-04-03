from __future__ import annotations

import sys
import time

from .progress import ProgressEvent


class TerminalProgressReporter:
    def __init__(self, min_interval: float = 0.25, detailed: bool = False):
        self.min_interval = min_interval
        self.detailed = detailed
        self._last_render = 0.0
        self._last_phase: str | None = None

    def emit(self, event: ProgressEvent) -> None:
        now = time.monotonic()
        phase_changed = event.phase != self._last_phase
        if not phase_changed and now - self._last_render < self.min_interval:
            return

        self._last_phase = event.phase
        self._last_render = now
        rendered = self._format(event)[:220]
        sys.stderr.write("\r" + rendered + " " * 30)
        sys.stderr.flush()

    def _format(self, event: ProgressEvent) -> str:
        bits = [f"Phase: {event.phase}"]
        if event.message:
            bits.append(event.message)
        if event.completed is not None and event.total:
            bits.append(f"{event.completed}/{event.total}")
        elif event.files_seen is not None:
            bits.append(f"files: {event.files_seen}")
        if event.moved is not None:
            bits.append(f"moved: {event.moved}")
        if event.renamed is not None:
            bits.append(f"renamed: {event.renamed}")
        if event.created_dirs is not None:
            bits.append(f"mkdir: {event.created_dirs}")
        if event.skipped is not None:
            bits.append(f"skipped: {event.skipped}")
        if event.errors is not None:
            bits.append(f"errors: {event.errors}")
        if self.detailed and event.topic_label:
            bits.append(f"topic: {event.topic_label}")
        if self.detailed and event.current_path:
            bits.append(f"current: {event.current_path}")
        return " | ".join(bits)

    def close(self) -> None:
        sys.stderr.write("\n")
        sys.stderr.flush()
