from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from .models import ClassificationResult, Config, FileRecord
from .utils import choose_descriptor, extract_json_object, normalize_date, sanitize_folder_path


def _build_prompt(snippet: str, config: Config) -> str:
    taxonomy_text = "\n".join(f"- {t}" for t in config.taxonomy)
    mode_hint = "Use only taxonomy entries" if config.controlled_taxonomy else "Open categorization allowed"

    return (
        "You are a strict JSON classifier for document organization. "
        "Return JSON only, no prose, no markdown.\n"
        "Rules:\n"
        "- descriptor must be 1 word when possible, 2 words max\n"
        "- lowercase and underscore style\n"
        "- avoid generic descriptors unless no better option\n"
        "- include document_date only if materially relevant and confident\n"
        "- if uncertain use folder_path unclear/needs_review\n"
        f"- {mode_hint}\n"
        "Expected schema:\n"
        '{"descriptor":"invoice","date_relevant":true,"document_date":"2024-03-15","folder_path":"finance/invoices","confidence":0.93,"reason":"short reason"}\n\n'
        "Allowed taxonomy:\n"
        f"{taxonomy_text}\n\n"
        "Document snippet:\n"
        f"{snippet[:3500]}"
    )


def _call_ollama(prompt: str, config: Config) -> dict[str, Any]:
    url = f"{config.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=config.timeout_seconds)
            response.raise_for_status()
            body = response.json()
            text = body.get("response", "")
            return extract_json_object(text)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.8 * (2**attempt))

    raise RuntimeError(f"Ollama request failed: {last_error}")


def _sanitize_result(raw: dict[str, Any], config: Config) -> ClassificationResult:
    descriptor = choose_descriptor(str(raw.get("descriptor", "needs_review")), fallback="needs_review")
    confidence = float(raw.get("confidence", 0.0))
    date_relevant = bool(raw.get("date_relevant", False))
    document_date = normalize_date(str(raw.get("document_date"))) if date_relevant else None

    folder_raw = str(raw.get("folder_path", config.review_bucket))
    safe_folder = sanitize_folder_path(folder_raw, config.max_folder_name_words, config.max_folder_depth)

    if config.controlled_taxonomy:
        allowed = {t.lower() for t in config.taxonomy}
        if safe_folder.lower() not in allowed:
            safe_folder = config.review_bucket

    if confidence < config.min_confidence:
        safe_folder = config.review_bucket

    return ClassificationResult(
        descriptor=descriptor,
        date_relevant=date_relevant,
        document_date=document_date,
        folder_path=safe_folder,
        confidence=confidence,
        reason=str(raw.get("reason", ""))[:240],
        normalized_descriptor=descriptor,
        normalized_folder_path=safe_folder,
    )


def classify_single(record: FileRecord, config: Config) -> ClassificationResult:
    if not record.extracted_snippet:
        return ClassificationResult(
            descriptor="needs_review",
            date_relevant=False,
            document_date=None,
            folder_path=config.review_bucket,
            confidence=0.0,
            reason="No extracted content",
            normalized_descriptor="needs_review",
            normalized_folder_path=config.review_bucket,
        )

    prompt = _build_prompt(record.extracted_snippet, config)
    raw = _call_ollama(prompt, config)
    return _sanitize_result(raw, config)


def classify_records(records: list[FileRecord], config: Config) -> dict[str, ClassificationResult]:
    results: dict[str, ClassificationResult] = {}

    def worker(rec: FileRecord) -> tuple[str, ClassificationResult]:
        key = rec.rel_path.as_posix()
        try:
            return key, classify_single(rec, config)
        except Exception as exc:
            return (
                key,
                ClassificationResult(
                    descriptor="needs_review",
                    date_relevant=False,
                    document_date=None,
                    folder_path=config.review_bucket,
                    confidence=0.0,
                    reason=f"Classification error: {exc}",
                    normalized_descriptor="needs_review",
                    normalized_folder_path=config.review_bucket,
                ),
            )

    with ThreadPoolExecutor(max_workers=max(1, config.workers_llm)) as pool:
        for key, value in pool.map(worker, records):
            results[key] = value

    return results


def to_jsonable(result: ClassificationResult) -> dict[str, Any]:
    return {
        "descriptor": result.descriptor,
        "date_relevant": result.date_relevant,
        "document_date": result.document_date,
        "folder_path": result.folder_path,
        "confidence": result.confidence,
        "reason": result.reason,
    }


def from_jsonable(data: dict[str, Any], review_bucket: str) -> ClassificationResult:
    descriptor = choose_descriptor(str(data.get("descriptor", "needs_review")), fallback="needs_review")
    folder = str(data.get("folder_path", review_bucket))
    return ClassificationResult(
        descriptor=descriptor,
        date_relevant=bool(data.get("date_relevant", False)),
        document_date=normalize_date(str(data.get("document_date"))),
        folder_path=folder,
        confidence=float(data.get("confidence", 0.0)),
        reason=str(data.get("reason", "")),
        normalized_descriptor=descriptor,
        normalized_folder_path=folder,
    )
