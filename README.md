# Disk ReOrganizer

Disk ReOrganizer is a Python 3.11+ CLI that reorganizes files using local Ollama classification, deterministic planning, and safe execution modes.

## What Changed In This Refactor

- All runtime paths are now centralized in configuration.
- `source_root` and `output_root` are the primary path inputs.
- Optional path fields are derived automatically when omitted:
  - `manifest_dir` defaults to `<output_root>/.organizer_manifests`
  - `state_file` defaults to `<manifest_dir>/state.json`
  - `log_dir` defaults to `<manifest_dir>`
- Optional GUI flow (`--gui`) allows folder selection dialogs.
- GUI is mode-aware and prompts differently for analyze vs apply-like modes.

## Installation

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux/macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you use OCR features, install optional OCR dependencies and system Tesseract.

## Quick Start (Recommended): GUI Mode

### Analyze (non-destructive)

```bash
python -m organizer analyze --gui
```

Prompts:

1. Select SOURCE folder (read-only scan in analyze mode).
2. Select OUTPUT folder for manifests/logs (or cancel to use `<source>_out`).

### Apply-like modes

```bash
python -m organizer apply-copy --gui
python -m organizer apply-move --gui
python -m organizer rename-in-place --gui --yes-i-understand
python -m organizer folder-rename-only --gui
```

Prompts:

1. Select TARGET folder (mode-dependent changes may occur).
2. Select OUTPUT/BACKUP folder (or cancel to use `<target>_out`).

## Configuration File (YAML)

Example:

```yaml
source_root: C:/data/messy_source
output_root: C:/data/messy_source_out
mode: analyze

# Optional overrides:
# manifest_dir: C:/data/messy_source_out/.organizer_manifests
# state_file: C:/data/messy_source_out/.organizer_manifests/state.json
# log_dir: C:/data/messy_source_out/.organizer_manifests
```

Run with config:

```bash
python -m organizer analyze --config sample_config.yaml
```

## CLI Overrides

You can override YAML values directly:

```bash
python -m organizer analyze \
  --source-root "C:/data/messy_source" \
  --output-root "C:/data/messy_source_out"
```

Supported path flags:

- `--source-root`
- `--output-root`
- `--manifest-dir`
- `--state-file`
- `--log-dir`

## Modes

| Mode | Source behavior | Output behavior |
| :-- | :-- | :-- |
| analyze | Read-only scan | Receives manifests/logs/state |
| apply-copy | Source unchanged; files copied by plan | Receives organized file tree + manifests/logs/state |
| apply-move | Files moved by plan | Receives organized file tree + manifests/logs/state |
| rename-in-place | Files renamed/moved in source tree | Receives manifests/logs/state |
| folder-rename-only | Folder renames in source tree | Receives manifests/logs/state |

## Safety Notes

- Dry-run is enabled by default.
- Use `--no-dry-run` for real writes.
- `rename-in-place` requires `--yes-i-understand`.
- Manifests/logs/state are always written under configured or derived config paths.

## Project Layout

- `organizer/__main__.py` CLI entrypoint and orchestration
- `organizer/config.py` YAML + override loading
- `organizer/models.py` config dataclass and path finalization
- `organizer/gui_select.py` folder dialog helper
- `organizer/scanner.py` file discovery
- `organizer/extractors.py` text extraction
- `organizer/classify.py` LLM classification
- `organizer/planner.py` deterministic action planning
- `organizer/executor.py` apply operations
- `organizer/manifest.py` output manifests
- `organizer/utils.py` helpers, logging, state I/O
