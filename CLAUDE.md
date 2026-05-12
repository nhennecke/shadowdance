# ShadowDance — Development Guidelines

## Stack

- Python 3.13+, PySide6 6.x, Pillow (optional), rawpy (optional), pillow-heif (optional)
- One file per logical component; no circular imports (use lazy imports where needed)

---

## Code style

- Use modern Python type syntax: `X | Y`, `list[str]`, `dict[str, T]`, `Path` throughout
- **Type-annotate everything** — all parameters, return values, and instance variables
- Use `dict[str, object]` for JSON-like data bags rather than bare `dict`
- No bare container types: write `list[str]` not `list`, `set[str]` not `set`
- No comments that explain *what* the code does — names do that
- Only comment *why*: a non-obvious constraint, a Qt quirk, a workaround for a specific bug

---

## Encapsulation

- **Never access `_private` attributes of another class instance**
  - Wrong: `self._slideshow._loop`
  - Right: `self._slideshow.get_state()["loop"]`
- Add a getter or use the existing public API; Qt signals are public, `_` attributes are not

---

## Qt-specific

### Event handler signatures
Always use the correct Qt event type — omitting it hides type errors:
```python
def closeEvent(self, event: QCloseEvent) -> None: ...
def keyPressEvent(self, event: QKeyEvent) -> None: ...
def resizeEvent(self, event: QResizeEvent) -> None: ...
def dropEvent(self, event: QDropEvent) -> None: ...
```

### Thread safety
- `QImage` — safe to create in worker threads
- `QPixmap` — **main thread only**; always convert `QImage → QPixmap` on the main thread via signal

### QStandardPaths
Must be called lazily (after `QApplication` exists). Use `GenericDataLocation` to avoid the org/app double-nesting that `AppDataLocation` produces when org name equals app name.

### No hardcoded paths
All user data directories go through `QStandardPaths`. Nothing writes into the project directory at runtime.

---

## File and path handling

- Use `pathlib.Path` throughout; convert to `str` only at Qt API or I/O boundaries that require it
- Always open PIL images with a context manager so file handles are released immediately:
  ```python
  with Image.open(path) as img:
      img.load()          # force pixel data into memory before file closes
      result = img.rotate(90, expand=True)
  result.save(out)        # file is already closed; result has its own data
  ```

---

## Optional dependencies

PIL, rawpy, and pillow-heif are optional — import them **lazily** (inside the function that uses them):
```python
def load_raw(path):
    import rawpy          # not at module level
    ...
```
This keeps the app startable even when a dependency is not installed.

---

## Error handling

- Catch exceptions only at system boundaries: file I/O, PIL/rawpy calls, Qt file dialogs
- Show `QMessageBox.warning()` for user-visible failures; write to `sys.stderr` for internal ones
- Never swallow exceptions silently outside thread workers (`except Exception: pass` in workers only)

---

## Personal data and git

- Session/window geometry writes to `QStandardPaths.GenericDataLocation` — never the repo directory
- `.sdshow` files are user-managed content — never auto-save or auto-load them on startup
- `.gitignore` excludes `.venv/`, `__pycache__/`, `*.sdshow`, and session state directories

---

## Features tracking

`FEATURES.md` in the project root is the QA checklist. Update it whenever a feature is added, changed, or removed.
