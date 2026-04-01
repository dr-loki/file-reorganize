from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Mode = Literal[
    "analyze",
    "apply-copy",
    "apply-move",
    "rename-in-place",
    "folder-rename-only",
]
ActionType = Literal["analyze", "copy", "move", "rename", "folder-rename", "skip"]


@dataclass(slots=True)
class Config:
    source_root: Path
    output_root: Path | None
    mode: Mode
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    timeout_seconds: int = 45
    workers_extract: int = 12
    workers_llm: int = 2
    dry_run: bool = True
    include_dates: bool = True
    max_file_name_words: int = 2
    max_folder_name_words: int = 3
    max_filename_length: int = 80
    max_folder_depth: int = 4
    ocr_enabled: bool = False
    ocr_on_scanned_pdfs: bool = True
    controlled_taxonomy: bool = True
    taxonomy: list[str] = field(default_factory=list)
    min_confidence: float = 0.65
    folder_rename_enabled: bool = False
    folder_rename_min_confidence: float = 0.75
    supported_extensions: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    review_bucket: str = "unclear/needs_review"
    skip_duplicates: bool = True
    detect_duplicates: bool = True
    skip_existing_in_output: bool = True
    state_file: Path | None = None
    manifest_dir: Path | None = None


@dataclass(slots=True)
class FileRecord:
    source_path: Path
    rel_path: Path
    extension: str
    size_bytes: int
    modified_ts: float
    fingerprint: str
    extracted_snippet: str = ""
    extraction_ok: bool = False
    extraction_error: str = ""
    content_hash: str | None = None


@dataclass(slots=True)
class ClassificationResult:
    descriptor: str
    date_relevant: bool
    document_date: str | None
    folder_path: str
    confidence: float
    reason: str
    normalized_descriptor: str = ""
    normalized_folder_path: str = ""


@dataclass(slots=True)
class PlannedAction:
    source_path: Path
    rel_source_path: Path
    action_type: ActionType
    file_type: str
    extracted_snippet: str
    descriptor: str
    date_relevant: bool
    normalized_date: str | None
    folder_path: str
    confidence: float
    final_filename: str
    final_destination_path: Path | None
    status: str = "planned"
    error_message: str = ""
    duplicate_of: Path | None = None


@dataclass(slots=True)
class FolderSummary:
    source_folder: Path
    proposed_name: str
    confidence: float
    reason: str
    status: str = "planned"
    error_message: str = ""


@dataclass(slots=True)
class RunStats:
    total_scanned: int = 0
    supported_files: int = 0
    extracted_successfully: int = 0
    classified_successfully: int = 0
    low_confidence_files: int = 0
    duplicates: int = 0
    renamed: int = 0
    copied: int = 0
    moved: int = 0
    skipped: int = 0
    errors: int = 0
