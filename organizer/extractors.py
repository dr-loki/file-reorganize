from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

import fitz
from docx import Document

from .models import Config, FileRecord

try:
    from PIL import Image
    import pytesseract
except Exception:  # pragma: no cover
    Image = None
    pytesseract = None


def _read_text_file(path: Path, max_chars: int = 3500) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return raw.strip()[:max_chars]


def _extract_pdf(path: Path, config: Config, max_chars: int = 3500) -> str:
    with fitz.open(path) as doc:
        if not doc:
            return ""
        first_page = doc[0]
        text = first_page.get_text("text", sort=True).strip()
        if text:
            return text[:max_chars]

        if config.ocr_on_scanned_pdfs and config.ocr_enabled and pytesseract and Image:
            pix = first_page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr = pytesseract.image_to_string(img).strip()
            return ocr[:max_chars]

    return ""


def _extract_docx(path: Path, max_chars: int = 3500) -> str:
    doc = Document(path)
    chunks: list[str] = []

    for p in doc.paragraphs:
        txt = (p.text or "").strip()
        if not txt:
            continue
        style = (p.style.name if p.style is not None else "").lower()
        if "heading" in style:
            chunks.append(f"# {txt}")
        else:
            chunks.append(txt)
        if len("\n".join(chunks)) >= max_chars:
            break

    return "\n".join(chunks)[:max_chars]


def _extract_csv(path: Path, max_chars: int = 3500) -> str:
    out = StringIO()
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        for idx, row in enumerate(reader):
            out.write(", ".join(cell.strip() for cell in row))
            out.write("\n")
            if idx >= 24:
                break
    return out.getvalue().strip()[:max_chars]


def _extract_image(path: Path, config: Config, max_chars: int = 3500) -> str:
    if not config.ocr_enabled or not pytesseract or not Image:
        return ""
    with Image.open(path) as img:
        return pytesseract.image_to_string(img).strip()[:max_chars]


def extract_single(record: FileRecord, config: Config) -> FileRecord:
    path = record.source_path
    try:
        if record.extension == ".pdf":
            snippet = _extract_pdf(path, config)
        elif record.extension == ".docx":
            snippet = _extract_docx(path)
        elif record.extension in {".txt", ".md"}:
            snippet = _read_text_file(path)
        elif record.extension == ".csv":
            snippet = _extract_csv(path)
        elif record.extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
            snippet = _extract_image(path, config)
        else:
            snippet = ""

        record.extracted_snippet = snippet
        record.extraction_ok = bool(snippet)
        if not snippet:
            record.extraction_error = "No content extracted"
    except Exception as exc:
        record.extraction_ok = False
        record.extraction_error = str(exc)

    return record


def extract_records(records: list[FileRecord], config: Config) -> list[FileRecord]:
    if not records:
        return []

    with ThreadPoolExecutor(max_workers=max(1, config.workers_extract)) as pool:
        return list(pool.map(lambda r: extract_single(r, config), records))
