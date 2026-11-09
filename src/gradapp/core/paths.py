"""Where GradApp keeps its data. Pure stdlib, no imports from the rest of the package."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def platform_data_dir() -> Path:
    """Per-user app folder: %APPDATA%\\GradApp, ~/Library/Application Support/GradApp, ~/.local/share/gradapp."""
    home = Path.home()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "GradApp"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "GradApp"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "gradapp"


def apply_default_data_dir() -> Path | None:
    """For the desktop app and the standalone binaries, whose working folder is arbitrary (a double-clicked
    .app starts in "/"). Does nothing when GRADAPP_DATA is set. An existing ./data folder from an older
    version keeps being used so nobody's data seems to vanish. Must run before gradapp.core.storage is imported."""
    if os.environ.get("GRADAPP_DATA"):
        return None
    legacy = Path.cwd() / "data"
    if (legacy / "users").is_dir() or (legacy / "config.json").is_file():
        return None
    d = platform_data_dir()
    os.environ["GRADAPP_DATA"] = str(d)
    return d
