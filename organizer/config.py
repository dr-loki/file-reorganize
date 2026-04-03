from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Config, Mode

DEFAULT_TAXONOMY = [
    "finance/invoices",
    "finance/statements",
    "finance/taxes",
    "legal/contracts",
    "legal/corporate",
    "medical/records",
    "personal/identity",
    "personal/correspondence",
    "research/technical",
    "research/business",
    "research/religious",
    "projects/active",
    "projects/archive",
    "media/photos",
    "media/scans",
    "unclear/needs_review",
]

DEFAULT_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".csv"]


class ConfigError(ValueError):
    pass


def _mode_from_str(raw: str) -> Mode:
    allowed: set[str] = {
        "analyze",
        "apply-copy",
        "apply-move",
        "rename-in-place",
        "folder-rename-only",
    }
    if raw not in allowed:
        raise ConfigError(f"Unsupported mode: {raw}")
    return raw  # type: ignore[return-value]


def _as_path(v: Any) -> Path | None:
    if v is None:
        return None
    return Path(str(v)).expanduser()


def load_config(config_path: Path | None, cli_overrides: dict[str, Any]) -> Config:
    data: dict[str, Any] = {}
    if config_path is not None:
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            raise ConfigError("Config must be a mapping")
        data = loaded

    merged = {**data, **{k: v for k, v in cli_overrides.items() if v is not None}}

    source_root = _as_path(merged.get("source_root"))
    output_root = _as_path(merged.get("output_root"))
    mode_raw = merged.get("mode", "analyze")

    if source_root is None:
        raise ConfigError("source_root is required")

    config = Config(
        source_root=source_root,
        output_root=output_root,
        mode=_mode_from_str(str(mode_raw)),
        ollama_url=str(merged.get("ollama_url", "http://localhost:11434")),
        model=str(merged.get("model", "llama3.2:3b")),
        timeout_seconds=int(merged.get("timeout_seconds", 45)),
        workers_extract=int(merged.get("workers_extract", 12)),
        workers_llm=int(merged.get("workers_llm", 2)),
        dry_run=bool(merged.get("dry_run", True)),
        include_dates=bool(merged.get("include_dates", True)),
        max_file_name_words=int(merged.get("max_file_name_words", 2)),
        max_folder_name_words=int(merged.get("max_folder_name_words", 3)),
        max_filename_length=int(merged.get("max_filename_length", 80)),
        max_folder_depth=int(merged.get("max_folder_depth", 4)),
        ocr_enabled=bool(merged.get("ocr_enabled", False)),
        ocr_on_scanned_pdfs=bool(merged.get("ocr_on_scanned_pdfs", True)),
        controlled_taxonomy=bool(merged.get("controlled_taxonomy", True)),
        taxonomy=list(merged.get("taxonomy", DEFAULT_TAXONOMY)),
        min_confidence=float(merged.get("min_confidence", 0.65)),
        folder_rename_enabled=bool(merged.get("folder_rename_enabled", False)),
        folder_rename_min_confidence=float(merged.get("folder_rename_min_confidence", 0.75)),
        supported_extensions=[s.lower() for s in merged.get("supported_extensions", DEFAULT_EXTENSIONS)],
        exclude_paths=list(merged.get("exclude_paths", [])),
        exclude_extensions=[s.lower() for s in merged.get("exclude_extensions", [])],
        review_bucket=str(merged.get("review_bucket", "unclear/needs_review")),
        skip_duplicates=bool(merged.get("skip_duplicates", True)),
        detect_duplicates=bool(merged.get("detect_duplicates", True)),
        skip_existing_in_output=bool(merged.get("skip_existing_in_output", True)),
        state_file=_as_path(merged.get("state_file")),
        manifest_dir=_as_path(merged.get("manifest_dir")),
        log_dir=_as_path(merged.get("log_dir")),
    )

    config.finalize()

    if not config.source_root.exists() or not config.source_root.is_dir():
        raise ConfigError(f"source_root does not exist or is not a directory: {config.source_root}")

    return config
