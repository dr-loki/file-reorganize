from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(0[1-9]|[12]\d|3[01])[-/](0[1-9]|1[0-2])[-/](20\d{2})\b"),
    re.compile(r"\b(0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])[-/](20\d{2})\b"),
]

GENERIC_DESCRIPTORS = {"file", "document", "scan", "image", "page", "untitled"}


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def normalize_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def sanitize_token(value: str, max_words: int, max_length: int) -> str:
    s = normalize_ascii(value).lower().strip()
    s = re.sub(r"[^a-z0-9\s_-]", " ", s)
    s = re.sub(r"[\s-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_. ")
    words = [w for w in s.split("_") if w]
    if max_words > 0:
        words = words[:max_words]
    s = "_".join(words)
    s = s[:max_length].strip("_. ")
    return s or "needs_review"


def sanitize_folder_path(path: str, max_words: int, max_depth: int) -> str:
    raw_parts = [p for p in path.replace("\\", "/").split("/") if p and p not in {".", ".."}]
    safe_parts: list[str] = []
    for part in raw_parts[:max_depth]:
        clean = sanitize_token(part, max_words=max_words, max_length=32)
        if clean:
            safe_parts.append(clean)
    return "/".join(safe_parts) if safe_parts else "unclear/needs_review"


def normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.strip()

    for pattern in DATE_PATTERNS:
        match = pattern.search(v)
        if not match:
            continue
        groups = match.groups()
        try:
            if pattern is DATE_PATTERNS[0]:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif pattern is DATE_PATTERNS[1]:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
            parsed = datetime(year, month, day)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(v, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def choose_descriptor(candidate: str, fallback: str = "needs_review") -> str:
    safe = sanitize_token(candidate, max_words=2, max_length=40)
    if safe in GENERIC_DESCRIPTORS:
        return fallback
    return safe


def stem_for_name(date: str | None, descriptor: str) -> str:
    return f"{date}_{descriptor}" if date else descriptor


def fingerprint_for_file(path: Path, size: int, modified_ts: float) -> str:
    return f"{path.as_posix()}|{size}|{int(modified_ts)}"


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def stable_collision_suffix(source_rel: Path) -> str:
    digest = hashlib.sha1(source_rel.as_posix().encode("utf-8")).hexdigest()[:8]
    return digest


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError("No JSON object found")
    candidate = text[start : end + 1]
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("Expected JSON object")
    return obj


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"files": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"files": {}}
        if "files" not in data or not isinstance(data["files"], dict):
            data["files"] = {}
        return data
    except Exception:
        return {"files": {}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=True)
