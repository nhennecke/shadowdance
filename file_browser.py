from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QLabel,
    QListView,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from settings import SUPPORTED_EXTENSIONS


class _MarkingDelegate(QStyledItemDelegate):
    """Paints a green highlight and checkmark badge on selected files."""

    _TINT = QColor(60, 180, 80, 55)
    _BADGE_BG = QColor(45, 160, 65)
    _BADGE_FG = QColor(255, 255, 255)
    _BADGE_TEXT = "✓"
    _BADGE_PAD = 3

    def __init__(self, model: QFileSystemModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._selected: set[str] = set()

    def update_selected(self, selected: set[str]) -> None:
        self._selected = selected

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        path = self._model.filePath(index)
        selected = path in self._selected

        if selected:
            painter.save()
            painter.fillRect(option.rect, self._TINT)
            painter.restore()

        super().paint(painter, option, index)

        if selected:
            painter.save()
            font = QFont(painter.font())
            font.setPointSize(max(7, font.pointSize() - 2))
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            badge_w = fm.horizontalAdvance(self._BADGE_TEXT) + self._BADGE_PAD * 2
            badge_h = fm.height() + self._BADGE_PAD
            r = option.rect
            badge = QRect(r.right() - badge_w - 2, r.top() + (r.height() - badge_h) // 2, badge_w, badge_h)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(self._BADGE_BG)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge, 3, 3)
            painter.setPen(self._BADGE_FG)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, self._BADGE_TEXT)
            painter.restore()


class FileBrowser(QWidget):
    file_selected = Signal(str)
    files_changed = Signal(list)
    selected_files_changed = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_files: set[str] = set()
        self._current_dir = str(Path.home())
        self._show_hidden = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Directory tree
        self._dir_model = QFileSystemModel()
        self._dir_model.setRootPath(QDir.rootPath())
        self._dir_model.setFilter(
            QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot
        )

        self._dir_tree = QTreeView()
        self._dir_tree.setModel(self._dir_model)
        self._dir_tree.setRootIndex(self._dir_model.index(QDir.rootPath()))
        for col in (1, 2, 3):
            self._dir_tree.setColumnHidden(col, True)
        self._dir_tree.setHeaderHidden(True)
        self._dir_tree.setMinimumHeight(120)
        self._dir_tree.clicked.connect(self._on_dir_clicked)

        # File list
        self._file_model = QFileSystemModel()
        self._file_model.setFilter(
            QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        name_filters = [f"*{ext}" for ext in SUPPORTED_EXTENSIONS]
        self._file_model.setNameFilters(name_filters)
        self._file_model.setNameFilterDisables(False)

        self._marking_delegate = _MarkingDelegate(self._file_model)

        self._file_list = QListView()
        self._file_list.setModel(self._file_model)
        self._file_list.setItemDelegate(self._marking_delegate)
        self._file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._file_list.clicked.connect(self._on_file_clicked)
        self._file_list.doubleClicked.connect(self._on_file_double_clicked)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._dir_tree)
        splitter.addWidget(self._file_list)
        splitter.setSizes([200, 300])

        self._mark_label = QLabel("0 selected")
        self._mark_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(splitter)
        layout.addWidget(self._mark_label)

        self._navigate_to(self._current_dir)

    def _navigate_to(self, path: str) -> None:
        self._current_dir = path
        idx = self._dir_model.index(path)
        self._dir_tree.setCurrentIndex(idx)
        self._dir_tree.scrollTo(idx)
        self._file_model.setRootPath(path)
        self._file_list.setRootIndex(self._file_model.index(path))
        self._file_list.scrollToTop()
        self._file_list.viewport().update()
        self._emit_files_changed()

    def _on_dir_clicked(self, index: QModelIndex) -> None:
        self._navigate_to(self._dir_model.filePath(index))

    def _on_file_clicked(self, index: QModelIndex) -> None:
        self.file_selected.emit(self._file_model.filePath(index))

    def _on_file_double_clicked(self, index: QModelIndex) -> None:
        path = self._file_model.filePath(index)
        if path in self._selected_files:
            self._selected_files.discard(path)
        else:
            self._selected_files.add(path)
        self._update_mark_label()
        self.selected_files_changed.emit(self._selected_files.copy())

    def _emit_files_changed(self) -> None:
        p = Path(self._current_dir)
        try:
            files = sorted(
                str(f)
                for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        except PermissionError:
            files = []
        self.files_changed.emit(files)

    def _update_mark_label(self) -> None:
        n = len(self._selected_files)
        self._mark_label.setText(f"{n} selected")
        self._marking_delegate.update_selected(self._selected_files)
        self._file_list.viewport().update()

    # Public API
    def navigate_to(self, path: str) -> None:
        self._navigate_to(path)

    def get_current_directory(self) -> str:
        return self._current_dir

    def get_current_files(self) -> list[str]:
        p = Path(self._current_dir)
        try:
            return sorted(
                str(f)
                for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        except PermissionError:
            return []

    def get_selected_files(self) -> set[str]:
        return self._selected_files.copy()

    def set_marks(self, paths: set[str]) -> None:
        self._selected_files = set(paths)
        self._update_mark_label()
        self.selected_files_changed.emit(self._selected_files.copy())

    def remove_mark(self, path: str) -> None:
        if path in self._selected_files:
            self._selected_files.discard(path)
            self._update_mark_label()
            self.selected_files_changed.emit(self._selected_files.copy())

    def clear_marks(self) -> None:
        if self._selected_files:
            self._selected_files.clear()
            self._update_mark_label()
            self.selected_files_changed.emit(self._selected_files.copy())

    def set_show_hidden(self, show: bool) -> None:
        self._show_hidden = show
        base_dir = QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot
        base_file = QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        if show:
            base_dir |= QDir.Filter.Hidden
            base_file |= QDir.Filter.Hidden
        self._dir_model.setFilter(base_dir)
        self._file_model.setFilter(base_file)
        self._emit_files_changed()

    def get_state(self) -> dict[str, object]:
        return {
            "directory": self._current_dir,
            "selected_files": list(self._selected_files),
        }

    def restore_state(self, state: dict[str, object]) -> None:
        if "directory" in state:
            self._navigate_to(state["directory"])
        if "selected_files" in state:
            self._selected_files = set(state["selected_files"])
            self._update_mark_label()  # also refreshes delegate
