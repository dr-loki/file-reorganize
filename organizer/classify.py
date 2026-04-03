from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from .models import ClassificationResult, Config, FileRecord
from .progress import ProgressReporter, emit
from .utils import (
    build_classification_cache_key,
    choose_descriptor,
    extract_json_object,
    first_meaningful_line,
    infer_date_from_text,
    normalize_date,
    normalize_snippet_text,
    sanitize_folder_path,
    sanitize_token,
)

TOPIC_MAX_WORDS = 4
_PROMPT_PREFIX = (
    "You are a strict JSON classifier for document organization. Return JSON only.\n"
    "System rules:\n"
    "- Use stable lowercase underscore labels\n"
    "- Choose parent_topic and optional subtopic\n"
    "- Use rename_policy: generated|hybrid|preserve_original\n"
    "- Preserve original names for low confidence\n"
    "- confidence and topic_confidence in [0,1]\n"
)


def _split_parent_subtopic(path: str) -> tuple[str, str | None]:
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if not parts:
        return "misc_topics", None
    parent = sanitize_token(parts[0], max_words=4, max_length=36)
    subtopic = sanitize_token(parts[1], max_words=4, max_length=36) if len(parts) > 1 else None
    return parent or "misc_topics", subtopic or None


def _build_prompt(snippet: str, config: Config) -> str:
    taxonomy_text = "\n".join(f"- {t}" for t in config.taxonomy)
    mode_hint = "Use only taxonomy entries" if config.controlled_taxonomy else "Open categorization allowed"

    return (
        _PROMPT_PREFIX
        +
        "Rules:\n"
        "- descriptor must be 1 word when possible, 2 words max\n"
        "- topic_label must be 2 to 4 words and content-driven\n"
        "- parent_topic must be broader than subtopic\n"
        "- set subtopic null when weak\n"
        "- avoid generic descriptors unless no better option\n"
        "- include document_date only if materially relevant and confident\n"
        "- if uncertain use parent_topic misc_topics and rename_policy preserve_original\n"
        f"- {mode_hint}\n"
        "Expected schema:\n"
        '{"descriptor":"invoice","date_relevant":true,"document_date":"2024-03-15","folder_path":"finance/taxes","parent_topic":"finance","subtopic":"taxes","topic_label":"annual_tax_return","rename_policy":"generated","confidence":0.93,"topic_confidence":0.92,"ambiguous":false,"reason":"short reason"}\n\n'
        "Allowed taxonomy:\n"
        f"{taxonomy_text}\n\n"
        "Document snippet:\n"
        f"{snippet[: config.max_heavy_chars]}"
    )


def _call_ollama(prompt: str, config: Config) -> dict[str, Any]:
    url = f"{config.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.keep_alive,
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
    topic_confidence = float(raw.get("topic_confidence", confidence))
    date_relevant = bool(raw.get("date_relevant", False))
    document_date = normalize_date(str(raw.get("document_date"))) if date_relevant else None
    raw_topic = str(raw.get("topic_label", "")).strip()
    if not raw_topic:
        raw_topic = descriptor
    raw_parent = str(raw.get("parent_topic", "")).strip()
    raw_subtopic = raw.get("subtopic")
    rename_policy = str(raw.get("rename_policy", "generated")).strip().lower()
    if rename_policy not in {"generated", "preserve_original", "hybrid"}:
        rename_policy = "preserve_original"

    folder_raw = str(raw.get("folder_path", config.review_bucket))
    safe_folder = sanitize_folder_path(folder_raw, config.max_folder_name_words, config.max_folder_depth)
    parent_topic, subtopic = _split_parent_subtopic(safe_folder)
    if raw_parent:
        parent_topic = sanitize_token(raw_parent, max_words=4, max_length=36)
    if raw_subtopic not in {None, "", "null"}:
        subtopic = sanitize_token(str(raw_subtopic), max_words=4, max_length=36)

    normalized_topic = sanitize_token(raw_topic, max_words=TOPIC_MAX_WORDS, max_length=42)
    if not normalized_topic:
        normalized_topic = descriptor or "needs_review"

    if config.controlled_taxonomy:
        allowed = {t.lower() for t in config.taxonomy}
        if safe_folder.lower() not in allowed:
            safe_folder = f"{parent_topic}/{subtopic}" if subtopic else parent_topic

    if confidence < config.min_confidence:
        parent_topic = "misc_topics"
        subtopic = None
        safe_folder = config.review_bucket
        normalized_topic = descriptor or "needs_review"
        rename_policy = "preserve_original"

    return ClassificationResult(
        descriptor=descriptor,
        date_relevant=date_relevant,
        document_date=document_date,
        folder_path=safe_folder,
        confidence=confidence,
        reason=str(raw.get("reason", ""))[:240],
        parent_topic=parent_topic,
        subtopic=subtopic,
        rename_policy=rename_policy,
        topic_confidence=topic_confidence,
        ambiguous=bool(raw.get("ambiguous", False)) or confidence < config.min_confidence,
        normalized_descriptor=descriptor,
        normalized_folder_path=safe_folder,
        topic_label=raw_topic,
        normalized_topic=normalized_topic,
    )


