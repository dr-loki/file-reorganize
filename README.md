<<<<<<< HEAD
# Disk ReOrganizer

Production-grade Python 3.11+ CLI that reorganizes large Linux directory trees using local Ollama classification, deterministic planning, and safe apply modes.

## Architecture Overview

The application is organized into staged modules:

- `organizer/scanner.py`: recursive discovery with extension and path filtering.
- `organizer/extractors.py`: bounded parallel extraction for PDF, DOCX, TXT, MD, CSV (with optional OCR fallback).
- `organizer/classify.py`: local Ollama calls with retry/backoff and strict JSON output sanitization.
- `organizer/planner.py`: deterministic path planning, numbering, duplicate detection, and collision handling.
- `organizer/executor.py`: safe copy/move/rename execution with dry-run defaults and no overwrite behavior.
- `organizer/manifest.py`: CSV/JSON manifest and summary generation.
- `organizer/__main__.py`: CLI orchestration, resumable state cache, and mode execution.

## Safety Defaults

- Dry-run is enabled by default.
- `apply-copy` is the recommended first real run.
- No silent overwrite.
- No destructive delete logic.
- `rename-in-place` requires `--yes-i-understand`.
- Manifest and logs are always generated under `manifest_dir`.

## Install

Linux-first setup:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional OCR dependencies:

```bash
pip install "Pillow>=10.0.0" "pytesseract>=0.3.10"
# Also install system tesseract package on Linux, e.g.:
# sudo apt-get install -y tesseract-ocr
```

## Run Commands

Use one-command execution through module entrypoint:

```bash
python3 -m organizer analyze /source/path --config sample_config.yaml
python3 -m organizer apply-copy /source/path /organized/output --config sample_config.yaml
python3 -m organizer apply-move /source/path /organized/output --config sample_config.yaml
python3 -m organizer rename-in-place /source/path --yes-i-understand --config sample_config.yaml
python3 -m organizer folder-rename-only /source/path --config sample_config.yaml
```

### Notes

- `--no-dry-run` enables real writes for apply/rename modes.
- `--model`, `--ollama-url`, `--workers-extract`, and `--workers-llm` can override config file values.

## Recommended First Dry-Run Workflow

```bash
# 1) Configure paths and model
cp sample_config.yaml my_config.yaml

# 2) Analyze only (safe)
python3 -m organizer analyze /data/messy_drive --config my_config.yaml

# 3) Review manifests
ls -lah /data/messy_drive/.organizer_manifests

# 4) First real run: copy mode (preserves source)
python3 -m organizer apply-copy /data/messy_drive /data/organized_copy --config my_config.yaml --no-dry-run

# 5) Optional advanced run after review
python3 -m organizer apply-move /data/messy_drive /data/organized_final --config my_config.yaml --no-dry-run
```

## Manifest Fields

Each action entry includes:

- source path
- relative source path
- file type
- extracted snippet
- descriptor
- date relevance
- normalized date
- folder path
- confidence
- final proposed filename
- final destination path
- action type
- status
- error message

## Project Layout

- `pyproject.toml`
- `requirements.txt`
- `sample_config.yaml`
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
=======
# Disk ReOrganizer

Production-grade Python 3.11+ CLI that reorganizes large Linux directory trees using local Ollama classification, deterministic planning, and safe apply modes.

## Architecture Overview

The application is organized into staged modules:

- `organizer/scanner.py`: recursive discovery with extension and path filtering.
- `organizer/extractors.py`: bounded parallel extraction for PDF, DOCX, TXT, MD, CSV (with optional OCR fallback).
- `organizer/classify.py`: local Ollama calls with retry/backoff and strict JSON output sanitization.
- `organizer/planner.py`: deterministic path planning, numbering, duplicate detection, and collision handling.
- `organizer/executor.py`: safe copy/move/rename execution with dry-run defaults and no overwrite behavior.
- `organizer/manifest.py`: CSV/JSON manifest and summary generation.
- `organizer/__main__.py`: CLI orchestration, resumable state cache, and mode execution.

## Safety Defaults

- Dry-run is enabled by default.
- `apply-copy` is the recommended first real run.
- No silent overwrite.
- No destructive delete logic.
- `rename-in-place` requires `--yes-i-understand`.
- Manifest and logs are always generated under `manifest_dir`.

## Install

Linux-first setup:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional OCR dependencies:

```bash
pip install "Pillow>=10.0.0" "pytesseract>=0.3.10"
# Also install system tesseract package on Linux, e.g.:
# sudo apt-get install -y tesseract-ocr
```

## Run Commands

Use one-command execution through module entrypoint:

```bash
python3 -m organizer analyze /source/path --config sample_config.yaml
python3 -m organizer apply-copy /source/path /organized/output --config sample_config.yaml
python3 -m organizer apply-move /source/path /organized/output --config sample_config.yaml
python3 -m organizer rename-in-place /source/path --yes-i-understand --config sample_config.yaml
python3 -m organizer folder-rename-only /source/path --config sample_config.yaml
```

### Notes

- `--no-dry-run` enables real writes for apply/rename modes.
- `--model`, `--ollama-url`, `--workers-extract`, and `--workers-llm` can override config file values.

## Recommended First Dry-Run Workflow

```bash
# 1) Configure paths and model
cp sample_config.yaml my_config.yaml

# 2) Analyze only (safe)
python3 -m organizer analyze /data/messy_drive --config my_config.yaml

# 3) Review manifests
ls -lah /data/messy_drive/.organizer_manifests

# 4) First real run: copy mode (preserves source)
python3 -m organizer apply-copy /data/messy_drive /data/organized_copy --config my_config.yaml --no-dry-run

# 5) Optional advanced run after review
python3 -m organizer apply-move /data/messy_drive /data/organized_final --config my_config.yaml --no-dry-run
```

## Manifest Fields

Each action entry includes:

- source path
- relative source path
- file type
- extracted snippet
- descriptor
- date relevance
- normalized date
- folder path
- confidence
- final proposed filename
- final destination path
- action type
- status
- error message

## Project Layout

- `pyproject.toml`
- `requirements.txt`
- `sample_config.yaml`
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
>>>>>>> fb11a3aff437569db5be90222a529837814e7c73
