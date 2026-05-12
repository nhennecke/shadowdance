"""Hideable panel showing the user's currently selected files.

Supports three view modes:
  Name      — plain filename list, drag/drop sortable
  Details   — filename + size + date, drag/drop sortable
  Thumbnails — icon grid with async-loaded thumbnails, drag/drop sortable
"""

from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

THUMB_SIZE = 120


# ---------------------------------------------------------------------------
# Async thumbnail loader
# ---------------------------------------------------------------------------

class _ThumbSignals(QObject):
    ready = Signal(str, QImage)


class _ThumbWorker(QRunnable):
    """Loads one thumbnail in the global thread pool; emits a QImage (thread-safe)."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _ThumbSignals()
        self.setAutoDelete(True)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._cancelled:
            return
        try:
            img = _load_thumb_qimage(self.path)
            if img and not img.isNull():
                self.signals.ready.emit(self.path, img)
        except Exception:
            pass


def _load_thumb_qimage(path: str) -> QImage | None:
    """Return a QImage scaled to THUMB_SIZE. Thread-safe (QImage, not QPixmap)."""
    # Qt native — respects EXIF orientation in Qt 6
    img = QImage(path)
    if not img.isNull():
        return img.scaled(
            THUMB_SIZE, THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    # Pillow fallback (HEIC, RAW, etc.)
    try:
        from PIL import Image, ImageOps
        pil = ImageOps.exif_transpose(Image.open(path))
        pil.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGBA" if "A" in pil.mode else "RGB")
        data = pil.tobytes("raw", pil.mode)
        fmt = (
            QImage.Format.Format_RGBA8888
            if pil.mode == "RGBA"
            else QImage.Format.Format_RGB888
        )
        # .copy() detaches from the bytes buffer so it's safe after `data` goes out of scope
        return QImage(data, pil.width, pil.height, fmt).copy()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Drag/drop-aware list widget
# ---------------------------------------------------------------------------

class _ReorderableListWidget(QListWidget):
    """QListWidget with a reliable custom dropEvent for both list and icon modes.

    Qt's built-in InternalMove in IconMode miscalculates the insert position
    because itemAt() returns None in the padding gaps between grid cells, causing
    every drop to fall through to "append at end".  This subclass finds the
    nearest item by distance to its visual rect instead, so drops in gaps are
    attributed to the logically closest slot.
    """

    rows_reordered = Signal()

    def dropEvent(self, event) -> None:
        if event.source() is not self:
            super().dropEvent(event)
            return

        dragged = self.selectedItems()
        if not dragged:
            event.ignore()
            return

        insert_row = self._drop_insert_index(event.position().toPoint())

        # Snapshot dragged item data before removing anything
        dragged_rows = sorted(self.row(i) for i in dragged)
        snap = []
        for row in dragged_rows:
            item = self.item(row)
            snap.append({
                "text": item.text(),
                "data": item.data(Qt.ItemDataRole.UserRole),
                "tooltip": item.toolTip(),
                "icon": item.icon(),
            })

        # Remove bottom-up to keep row indices stable
        for row in reversed(dragged_rows):
            self.takeItem(row)

        # Adjust insert position for the rows that were removed above it
        insert_row -= sum(1 for r in dragged_rows if r < insert_row)
        insert_row = max(0, min(insert_row, self.count()))

        for i, s in enumerate(snap):
            new_item = QListWidgetItem(s["text"])
            new_item.setData(Qt.ItemDataRole.UserRole, s["data"])
            new_item.setToolTip(s["tooltip"])
            if not s["icon"].isNull():
                new_item.setIcon(s["icon"])
            self.insertItem(insert_row + i, new_item)
            new_item.setSelected(True)

        event.accept()
        self.rows_reordered.emit()

    def _drop_insert_index(self, pt: QPoint) -> int:
        """Return the logical insert index for a drop at pixel position pt."""
        if self.count() == 0:
            return 0

        if self.viewMode() != QListView.ViewMode.IconMode:
            # List mode: itemAt() works reliably; split on top/bottom half.
            target = self.itemAt(pt)
            if target is None:
                return self.count()
            rect = self.visualItemRect(target)
            return self.row(target) + (1 if pt.y() > rect.center().y() else 0)

        # Icon/thumbnail mode: read actual item rects from Qt's layout engine so
        # that spacing and margins don't throw off the calculation.
        #
        # Strategy:
        #   1. Group items into grid rows by their top-y coordinate.
        #   2. Find which row contains pt.y (first row whose bottom >= pt.y).
        #   3. Within that row, insert before the first item whose center-x is
        #      to the right of pt.x; if pt.x is past all of them, append after
        #      the last item in the row (= start of next row in list order).
        rects = [self.visualItemRect(self.item(i)) for i in range(self.count())]

        row_map: dict[int, list[int]] = {}
        for i, r in enumerate(rects):
            row_map.setdefault(r.top(), []).append(i)

        sorted_tops = sorted(row_map)

        # Find the row that contains pt.y; fall back to the last row if below all.
        target_top = sorted_tops[-1]
        for top in sorted_tops:
            if pt.y() <= rects[row_map[top][0]].bottom():
                target_top = top
                break

        row_indices = sorted(row_map[target_top], key=lambda i: rects[i].left())

        for i in row_indices:
            if pt.x() < rects[i].center().x():
                return i

        return row_indices[-1] + 1


# ---------------------------------------------------------------------------
# The pane widget
# ---------------------------------------------------------------------------

class SelectionPane(QWidget):
    """Hideable dock panel for managing the selected/ordered file list."""

    file_activated = Signal(str)    # double-click → jump to file in viewer
    remove_requested = Signal(str)  # context-menu remove one file
    clear_requested = Signal()      # clear all
    order_changed = Signal(list)    # user reordered via drag/drop → new list[str]

    VIEW_NAME = "name"
    VIEW_DETAILS = "details"
    VIEW_THUMBNAILS = "thumbnails"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._view = self.VIEW_NAME
        self._thumb_cache: dict[str, QPixmap] = {}
        self._active_workers: list[_ThumbWorker] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = QToolBar()
        tb.setMovable(False)

        grp = QActionGroup(self)
        grp.setExclusive(True)

        for label, mode in (
            ("Name", self.VIEW_NAME),
            ("Details", self.VIEW_DETAILS),
            ("Thumbnails", self.VIEW_THUMBNAILS),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(mode == self.VIEW_NAME)
            act.triggered.connect(lambda checked, m=mode: self._set_view(m))
            grp.addAction(act)
            tb.addAction(act)

        tb.addSeparator()
        clear_act = QAction("Clear All", self)
        clear_act.triggered.connect(self.clear_requested)
        tb.addAction(clear_act)

        layout.addWidget(tb)

        self._list = _ReorderableListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Pixel-level scrolling so the wheel doesn't jump a full item height
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Drag/drop internal reordering (custom handler in _ReorderableListWidget)
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.rows_reordered.connect(self._on_rows_moved)

        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        self._count_label = QLabel("0 selected")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._count_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_files(self, files: list[str] | set[str]) -> None:
        """Replace the displayed file list (preserving thumb cache)."""
        self._files = list(files)  # caller sends already-ordered list
        self._cancel_pending_workers()
        self._refresh()

    # ------------------------------------------------------------------
    # View mode
    # ------------------------------------------------------------------

    def _set_view(self, mode: str) -> None:
        self._cancel_pending_workers()
        self._view = mode
        if mode == self.VIEW_THUMBNAILS:
            self._list.setViewMode(QListView.ViewMode.IconMode)
            self._list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
            self._list.setGridSize(QSize(THUMB_SIZE + 24, THUMB_SIZE + 36))
            self._list.setWordWrap(True)
            self._list.setSpacing(4)
        else:
            self._list.setViewMode(QListView.ViewMode.ListMode)
            self._list.setIconSize(QSize(16, 16))
            self._list.setGridSize(QSize())
            self._list.setSpacing(3 if mode == self.VIEW_DETAILS else 0)
        self._refresh()
        if mode == self.VIEW_THUMBNAILS:
            self._start_thumb_loading()

    # ------------------------------------------------------------------
    # List population
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._list.clear()
        for path in self._files:
            p = Path(path)
            if self._view == self.VIEW_DETAILS:
                try:
                    st = p.stat()
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    text = f"{p.name}\n  {_fmt_size(st.st_size)}  ·  {mtime}"
                except OSError:
                    text = p.name
            else:
                text = p.name

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)

            if self._view == self.VIEW_THUMBNAILS and path in self._thumb_cache:
                item.setIcon(QIcon(self._thumb_cache[path]))

            self._list.addItem(item)

        n = len(self._files)
        self._count_label.setText(f"{n} selected")

    # ------------------------------------------------------------------
    # Async thumbnail loading
    # ------------------------------------------------------------------

    def _start_thumb_loading(self) -> None:
        pool = QThreadPool.globalInstance()
        for path in self._files:
            if path in self._thumb_cache:
                self._apply_cached_thumb(path)
            else:
                worker = _ThumbWorker(path)
                worker.signals.ready.connect(self._on_thumb_ready)
                self._active_workers.append(worker)
                pool.start(worker)

    def _on_thumb_ready(self, path: str, img: QImage) -> None:
        px = QPixmap.fromImage(img)
        self._thumb_cache[path] = px
        self._apply_cached_thumb(path)

    def _apply_cached_thumb(self, path: str) -> None:
        if self._view != self.VIEW_THUMBNAILS or path not in self._thumb_cache:
            return
        px = self._thumb_cache[path]
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(QIcon(px))
                break

    def _cancel_pending_workers(self) -> None:
        for w in self._active_workers:
            w.cancel()
        self._active_workers.clear()

    # ------------------------------------------------------------------
    # Drag/drop reorder
    # ------------------------------------------------------------------

    def _on_rows_moved(self) -> None:
        new_order = [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]
        self._files = new_order
        self.order_changed.emit(new_order)
        # Qt's InternalMove cleanup fires after dropEvent returns and removes the
        # item at the original source row — by that point our takeItem/insertItem
        # has shifted everything, so it deletes the wrong item.  Deferring the
        # refresh via singleShot(0) means it runs after that cleanup and rebuilds
        # from the already-correct self._files, fixing all three view modes.
        QTimer.singleShot(0, self._refresh)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.file_activated.emit(path)

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        menu = QMenu(self)
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            act = menu.addAction(f'Remove "{Path(path).name}" from selection')
            act.triggered.connect(lambda: self.remove_requested.emit(path))
            menu.addSeparator()
        menu.addAction("Clear all selected files").triggered.connect(self.clear_requested)
        menu.exec(self._list.viewport().mapToGlobal(pos))
