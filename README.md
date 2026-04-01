# file-reorganize
Content‑aware, LLM‑powered disk organizer for Linux.


This project is a content‑aware disk reorganization tool that uses a local LLM (via Ollama) to rename and sort files and folders based on what’s actually inside them, not just their existing filenames.

Point it at a root directory and it will:

Recursively scan documents (PDF, DOCX, TXT, MD, CSV, with optional OCR for scans).

Extract first-page or first-chunk text from each file.

Ask a local LLM to infer a short descriptor, an optional document date, and a semantic category.

Generate compact, human-readable filenames like 2024-03-15_invoice_001.pdf (1–2 word descriptors, ISO dates when relevant, and _001 style numbering for related files).

Organize files into meaningful folders (for example finance/invoices, legal/contracts, medical/records, research/technical, unclear/needs_review), using a configurable taxonomy.

Optionally rename folders based on the aggregate content of their files.

The tool is designed to be Linux-first, local-only, and safety‑focused:

Dry‑run is the default; it always produces CSV/JSON manifests so you can review proposed moves and renames before committing anything.

Supports multiple modes: analyze-only, copy into a new organized tree, move into a new tree, rename in place, and folder‑rename‑only.

Uses bounded parallelism for fast content extraction with a small, controlled worker pool for LLM calls.

Never silently overwrites or deletes files, and handles name collisions deterministically with stable numbering and safe suffixes.

The goal is to turn a chaotic SSD full of badly named documents into an intelligible, date-aware and category-aware archive, while keeping everything local, auditable, and reversible.