def _fast_infer(record: FileRecord, config: Config) -> ClassificationResult:
    filename = record.source_path.stem
    normalized_name = sanitize_token(filename, max_words=4, max_length=42)
    snippet = normalize_snippet_text(record.extracted_snippet, max_chars=config.max_light_chars)
    first_line = first_meaningful_line(record.extracted_snippet)

    tokens = [t for t in normalized_name.split("_") if t]
    descriptor = choose_descriptor(tokens[0] if tokens else record.extension.lstrip("."), fallback="file")

    parent_topic = "misc_topics"
    subtopic: str | None = None
    confidence = 0.42

    ext = record.extension.lower()
    if ext in {".md", ".txt"}:
        parent_topic = "notes"
        confidence += 0.1
    elif ext in {".pdf", ".docx"}:
        parent_topic = "documents"
        confidence += 0.08
    elif ext in {".csv"}:
        parent_topic = "data"
        confidence += 0.1

    if "invoice" in normalized_name or "receipt" in normalized_name:
        parent_topic = "finance"
        subtopic = "billing"
        confidence = 0.78
    elif "tax" in normalized_name:
        parent_topic = "finance"
        subtopic = "taxes"
        confidence = 0.81
    elif "transit" in normalized_name or "natal" in normalized_name or "astrology" in normalized_name:
        parent_topic = "astrology"
        if "transit" in normalized_name:
            subtopic = "transits"
        if "natal" in normalized_name:
            subtopic = "natal"
        confidence = 0.79
    elif "project" in normalized_name or "proposal" in normalized_name:
        parent_topic = "projects"
        subtopic = descriptor if descriptor not in {"file", "document"} else None
        confidence = 0.74

    if snippet and len(snippet) > 180:
        confidence += 0.07
    if first_line:
        confidence += 0.05
    confidence = min(0.9, confidence)

    if confidence >= config.medium_confidence:
        rename_policy = "generated"
    elif confidence >= config.min_confidence:
        rename_policy = "hybrid"
    else:
        rename_policy = "preserve_original"

    document_date = infer_date_from_text(record.extracted_snippet)
    folder = f"{parent_topic}/{subtopic}" if subtopic else parent_topic
    return ClassificationResult(
        descriptor=descriptor,
        date_relevant=document_date is not None,
        document_date=document_date,
        folder_path=folder,
        confidence=confidence,
        reason="fast-pass inference",
        parent_topic=parent_topic,
        subtopic=subtopic,
        rename_policy=rename_policy,
        topic_confidence=confidence,
        ambiguous=confidence < config.medium_confidence,
        normalized_descriptor=descriptor,
        normalized_folder_path=folder,
        topic_label=subtopic or parent_topic,
        normalized_topic=sanitize_token(subtopic or parent_topic, max_words=TOPIC_MAX_WORDS, max_length=42),
    )


def classify_single(record: FileRecord, config: Config) -> ClassificationResult:
    if not record.extracted_snippet:
        return ClassificationResult(
            descriptor="file",
            date_relevant=False,
            document_date=None,
            folder_path="misc_topics",
            confidence=0.0,
            reason="No extracted content",
            parent_topic="misc_topics",
            subtopic=None,
            rename_policy="preserve_original",
            topic_confidence=0.0,
            ambiguous=True,
            normalized_descriptor="file",
            normalized_folder_path="misc_topics",
            topic_label="misc_topics",
            normalized_topic="misc_topics",
        )

    fast = _fast_infer(record, config)
    if fast.confidence >= config.medium_confidence:
        return fast

    prompt = _build_prompt(record.extracted_snippet, config)
    raw = _call_ollama(prompt, config)
    heavy = _sanitize_result(raw, config)
    if heavy.confidence >= fast.confidence:
        return heavy
    return fast


