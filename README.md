# Disk ReOrganizer

Disk ReOrganizer is a Python 3.11+ local file organizer that extracts content, asks a local Ollama model for semantic labeling, builds a full topic plan, and then safely analyzes, copies, moves, or renames files.

## What This Refactor Added

- Lightweight terminal progress reporting with clear phases.
- Hierarchical parent/subtopic planning with corpus-wide normalization.
- Minimum topic and subtopic size thresholds (default 3).
- Small/weak topics routed into `misc_topics`.
- Low-confidence files preserve original filenames.
- Staged classification: fast pass first, heavy LLM only when needed.
- Content-hash classification cache + concept cache with prompt/schema versioning.
- Keep-alive support for Ollama model reuse.
- Full folder audit (`normalize`, `semantic_rename`, `preserve_with_reason`, `trash_if_empty`).
- Empty-folder garbage collection into `.trash_empty_dirs`.
- Incremental rename trace output (`rename_trace.csv` or dry-run preview).
- Early dependency checks, including GUI `tkinter` detection.
- A `doctor` command for quick environment validation.

## Standard Install

Recommended base install:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install .
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

If you prefer the plain requirements file instead of package install:

```bash
pip install -r requirements.txt
```

## Optional OCR Support

OCR is optional. To install the OCR extra:

### Windows PowerShell

```powershell
pip install ".[ocr]"
```

### Linux/macOS

```bash
pip install '.[ocr]'
```

You also need the system Tesseract binary installed if OCR is enabled.

## GUI / Tkinter Requirement

GUI mode uses `tkinter`.

- Windows and macOS usually include it with Python.
- Linux often requires an OS package.

Examples:

- Ubuntu/Debian: `sudo apt install python3-tk`
- Fedora: `sudo dnf install python3-tkinter`
- Arch: ensure Python was built with Tk support

The organizer now checks this early and fails fast with a clear message if GUI mode is requested without Tk support.

## Quick Validation

Check the CLI is installed and imports are available:

```bash
python -m organizer analyze --help
```

Run the environment doctor:

```bash
python -m organizer doctor
```

## Progress Reporting

Progress is shown in these phases:

- `startup`
- `scanning`
- `extracting`
- `classifying`
- `topic_clustering`
- `topic_normalization`
- `planning`
- `folder_audit`
- `garbage_collect`
- `mkdir`
- `renaming`
- `moving`
- `manifest`
- `state`
- `done`

CLI flags:

```bash
python -m organizer analyze --progress basic
python -m organizer analyze --progress detailed
python -m organizer analyze --progress off
python -m organizer analyze --progress detailed --progress-refresh-ms 250
```

- `basic` shows phase and counts.
- `detailed` also shows current path and topic label.
- updates are throttled to avoid terminal spam.

## Semantic Topic Planning

The organizer now performs corpus-wide hierarchical planning before any move/rename.

Rules:

- each file is classified with `parent_topic`, optional `subtopic`, confidence, and rename policy
- parent topics are normalized across variants before planning
- parent/subtopic folders are created only when thresholds are met
- weak subtopics collapse into parent; weak parents collapse into `misc_topics`
- low-confidence files keep original filename stems
- full topic plan is computed and written before execution

A topic plan manifest is written to:

```text
<manifest_dir>/topic_plan_<run_id>.json
```

## Quick Start

### Analyze with GUI

```bash
python -m organizer analyze --gui
```

### Apply-copy with GUI

```bash
python -m organizer apply-copy --gui
```

### Apply-move with GUI

```bash
python -m organizer apply-move --gui
```

### Rename in place

```bash
python -m organizer rename-in-place --gui --yes-i-understand
```

## YAML Configuration Example

```yaml
source_root: C:/data/messy_source
output_root: C:/data/messy_source_out
mode: analyze
ocr_enabled: false

# Optional derived paths:
# manifest_dir: C:/data/messy_source_out/.organizer_manifests
# state_file: C:/data/messy_source_out/.organizer_manifests/state.json
# log_dir: C:/data/messy_source_out/.organizer_manifests
```

Run with config:

```bash
python -m organizer analyze --config sample_config.yaml
```

## Useful CLI Overrides

```bash
python -m organizer analyze \
  --source-root "C:/data/messy_source" \
  --output-root "C:/data/messy_source_out" \
  --keep-alive "20m" \
  --progress detailed
```

Path-related flags:

- `--source-root`
- `--output-root`
- `--manifest-dir`
- `--state-file`
- `--log-dir`

## Modes

| Mode | Behavior |
| :-- | :-- |
| analyze | Read-only planning and manifest generation |
| apply-copy | Copies files into the planned topic folder structure |
| apply-move | Moves files into the planned topic folder structure |
| rename-in-place | Renames and reorganizes inside the source tree |
| folder-rename-only | Renames folders only |
| doctor | Validates environment dependencies |

## Safety Notes

- Dry-run is enabled by default.
- Dry-run no longer creates misleading empty directories before skipping execution.
- `rename-in-place` requires `--yes-i-understand`.
- Topic planning happens before execution; execution only applies the precomputed plan.
- Missing dependencies are checked before long-running work begins.
- Empty directories are moved to `.trash_empty_dirs` rather than permanently deleted.

## Manifests Produced

- `topic_plan_<run_id>.json`
- `manifest_<run_id>.csv`
- `manifest_<run_id>.json`
- `folder_audit_<run_id>.json` when folder audit is run
- `empty_dirs_<run_id>.json` when garbage collection runs
- `rename_trace.csv` (or `rename_trace_preview.csv` in dry-run)
- `summary_<run_id>.json`
- `state.json`

## Cache Internals

The organizer persists cache data in `state.json` under the manifest directory.

Current cache layers:

- `files`: fingerprint-based reuse by relative path (`size + mtime`), storing snippet and last classification.
- `classification_cache`: content-hash keyed classification reuse across path changes.
- `concept_cache`: intermediate concept fields (`parent_topic`, `subtopic`, `descriptor`, confidence, rename policy).

Classification cache key inputs:

- normalized filename
- extension
- normalized extracted snippet
- model name
- `prompt_version`
- `schema_version`

This means cache invalidates cleanly when prompt/schema/model changes, while unchanged content can be reused across reruns.

Recommended settings for stable reuse:

- keep `prompt_version` and `schema_version` stable unless behavior changes intentionally
- avoid changing model name between benchmark runs
- keep prompt prefix/instructions deterministic

Relevant config keys:

- `cache_enabled`
- `prompt_version`
- `schema_version`
- `keep_alive`

Note: the summary includes `cache_hits` and `cache_misses` from classification requests that pass through the classifier stage.

## Install Troubleshooting

If `python -m organizer doctor` fails:

1. Install the missing Python package shown in the output.
2. If the missing item is `tkinter`, install the OS package for Tk support.
3. If OCR packages are missing, install the OCR extra with `pip install .[ocr]`.
4. If Ollama is unreachable, start Ollama locally and verify the configured URL.
