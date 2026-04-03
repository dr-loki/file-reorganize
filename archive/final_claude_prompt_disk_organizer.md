# Final Complete Prompt for Claude

Build a complete, production-grade Python 3.11+ application for Linux that can reorganize a user-selected hard disk or SSD directory tree based on file contents using a local LLM through Ollama.

This must be a real, runnable project, not a sketch, not pseudocode, and not a partial prototype. Return the full project as multiple files with clear file boundaries, plus all required supporting files and exact usage instructions.

## Overall Goal

The application must let a user point the tool at a source directory and then:
- recursively scan files and folders,
- inspect file content,
- infer meaningful short names,
- detect relevant dates,
- classify files into meaningful destination folders,
- optionally rename folders based on aggregate contents,
- generate a dry-run review manifest,
- and then safely copy, move, or rename items according to the plan.

The tool is for large real-world storage trees with many badly named, missing-name, or disorderly named files and folders.

## Non-Negotiable Constraints

- Linux-first.
- Local-only LLM integration through Ollama HTTP API.
- No cloud API dependency.
- Dry-run must be the default behavior.
- Copy mode must be supported and recommended for first real run.
- The source data must never be silently overwritten or deleted.
- The code must be deterministic where possible.
- The code must be resumable for large runs.
- The code must be safe for thousands of files.
- The code must be structured as a real project that is easy to run.

## Deliverables You Must Return

Return the complete project as multiple files with clear headings like:
- `pyproject.toml`
- `requirements.txt` if needed
- `README.md`
- `organizer/__init__.py`
- `organizer/__main__.py`
- `organizer/config.py`
- `organizer/models.py`
- `organizer/scanner.py`
- `organizer/extractors.py`
- `organizer/classify.py`
- `organizer/planner.py`
- `organizer/executor.py`
- `organizer/manifest.py`
- `organizer/utils.py`
- `sample_config.yaml`

If you choose a slightly different structure, it must still be a clean multi-file package with a one-command execution path.

## Execution Requirement

The finished project must be runnable with a single command in one of these forms:
- `python3 -m organizer ...`
- or an installed console command such as `organizer ...`

Prefer the `python3 -m organizer ...` route.

You must include a `__main__.py` entry point and a README with exact install and execution commands.

## Required Modes

Implement these CLI modes:

1. `analyze`
   - scans and classifies only,
   - generates manifest files,
   - makes no filesystem changes.

2. `apply-copy`
   - creates an organized output tree by copying files,
   - leaves source untouched.

3. `apply-move`
   - creates an organized output tree by moving files,
   - should still be safe and explicit.

4. `rename-in-place`
   - renames and reorganizes within the original tree,
   - highest risk,
   - must require an explicit confirmation flag like `--yes-i-understand`.

5. `folder-rename-only`
   - renames folders based on aggregate contents,
   - does not move files.

## Core Functional Requirements

The application must:
- accept a source root path,
- recursively scan the tree,
- identify supported files,
- extract first-page or first-chunk content,
- send content to Ollama for structured classification,
- sanitize and validate model output,
- plan deterministic destination paths,
- number related files safely,
- write review manifests,
- apply the plan only in non-dry-run modes.

## Supported File Types

Support at minimum:
- PDF
- DOCX
- TXT
- MD
- CSV

Optional but preferred:
- image formats via OCR
- HTML
- EML
- XLSX
- PPTX

### Extraction rules

For PDFs:
- use PyMuPDF,
- extract the first page,
- use sorted text extraction when appropriate.

For DOCX:
- extract heading-like content and early paragraphs.

For TXT, MD, CSV:
- extract the first meaningful chunk.

For images:
- optionally OCR with Tesseract if enabled.

For scanned PDFs:
- optionally OCR the first page if text extraction is empty and OCR fallback is enabled.

Unsupported or unreadable files must be skipped cleanly and logged.

## File Naming Rules

All final file names must be short, human-scannable, and deterministic.

Use this naming pattern:
- `[date_]descriptor[_NNN].ext`

Examples:
- `invoice.pdf`
- `contract.pdf`
- `bank_statement.pdf`
- `2024-03-15_invoice.pdf`
- `2024-03-15_invoice_001.pdf`
- `lab_report_002.pdf`

### Descriptor rules

The descriptor must be:
- 1 word if possible,
- maximum 2 words if needed,
- lowercase only,
- underscores instead of spaces,
- no special characters,
- concise and semantically meaningful.

Avoid generic low-value descriptors such as:
- `file`
- `document`
- `scan`
- `image`
- `page`
- `untitled`