def classify_records(
    records: list[FileRecord],
    config: Config,
    reporter: ProgressReporter | None = None,
    classification_cache: dict[str, dict[str, Any]] | None = None,
    concept_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, ClassificationResult]:
    results: dict[str, ClassificationResult] = {}
    class_cache = classification_cache if classification_cache is not None else {}
    concept = concept_cache if concept_cache is not None else {}

    def worker(rec: FileRecord) -> tuple[str, ClassificationResult]:
        key = rec.rel_path.as_posix()
        cache_key = build_classification_cache_key(
            filename=rec.source_path.name,
            extension=rec.extension,
            snippet=rec.extracted_snippet,
            model_name=config.model,
            prompt_version=config.prompt_version,
            schema_version=config.schema_version,
        )

        cached = class_cache.get(cache_key)
        if isinstance(cached, dict):
            out = from_jsonable(cached, config.review_bucket)
            out.cache_key = cache_key
            out.cache_hit = True
            return key, out

        try:
            out = classify_single(rec, config)
            out.cache_key = cache_key
            out.cache_hit = False
            class_cache[cache_key] = to_jsonable(out)
            concept[cache_key] = {
                "parent_topic": out.parent_topic,
                "subtopic": out.subtopic,
                "descriptor": out.descriptor,
                "confidence": out.confidence,
                "topic_confidence": out.topic_confidence,
                "rename_policy": out.rename_policy,
                "ambiguous": out.ambiguous,
                "reason": out.reason,
                "prompt_version": config.prompt_version,
                "schema_version": config.schema_version,
                "model_name": config.model,
            }
            return key, out
        except Exception as exc:
            return (
                key,
                ClassificationResult(
                    descriptor="file",
                    date_relevant=False,
                    document_date=None,
                    folder_path="misc_topics",
                    confidence=0.0,
                    reason=f"Classification error: {exc}",
                    parent_topic="misc_topics",
                    subtopic=None,
                    rename_policy="preserve_original",
                    topic_confidence=0.0,
                    ambiguous=True,
                    normalized_descriptor="file",
                    normalized_folder_path="misc_topics",
                    topic_label="misc_topics",
                    normalized_topic="misc_topics",
                    cache_key=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                    cache_hit=False,
                ),
            )

    emit(reporter, phase="classifying", message="Classifying extracted content", completed=0, total=len(records))

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, config.workers_llm)) as pool:
        future_map = {pool.submit(worker, record): record for record in records}
        for future in as_completed(future_map):
            key, value = future.result()
            results[key] = value
            completed += 1
            emit(
                reporter,
                phase="classifying",
                completed=completed,
                total=len(records),
                current_path=future_map[future].source_path.as_posix(),
                topic_label=value.normalized_topic,
            )

    return results


def to_jsonable(result: ClassificationResult) -> dict[str, Any]:
    return {
        "descriptor": result.descriptor,
        "date_relevant": result.date_relevant,
        "document_date": result.document_date,
        "folder_path": result.folder_path,
        "confidence": result.confidence,
        "reason": result.reason,
        "parent_topic": result.parent_topic,
        "subtopic": result.subtopic,
        "rename_policy": result.rename_policy,
        "topic_confidence": result.topic_confidence,
        "ambiguous": result.ambiguous,
        "topic_label": result.topic_label,
        "normalized_topic": result.normalized_topic,
        "cache_key": result.cache_key,
        "cache_hit": result.cache_hit,
    }


def from_jsonable(data: dict[str, Any], review_bucket: str) -> ClassificationResult:
    descriptor = choose_descriptor(str(data.get("descriptor", "file")), fallback="file")
    folder = str(data.get("folder_path", review_bucket))
    parent_topic, subtopic = _split_parent_subtopic(folder)
    return ClassificationResult(
        descriptor=descriptor,
        date_relevant=bool(data.get("date_relevant", False)),
        document_date=normalize_date(str(data.get("document_date"))),
        folder_path=folder,
        confidence=float(data.get("confidence", 0.0)),
        reason=str(data.get("reason", "")),
        parent_topic=str(data.get("parent_topic", parent_topic)),
        subtopic=data.get("subtopic", subtopic),
        rename_policy=str(data.get("rename_policy", "preserve_original")),
        topic_confidence=float(data.get("topic_confidence", data.get("confidence", 0.0))),
        ambiguous=bool(data.get("ambiguous", False)),
        normalized_descriptor=descriptor,
        normalized_folder_path=folder,
        topic_label=str(data.get("topic_label", descriptor)),
        normalized_topic=sanitize_token(
            str(data.get("normalized_topic", data.get("topic_label", descriptor))),
            max_words=TOPIC_MAX_WORDS,
            max_length=42,
        ) or descriptor,
        cache_key=str(data.get("cache_key", "")),
        cache_hit=bool(data.get("cache_hit", False)),
    )
