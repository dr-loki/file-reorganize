from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any


@dataclass(slots=True)
class DependencyIssue:
    package: str
    install_hint: str


def _tkinter_hint() -> str:
    return (
        "Install Tk support for your Python build. "
        "Windows/macOS usually bundle it. Linux examples: Ubuntu/Debian `sudo apt install python3-tk`, "
        "Fedora `sudo dnf install python3-tkinter`, Arch: ensure Python was built with Tk support."
    )


def get_dependency_issues(gui_requested: bool = False, ocr_enabled: bool = False) -> list[DependencyIssue]:
    checks: list[tuple[str, str, str]] = [
        ("yaml", "pyyaml", "pip install pyyaml"),
        ("requests", "requests", "pip install requests"),
        ("fitz", "pymupdf", "pip install pymupdf"),
        ("docx", "python-docx", "pip install python-docx"),
        ("rich", "rich", "pip install rich"),
    ]

    issues: list[DependencyIssue] = []
    for module_name, package_name, hint in checks:
        try:
            import_module(module_name)
        except Exception:
            issues.append(DependencyIssue(package_name, hint))

    if ocr_enabled:
        for module_name, package_name, hint in [
            ("PIL", "pillow", "pip install pillow"),
            ("pytesseract", "pytesseract", "pip install pytesseract"),
        ]:
            try:
                import_module(module_name)
            except Exception:
                issues.append(DependencyIssue(package_name, hint))

    if gui_requested:
        try:
            import_module("tkinter")
        except Exception:
            issues.append(DependencyIssue("tkinter", _tkinter_hint()))

    return issues


def check_runtime_dependencies(gui_requested: bool = False, ocr_enabled: bool = False) -> None:
    issues = get_dependency_issues(gui_requested=gui_requested, ocr_enabled=ocr_enabled)
    if not issues:
        return

    lines = ["Missing required dependencies:"]
    for issue in issues:
        lines.append(f"- {issue.package}: {issue.install_hint}")
    raise RuntimeError("\n".join(lines))


def run_doctor(gui_requested: bool = True, ocr_enabled: bool = False, ollama_url: str | None = None) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    issues = get_dependency_issues(gui_requested=gui_requested, ocr_enabled=ocr_enabled)
    issue_by_package = {issue.package: issue.install_hint for issue in issues}

    for package in ["pyyaml", "requests", "pymupdf", "python-docx", "rich"]:
        hint = issue_by_package.get(package)
        results.append((package, hint is None, "ok" if hint is None else hint))

    if gui_requested:
        hint = issue_by_package.get("tkinter")
        results.append(("tkinter", hint is None, "ok" if hint is None else hint))

    if ocr_enabled:
        for package in ["pillow", "pytesseract"]:
            hint = issue_by_package.get(package)
            results.append((package, hint is None, "ok" if hint is None else hint))

    if ollama_url:
        try:
            requests_module: Any = import_module("requests")
            response = requests_module.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=5)
            response.raise_for_status()
            results.append(("ollama", True, f"reachable at {ollama_url}"))
        except Exception as exc:
            results.append(("ollama", False, f"unreachable: {exc}"))

    return results