unless there is truly no better option.

## Date Rules

If a document is materially date-relevant, include a leading ISO date in `YYYY-MM-DD` format.

Use dates for documents such as:
- invoices,
- receipts,
- statements,
- contracts,
- filings,
- notices,
- letters,
- tax documents,
- medical records,
- meeting notes,
- reports,
- event-bound correspondence.

Do not include a date when:
- no date is confidently extractable,
- the date is ambiguous,
- the date is not materially relevant,
- the document is effectively timeless.

If multiple dates are present, choose the most document-relevant date. Prefer explicit issue/execution/reporting dates over incidental dates. If uncertain, return no date.

## Sequence Numbering Rules

If multiple distinct files in the same destination grouping resolve to the same final base stem, append a zero-padded sequence number:
- `_001`, `_002`, `_003`, etc.

Rules:
- if only one file has the descriptor, do not add a number,
- if multiple files share the same base stem, number all of them consistently,
- numbering must be assigned after the analysis/planning phase,
- numbering must not depend on nondeterministic thread completion order,
- sorting for numbering must be deterministic.

Use stable sort keys such as:
1. destination folder,
2. normalized descriptor,
3. normalized date,
4. source relative path.

## Folder Organization Rules

The application must organize files into meaningful folders named by content.

### Folder naming

Folder names should be:
- usually 1 to 2 words,
- maximum 3 words if necessary,
- lowercase,
- underscores between words,
- no unsafe characters.

Examples:
- `finance`
- `tax_docs`
- `medical_records`
- `legal_contracts`
- `vedic_research`
- `needs_review`

### Folder strategy

Support both:
1. **controlled taxonomy mode**
2. **open categorization mode**

Default to controlled taxonomy mode.

Provide a user-configurable taxonomy in YAML or JSON.

Use this as the default taxonomy:
- `finance/invoices`
- `finance/statements`
- `finance/taxes`
- `legal/contracts`
- `legal/corporate`
- `medical/records`
- `personal/identity`
- `personal/correspondence`
- `research/technical`
- `research/business`
- `research/religious`
- `projects/active`
- `projects/archive`
- `media/photos`
- `media/scans`
- `unclear/needs_review`

If uncertain, the model should choose `unclear/needs_review`.

## Folder Renaming

Support optional folder renaming based on aggregate contents.

Rules:
- infer folder name from representative files inside the folder,
- allow up to 3 words for folder names,
- skip rename if confidence is low or contents are too mixed,
- rename deepest folders first,
- support a minimum confidence threshold for folder renaming.

## Ollama Integration

Use Ollama locally via HTTP.

Requirements:
- default base URL: `http://localhost:11434`
- configurable model name,
- configurable timeout,
- retry with backoff on transient failures,
- bounded concurrency.

Do not use a cloud model.

### Model output contract

For file classification, require strict JSON shaped like this:

```json
{
  "descriptor": "invoice",
  "date_relevant": true,
  "document_date": "2024-03-15",
  "folder_path": "finance/invoices",
  "confidence": 0.93,
  "reason": "Invoice dated March 15, 2024"
}
```

Validate and sanitize all model output in Python. Never trust model output blindly.

### Prompt requirements for classification

The prompt must instruct the model to:
- return JSON only,
- avoid prose,
- prefer one-word descriptors,
- use two words max for file descriptors,
- include date only if materially relevant,
- choose from taxonomy when controlled taxonomy mode is active,
- route uncertain files to `unclear/needs_review`.

## Safety Requirements

Safety is critical.

You must implement:
- dry-run by default,
- CSV manifest output,
- JSON manifest output,
- explicit logging,
- safe collision handling,
- support for copy mode,
- support for exclude paths and extensions,
- resume support,
- no silent overwrite,
- no destructive delete logic,
- no remote upload.

### Manifest fields

Each manifest entry should include:
- source path,
- relative source path,
- file type,
- extracted snippet,
- descriptor,
- date relevance,
- normalized date,
- folder path,
- confidence,
- final proposed filename,
- final destination path,
- action type,
- status,
- error message if any.

## Duplicate and Collision Handling

The code must distinguish between:
1. exact duplicate files,
2. same descriptor but different files,
3. destination path collisions.

Required behavior:
- optionally detect exact duplicates by size plus hash,
- optionally skip duplicate copies if configured,
- if different files share descriptor/date/folder, assign `_001`, `_002`, etc.,
- if collision still remains, append a stable suffix.

## Parallelism and Performance

Implement bounded parallelism.

### Pipeline stages

