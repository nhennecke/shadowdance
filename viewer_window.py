import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QImage, QKeyEvent, QKeySequence, QMouseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QToolBar,
    QVBoxLayout,
)

import editor
import session as session_mod
from file_browser import FileBrowser
from selection_pane import SelectionPane
from settings import (
    APP_NAME,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_X,
    DEFAULT_WINDOW_Y,
    HEIC_EXTENSIONS,
    RAW_EXTENSIONS,
    SLIDESHOW_EXTENSION,
    SUPPORTED_EXTENSIONS,
)
from slideshow import SlideshowController


def load_image_to_pixmap(path: str) -> QPixmap | None:
    """Load an image to QPixmap.

    Strategy:
      RAW  → rawpy (handles orientation internally)
      HEIC → pillow-heif → PIL → QPixmap
      All other formats → QPixmap.load() (Qt native, same engine as Gwenview,
                          respects EXIF orientation automatically in Qt 6)
                          → PIL fallback if Qt returns a null pixmap
    """
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext in RAW_EXTENSIONS:
            import rawpy
            from PIL import Image
            with rawpy.imread(path) as raw:
                rgb = raw.postprocess()
            return _pil_to_pixmap(Image.fromarray(rgb))

        if ext in HEIC_EXTENSIONS:
            from PIL import Image, ImageOps
            from pillow_heif import register_heif_opener
            register_heif_opener()
            with Image.open(path) as pil_img:
                pil_img.load()
                img = ImageOps.exif_transpose(pil_img)
            return _pil_to_pixmap(img)

        # Qt native path — fastest, highest quality, auto EXIF rotation
        px = QPixmap(path)
        if not px.isNull():
            return px

        # Pillow fallback for any format Qt couldn't handle (e.g. AVIF without plugin)
        from PIL import Image, ImageOps
        with Image.open(path) as pil_img:
            pil_img.load()
            img = ImageOps.exif_transpose(pil_img)
        return _pil_to_pixmap(img)

    except Exception as exc:
        print(f"Failed to load {path}: {exc}", file=sys.stderr)
        return None


def _pil_to_pixmap(img: object) -> QPixmap:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")
    data = img.tobytes("raw", img.mode)
    fmt = (
        QImage.Format.Format_RGBA8888
        if img.mode == "RGBA"
        else QImage.Format.Format_RGB888
    )
    qimg = QImage(data, img.width, img.height, fmt)
    return QPixmap.fromImage(qimg)


