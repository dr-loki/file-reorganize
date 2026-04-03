from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog


def select_directory(title: str, initialdir: str | None = None) -> Path | None:
    """Open a folder picker and return the chosen directory, or None on cancel."""
    root = tk.Tk()
    root.withdraw()

    options: dict[str, str] = {"title": title}
    if initialdir is not None:
        options["initialdir"] = initialdir

    selected = filedialog.askdirectory(**options)
    root.destroy()

    if not selected:
        return None
    return Path(selected)