Use a staged pipeline:
1. filesystem discovery,
2. content extraction,
3. LLM classification,
4. planning,
5. execution.

### Concurrency rules

- Use `ThreadPoolExecutor` for filesystem scanning and content extraction.
- Use bounded concurrency for Ollama requests, default small pool such as 1 to 3 workers.
- Do not let thread completion order affect numbering.
- Perform final planning only after analysis is complete.
- Keep apply/commit stage serialized or carefully controlled.

### Resume and cache

Support resumable operation for large trees.

Include:
- optional state file,
- optional content hash cache,
- skip re-analysis if unchanged and cache is valid,
- progress output.

## CLI Design

Use `argparse`, `click`, or `typer`.

The CLI must support commands like:

```bash
python3 -m organizer analyze /source/path --config sample_config.yaml
python3 -m organizer apply-copy /source/path /organized/output --config sample_config.yaml
python3 -m organizer apply-move /source/path /organized/output --config sample_config.yaml
python3 -m organizer rename-in-place /source/path --yes-i-understand --config sample_config.yaml
python3 -m organizer folder-rename-only /source/path --dry-run --config sample_config.yaml
```

## Configuration

Provide a sample config file, preferably YAML.

It should include fields like:

```yaml
source_root: /path/to/source
output_root: /path/to/output
mode: analyze
ollama_url: http://localhost:11434
model: llama3.2:3b
workers_extract: 12
workers_llm: 2
dry_run: true
include_dates: true
max_file_name_words: 2
max_folder_name_words: 3
ocr_enabled: false
ocr_on_scanned_pdfs: true
controlled_taxonomy: true
min_confidence: 0.65
folder_rename_enabled: false
folder_rename_min_confidence: 0.75
supported_extensions:
  - .pdf
  - .docx
  - .txt
  - .md
  - .csv
exclude_paths: []
exclude_extensions: []
review_bucket: unclear/needs_review
skip_duplicates: true
```

## Internal Architecture

Implement a clean modular design.

Suggested modules:
- configuration loading,
- data models,
- scanning,
- extraction,
- classification,
- planning,
- execution,
- manifest/report writing,
- shared utilities.

Use dataclasses or Pydantic models for core records.

Suggested models:
- `Config`
- `FileRecord`
- `ClassificationResult`
- `PlannedAction`
- `FolderSummary`

## Sanitization and Validation

Implement strong sanitization.

### File and folder names

Must:
- normalize Unicode to ASCII where possible,
- lowercase,
- remove unsafe characters,
- replace whitespace with underscores,
- collapse repeated underscores,
- trim trailing dots and spaces,
- enforce max length,
- enforce max word count.

### Date normalization

Must:
- parse likely date strings,
- normalize to `YYYY-MM-DD`,
- reject impossible dates,
- return null if uncertain.

### Folder path sanitization

Must:
- prevent absolute paths,
- prevent path traversal,
- normalize separators,
- cap folder depth,
- reject unsafe or empty components.

## Logging and Reports

Provide:
- console progress output,
- structured log file,
- CSV manifest,
- JSON manifest,
- end-of-run summary stats.

Summary stats should include:
- total scanned,
- supported files,
- extracted successfully,
- classified successfully,
- low-confidence files,
- duplicates,
- renamed,
- copied,
- moved,
- skipped,
- errors.

## Preferred Dependencies

Use practical Python packages only.

Preferred:
- `requests`
- `PyMuPDF`
- `python-docx`
- `PyYAML`
- `rich` or `tqdm`
- `pydantic` or `dataclasses`
- `Pillow` and `pytesseract` only if OCR is enabled

Avoid unnecessary bloat.

## Installation Instructions You Must Include

Include exact installation instructions in the README, such as:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Code Quality Requirements

The code must be:
- complete,
- runnable,
- modular,
- robust,
- readable,
- type-hinted where practical,
- well-structured for maintenance,
- explicit around dangerous operations,
- suitable for large real-world directory trees.

Include comments only where they help explain non-obvious logic.

## Explicit Non-Goals

Do not build:
- a GUI,
- an Electron app,
- a web app,
- a cloud dependency,
- a daemon,
- destructive deletion logic,
- remote document storage.

## Output Formatting Requirement

Return the full project in clearly separated file blocks, each with the filename as a heading and then the exact contents.

Also include:
1. a short architecture overview,
2. exact install commands,
3. exact run commands,
4. a recommended first dry-run workflow.

## Final Instruction

Now build the complete project exactly as specified above. Do not summarize the design. Do not ask clarifying questions. Do not return pseudocode. Return the full codebase and supporting files in one response.