class ImageDisplay(QScrollArea):
    mouse_clicked = Signal(Qt.MouseButton)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWidget(self._label)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a;")
        self._pixmap: QPixmap | None = None
        self._fit = True
        self._zoom = 1.0

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self._update_display()

    def set_fit(self, fit: bool) -> None:
        self._fit = fit
        self._update_display()

    def set_zoom(self, factor: float) -> None:
        self._zoom = max(0.05, min(factor, 20.0))
        self._fit = False
        self._update_display()

    def _update_display(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            self._label.clear()
            self._label.setText("No image")
            return
        if self._fit:
            scaled = self._pixmap.scaled(
                self.viewport().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            w = int(self._pixmap.width() * self._zoom)
            h = int(self._pixmap.height() * self._zoom)
            scaled = self._pixmap.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._label.setPixmap(scaled)

    # Keys the scroll area would normally consume for scrolling — pass them
    # through to the parent window so fullscreen navigation always works.
    _PASSTHROUGH_KEYS: frozenset[Qt.Key] = frozenset({
        Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
        Qt.Key.Key_Space, Qt.Key.Key_Escape, Qt.Key.Key_F11,
    })

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in self._PASSTHROUGH_KEYS:
            event.ignore()  # propagate to ViewerWindow
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.mouse_clicked.emit(event.button())
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._fit:
            self._update_display()


class ViewerWindow(QMainWindow):
    window_closed = Signal(str)
    request_new_window = Signal()

    def __init__(self, session_id: str | None = None):
        super().__init__()
        self._session_id = session_id or session_mod.new_session_id()
        self._files: list[str] = []       # effective list used by slideshow
        self._dir_files: list[str] = []   # current directory files (fallback when nothing marked)
        self._current_index: int = -1
        self._slideshow_path: str | None = None
        self._modified = False
        self._pre_fs_browser = False
        self._pre_fs_selection = False

        self._setup_ui()
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.move(DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y)
        self._update_title()

    @property
    def session_id(self) -> str:
        return self._session_id

    def _setup_ui(self) -> None:
        self._display = ImageDisplay(self)
        self.setCentralWidget(self._display)
        self._display.mouse_clicked.connect(self._on_image_clicked)

        self._browser = FileBrowser()
        self._browser_dock = QDockWidget("Files", self)
        self._browser_dock.setWidget(self._browser)
        self._browser_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._browser_dock)

        self._browser.file_selected.connect(self._on_file_selected)
        self._browser.files_changed.connect(self._on_files_changed)
        self._browser.selected_files_changed.connect(self._on_selected_files_changed)

        self._selection_pane = SelectionPane()
        self._selection_dock = QDockWidget("Selected Files", self)
        self._selection_dock.setWidget(self._selection_pane)
        self._selection_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._selection_dock)
        self._selection_dock.hide()

        self._selection_pane.file_activated.connect(self._on_file_selected)
        self._selection_pane.remove_requested.connect(self._browser.remove_mark)
        self._selection_pane.clear_requested.connect(self._browser.clear_marks)
        self._selection_pane.order_changed.connect(self._on_selection_order_changed)

        self._slideshow = SlideshowController(self)
        self._slideshow.advance.connect(self._show_index)
        self._slideshow.started.connect(self._on_slideshow_started)
        self._slideshow.stopped.connect(self._on_slideshow_stopped)

        self._setup_menu()
        self._setup_toolbar()
        self._status_label = QLabel("No image loaded")
        self.statusBar().addWidget(self._status_label)

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")

        a = QAction("&New Slideshow", self)
        a.triggered.connect(self._new_slideshow)
        file_menu.addAction(a)

        a = QAction("&Open Slideshow…", self)
        a.setShortcut(QKeySequence("Ctrl+O"))
        a.triggered.connect(self._open_slideshow)
        file_menu.addAction(a)

        self._act_save = QAction("&Save Slideshow", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self._save_slideshow)
        file_menu.addAction(self._act_save)

        a = QAction("Save Slideshow &As…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+S"))
        a.triggered.connect(self._save_slideshow_as)
        file_menu.addAction(a)

        file_menu.addSeparator()

        a = QAction("Browse &Directory…", self)
        a.setShortcut(QKeySequence("Ctrl+D"))
        a.triggered.connect(self._open_directory)
        file_menu.addAction(a)

        file_menu.addSeparator()

        a = QAction("&New Window", self)
        a.setShortcut(QKeySequence("Ctrl+N"))
        a.triggered.connect(self.request_new_window)
        file_menu.addAction(a)

        file_menu.addSeparator()

        a = QAction("&Close", self)
        a.setShortcut(QKeySequence("Ctrl+W"))
        a.triggered.connect(self.close)
        file_menu.addAction(a)

        # View
        view_menu = mb.addMenu("&View")

        self._act_fit = QAction("&Fit to Window", self)
        self._act_fit.setShortcut(QKeySequence("Ctrl+F"))
        self._act_fit.setCheckable(True)
        self._act_fit.setChecked(True)
        self._act_fit.triggered.connect(self._on_fit_toggled)
        view_menu.addAction(self._act_fit)

        self._act_fullscreen = QAction("F&ull Screen", self)
        self._act_fullscreen.setShortcut(QKeySequence("F11"))
        self._act_fullscreen.setCheckable(True)
        self._act_fullscreen.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self._act_fullscreen)

        view_menu.addSeparator()
        toggle_browser = self._browser_dock.toggleViewAction()
        toggle_browser.setText("&File Browser")
        toggle_browser.setShortcut(QKeySequence("Ctrl+B"))
        view_menu.addAction(toggle_browser)

        toggle_selection = self._selection_dock.toggleViewAction()
        toggle_selection.setText("&Selected Files")
        toggle_selection.setShortcut(QKeySequence("Ctrl+E"))
        view_menu.addAction(toggle_selection)

        view_menu.addSeparator()

        self._act_show_hidden = QAction("Show &Hidden Files", self)
        self._act_show_hidden.setCheckable(True)
        self._act_show_hidden.setChecked(False)
        self._act_show_hidden.setShortcut(QKeySequence("Ctrl+H"))
        self._act_show_hidden.toggled.connect(self._browser.set_show_hidden)
        view_menu.addAction(self._act_show_hidden)

        # Slideshow
        ss_menu = mb.addMenu("&Slideshow")

        self._act_play = QAction("&Play", self)
        self._act_play.setShortcut(QKeySequence("Space"))
        self._act_play.triggered.connect(self._slideshow.toggle)
        ss_menu.addAction(self._act_play)

        a = QAction("&Next", self)
        a.setShortcut(QKeySequence("Right"))
        a.triggered.connect(self._next_image)
        ss_menu.addAction(a)

        a = QAction("&Previous", self)
        a.setShortcut(QKeySequence("Left"))
        a.triggered.connect(self._prev_image)
        ss_menu.addAction(a)

        ss_menu.addSeparator()

        self._act_loop = QAction("&Loop", self)
        self._act_loop.setCheckable(True)
        self._act_loop.setChecked(True)
        self._act_loop.toggled.connect(self._slideshow.set_loop)
        ss_menu.addAction(self._act_loop)

        self._act_random = QAction("&Shuffle", self)
        self._act_random.setCheckable(True)
        self._act_random.setChecked(False)
        self._act_random.toggled.connect(self._slideshow.set_random)
        ss_menu.addAction(self._act_random)

        ss_menu.addSeparator()

        a = QAction("&Slide Duration…", self)
        a.triggered.connect(self._show_slideshow_settings)
        ss_menu.addAction(a)

        # Edit
        edit_menu = mb.addMenu("&Edit")

        a = QAction("&Crop…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+C"))
        a.triggered.connect(self._crop)
        edit_menu.addAction(a)

        edit_menu.addSeparator()

        a = QAction("Rotate &Clockwise", self)
        a.setShortcut(QKeySequence("Ctrl+R"))
        a.triggered.connect(lambda: self._rotate(90))
        edit_menu.addAction(a)

        a = QAction("Rotate C&ounter-Clockwise", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+R"))
        a.triggered.connect(lambda: self._rotate(-90))
        edit_menu.addAction(a)

        a = QAction("Flip &Horizontal", self)
        a.triggered.connect(lambda: self._flip(True))
        edit_menu.addAction(a)

        a = QAction("Flip &Vertical", self)
        a.triggered.connect(lambda: self._flip(False))
        edit_menu.addAction(a)

    def _setup_toolbar(self) -> None:
        tb = QToolBar("Navigation", self)
        tb.setObjectName("nav_toolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        sp = QStyle.StandardPixmap
        s = self.style()
        tb.addAction(s.standardIcon(sp.SP_MediaSkipBackward), "First", self._first_image)
        tb.addAction(s.standardIcon(sp.SP_MediaSeekBackward), "Previous", self._prev_image)
        self._tb_play = QAction(s.standardIcon(sp.SP_MediaPlay), "Play", self)
        self._tb_play.triggered.connect(self._slideshow.toggle)
        tb.addAction(self._tb_play)
        tb.addAction(s.standardIcon(sp.SP_MediaSeekForward), "Next", self._next_image)
        tb.addAction(s.standardIcon(sp.SP_MediaSkipForward), "Last", self._last_image)
        tb.addSeparator()
        tb.addAction("New Window", self.request_new_window)

    # -----------------------------------------------------------------------
    # Title management
    # -----------------------------------------------------------------------

    def _update_title(self) -> None:
        marker = " *" if self._modified else ""
        if self._slideshow_path:
            name = Path(self._slideshow_path).stem
            self.setWindowTitle(f"{APP_NAME} — {name}{marker}")
        else:
            self.setWindowTitle(f"{APP_NAME}{marker}")

    def _mark_modified(self) -> None:
        if not self._modified:
            self._modified = True
            self._update_title()

    # -----------------------------------------------------------------------
    # Slideshow file operations
    # -----------------------------------------------------------------------

    def _ask_save_if_modified(self) -> bool:
        """Return True if it's safe to proceed (saved or user chose to discard)."""
        if not self._modified or not self._files:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved Slideshow",
            "The current slideshow has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_slideshow()
        return True

    def _new_slideshow(self) -> None:
        if not self._ask_save_if_modified():
            return
        self._browser.clear_marks()
        self._files = []
        self._dir_files = []
        self._current_index = -1
        self._slideshow_path = None
        self._modified = False
        self._slideshow.set_files(0, 0)
        self._display.set_pixmap(None)
        self._status_label.setText("No image loaded")
        self._update_title()

    def _open_slideshow(self) -> None:
        if not self._ask_save_if_modified():
            return
        ext = f"*{SLIDESHOW_EXTENSION}"
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Slideshow", str(Path.home()), f"Slideshows ({ext});;All Files (*)"
        )
        if not path:
            return
        try:
            data = session_mod.load_slideshow(path)
        except Exception as exc:
            QMessageBox.warning(self, "Open Failed", str(exc))
            return
        self._apply_slideshow_data(data)
        self._slideshow_path = path
        self._modified = False
        self._update_title()

    def _save_slideshow(self) -> bool:
        """Save to current path; falls back to Save As. Returns True on success."""
        if not self._slideshow_path:
            return self._save_slideshow_as()
        try:
            session_mod.save_slideshow(self._slideshow_path, self._build_slideshow_data())
            self._modified = False
            self._update_title()
            self._status_label.setText("Slideshow saved.")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return False

    def _save_slideshow_as(self) -> bool:
        """Prompt for a path and save. Returns True on success."""
        ext = f"*{SLIDESHOW_EXTENSION}"
        default = str(Path(self._slideshow_path) if self._slideshow_path else Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Slideshow As", default, f"Slideshows ({ext});;All Files (*)"
        )
        if not path:
            return False
        if not path.endswith(SLIDESHOW_EXTENSION):
            path += SLIDESHOW_EXTENSION
        try:
            session_mod.save_slideshow(path, self._build_slideshow_data())
            self._slideshow_path = path
            self._modified = False
            self._update_title()
            self._status_label.setText("Slideshow saved.")
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return False

    def _build_slideshow_data(self) -> dict[str, object]:
        return {
            "files": self._files,
            "current_index": self._current_index,
            "slideshow": self._slideshow.get_state(),
            "browser_directory": self._browser.get_current_directory(),
        }

    def _apply_slideshow_data(self, data: dict[str, object]) -> None:
        files = data.get("files", [])
        idx = data.get("current_index", 0)

        self._slideshow.restore_state(data.get("slideshow", {}))
        ss_state = self._slideshow.get_state()
        self._act_loop.setChecked(ss_state["loop"])
        self._act_random.setChecked(ss_state["random"])

        # Restore selection — triggers _on_selected_files_changed → _sync_effective_files
        self._browser.set_marks(set(files))

        if "browser_directory" in data:
            self._browser.navigate_to(data["browser_directory"])

        if self._files and 0 <= idx < len(self._files):
            self._show_index(idx)
        else:
            self._status_label.setText("No image loaded")

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _show_index(self, index: int) -> None:
        if not self._files or not (0 <= index < len(self._files)):
            return
        self._current_index = index
        self._slideshow.set_current_index(index)
        path = self._files[index]
        pixmap = load_image_to_pixmap(path)
        self._display.set_pixmap(pixmap)
        name = Path(path).name
        self._status_label.setText(f"{name}  [{index + 1}/{len(self._files)}]")

    def _next_image(self) -> None:
        if self._files:
            self._show_index((self._current_index + 1) % len(self._files))

    def _prev_image(self) -> None:
        if self._files:
            self._show_index((self._current_index - 1) % len(self._files))

    def _first_image(self) -> None:
        if self._files:
            self._show_index(0)

    def _last_image(self) -> None:
        if self._files:
            self._show_index(len(self._files) - 1)

    # -----------------------------------------------------------------------
    # File loading / browser events
    # -----------------------------------------------------------------------

    def _open_directory(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Browse Directory", str(Path.home()))
        if d:
            self._browser.navigate_to(d)

    def _load_file(self, path: str) -> None:
        p = Path(path)
        try:
            siblings = sorted(
                str(f)
                for f in p.parent.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        except PermissionError:
            siblings = [path]
        self._dir_files = siblings
        self._sync_effective_files()
        # Navigate to the requested file within the effective list
        target = str(p)
        if target in self._files:
            idx = self._files.index(target)
            self._show_index(idx)
        self._mark_modified()

    def _on_file_selected(self, path: str) -> None:
        if path in self._files:
            # File is in the active slideshow list — update position and preview
            idx = self._files.index(path)
            self._current_index = idx
            self._slideshow.set_current_index(idx)
            self._show_index(idx)
        else:
            # Browsing a file outside the slideshow list — preview without disrupting it
            pixmap = load_image_to_pixmap(path)
            self._display.set_pixmap(pixmap)
            self._status_label.setText(Path(path).name)

    def _on_files_changed(self, files: list[str]) -> None:
        self._dir_files = files
        self._sync_effective_files()

    def _on_selected_files_changed(self, selected: set[str]) -> None:
        self._sync_effective_files()
        # Pass the already-ordered self._files so the pane reflects slideshow order
        self._selection_pane.update_files(self._files if selected else [])
        if selected and self._selection_dock.isHidden():
            self._selection_dock.show()
        self._mark_modified()

    def _on_selection_order_changed(self, new_order: list) -> None:
        """User drag/dropped items in the selection pane — update slideshow order."""
        current_path = (
            self._files[self._current_index]
            if 0 <= self._current_index < len(self._files)
            else None
        )
        self._files = new_order
        self._slideshow.set_files(len(new_order), 0)
        if current_path and current_path in new_order:
            idx = new_order.index(current_path)
            self._current_index = idx
            self._slideshow.set_current_index(idx)
        self._mark_modified()

    def _sync_effective_files(self) -> None:
        """Rebuild the active file list: selected files take priority over directory files.

        Preserves the existing user-defined order — new additions go at the end,
        deselected files are removed in place. This ensures drag/drop ordering
        in the selection pane survives subsequent mark/unmark operations.
        """
        selected = self._browser.get_selected_files()

        if selected:
            # Keep existing order; append any newly added files sorted at the end
            existing = [f for f in self._files if f in selected]
            new_additions = sorted(f for f in selected if f not in set(self._files))
            new_files = existing + new_additions
        else:
            new_files = self._dir_files

        current_path = (
            self._files[self._current_index]
            if 0 <= self._current_index < len(self._files)
            else None
        )

        self._files = new_files
        self._slideshow.set_files(len(new_files), 0)

        if not new_files:
            self._current_index = -1
            return

        if current_path and current_path in new_files:
            idx = new_files.index(current_path)
            self._current_index = idx
            self._slideshow.set_current_index(idx)
        else:
            self._show_index(0)

    # -----------------------------------------------------------------------
    # Slideshow playback
    # -----------------------------------------------------------------------

    def _on_slideshow_started(self) -> None:
        sp = QStyle.StandardPixmap
        self._tb_play.setIcon(self.style().standardIcon(sp.SP_MediaPause))
        self._tb_play.setText("Pause")
        self._act_play.setText("&Pause")

    def _on_slideshow_stopped(self) -> None:
        sp = QStyle.StandardPixmap
        self._tb_play.setIcon(self.style().standardIcon(sp.SP_MediaPlay))
        self._tb_play.setText("Play")
        self._act_play.setText("&Play")

    # -----------------------------------------------------------------------
    # View
    # -----------------------------------------------------------------------

    def _on_fit_toggled(self, checked: bool) -> None:
        self._display.set_fit(checked)

    def _toggle_fullscreen(self, checked: bool) -> None:
        if checked:
            self._pre_fs_browser = self._browser_dock.isVisible()
            self._pre_fs_selection = self._selection_dock.isVisible()
            self.menuBar().hide()
            self.statusBar().hide()
            for tb in self.findChildren(QToolBar):
                tb.hide()
            self._browser_dock.hide()
            self._selection_dock.hide()
            self.showFullScreen()
        else:
            self.showNormal()
            self.menuBar().show()
            self.statusBar().show()
            for tb in self.findChildren(QToolBar):
                tb.show()
            if self._pre_fs_browser:
                self._browser_dock.show()
            if self._pre_fs_selection:
                self._selection_dock.show()

    def _on_image_clicked(self, button: Qt.MouseButton) -> None:
        if not self.isFullScreen():
            return
        if button == Qt.MouseButton.LeftButton:
            self._next_image()
        elif button == Qt.MouseButton.RightButton:
            self._prev_image()

    # -----------------------------------------------------------------------
    # Edit
    # -----------------------------------------------------------------------

    def _rotate(self, degrees: int) -> None:
        if self._current_index < 0 or not self._files:
            return
        path = self._files[self._current_index]
        try:
            out = editor.rotate_image(path, degrees)
            self._display.set_pixmap(load_image_to_pixmap(out))
        except Exception as exc:
            QMessageBox.warning(self, "Rotate Failed", str(exc))

    def _flip(self, horizontal: bool) -> None:
        if self._current_index < 0 or not self._files:
            return
        path = self._files[self._current_index]
        try:
            out = editor.flip_image(path, horizontal)
            self._display.set_pixmap(load_image_to_pixmap(out))
        except Exception as exc:
            QMessageBox.warning(self, "Flip Failed", str(exc))

    def _crop(self) -> None:
        if self._current_index < 0 or not self._files:
            return
        path = self._files[self._current_index]
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.size
        except Exception as exc:
            QMessageBox.warning(self, "Crop Failed", str(exc))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Crop Image")
        outer = QVBoxLayout(dlg)

        grp = QGroupBox(f"Image size: {w} × {h} px")
        form = QFormLayout(grp)

        def _spin(lo, hi, val):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            return s

        left_s = _spin(0, w - 1, 0)
        top_s = _spin(0, h - 1, 0)
        right_s = _spin(1, w, w)
        bottom_s = _spin(1, h, h)
        form.addRow("Left:", left_s)
        form.addRow("Top:", top_s)
        form.addRow("Right:", right_s)
        form.addRow("Bottom:", bottom_s)

        overwrite_check = QCheckBox("Overwrite original (backs up to .orig)")
        outer.addWidget(grp)
        outer.addWidget(overwrite_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        left, top, right, bottom = left_s.value(), top_s.value(), right_s.value(), bottom_s.value()
        if left >= right or top >= bottom:
            QMessageBox.warning(self, "Crop Failed", "Invalid crop bounds.")
            return
        try:
            out = editor.crop_image(path, left, top, right, bottom, overwrite=overwrite_check.isChecked())
            if overwrite_check.isChecked():
                self._display.set_pixmap(load_image_to_pixmap(out))
            else:
                self._load_file(out)
        except Exception as exc:
            QMessageBox.warning(self, "Crop Failed", str(exc))

    # -----------------------------------------------------------------------
    # Slideshow settings
    # -----------------------------------------------------------------------

    def _show_slideshow_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Slide Duration")
        layout = QFormLayout(dlg)

        interval_spin = QSpinBox()
        interval_spin.setRange(200, 300_000)
        interval_spin.setSingleStep(500)
        interval_spin.setValue(self._slideshow.get_state()["interval"])
        interval_spin.setSuffix(" ms")
        layout.addRow("Duration per slide:", interval_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._slideshow.set_interval(interval_spin.value())
            self._mark_modified()

    # -----------------------------------------------------------------------
    # Qt event overrides
    # -----------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._ask_save_if_modified():
            event.ignore()
            return
        self.window_closed.emit(self._session_id)
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if self.isFullScreen():
            if key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                self._act_fullscreen.setChecked(False)
                self._toggle_fullscreen(False)
                return
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                self._next_image()
                return
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                self._prev_image()
                return
            if key == Qt.Key.Key_Space:
                self._slideshow.toggle()
                return
        super().keyPressEvent(event)
