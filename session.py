"""Session persistence — two separate concerns:

  Window sessions  — auto-saved window geometry / UI state to the platform-appropriate
                     app data directory (via QStandardPaths). No file paths or personal
                     content — safe to auto-save.

  Slideshow files  — explicit user-managed .sdshow files opened/saved via file dialog.
                     Contains the file list + playback settings the user curated.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from settings import SLIDESHOW_EXTENSION

_SESSION_EXT = ".json"


def _session_dir() -> Path:
    """Return the platform-correct app-data directory for window sessions.

    Computed lazily so QApplication is guaranteed to exist (and have its name
    set) before QStandardPaths is called.
      Linux   → ~/.local/share/shadowdance/windows
      macOS   → ~/Library/Application Support/shadowdance/windows
      Windows → %APPDATA%/shadowdance/windows
    """
    from PySide6.QtCore import QCoreApplication, QStandardPaths
    # GenericDataLocation avoids the org/app double-nesting that AppDataLocation
    # produces when OrganizationName == ApplicationName.
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    app = QCoreApplication.applicationName() or "shadowdance"
    return Path(base) / app / "windows"


# ---------------------------------------------------------------------------
# Window session helpers (auto-saved, geometry only)
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    return str(uuid.uuid4())[:8]


def _session_path(session_id: str) -> Path:
    return _session_dir() / f"win_{session_id}{_SESSION_EXT}"


def save_window_session(session_id: str, data: dict) -> None:
    """Persist window geometry and UI state only — no file paths."""
    d = _session_dir()
    d.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = datetime.now().isoformat()
    _session_path(session_id).write_text(json.dumps(data, indent=2))


def load_window_session(session_id: str) -> dict | None:
    p = _session_path(session_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def delete_window_session(session_id: str) -> None:
    p = _session_path(session_id)
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------------------
# Slideshow file helpers (explicit open/save, user-managed paths)
# ---------------------------------------------------------------------------

def save_slideshow(path: str, data: dict) -> None:
    """Write a slideshow file to a user-chosen path."""
    out = Path(path)
    if out.suffix.lower() != SLIDESHOW_EXTENSION:
        out = out.with_suffix(SLIDESHOW_EXTENSION)
    out.write_text(json.dumps(data, indent=2))


def load_slideshow(path: str) -> dict:
    """Load a slideshow file; raises OSError / ValueError on failure."""
    return json.loads(Path(path).read_text())
