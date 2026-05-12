import random as _rnd

from PySide6.QtCore import QObject, QTimer, Signal

from settings import DEFAULT_SLIDESHOW_INTERVAL, DEFAULT_SLIDESHOW_LOOP


class SlideshowController(QObject):
    advance = Signal(int)
    started = Signal()
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._interval = DEFAULT_SLIDESHOW_INTERVAL
        self._loop = DEFAULT_SLIDESHOW_LOOP
        self._random = False
        self._current_index = 0
        self._file_count = 0
        self._running = False
        self._slides_shown = 0

    def set_files(self, count: int, current_index: int = 0) -> None:
        self._file_count = count
        self._current_index = current_index
        self._slides_shown = 0

    def set_interval(self, ms: int) -> None:
        self._interval = max(100, ms)
        if self._running:
            self._timer.setInterval(self._interval)

    def set_loop(self, loop: bool) -> None:
        self._loop = loop

    def set_random(self, random: bool) -> None:
        self._random = random

    def start(self) -> None:
        if self._file_count == 0:
            return
        self._slides_shown = 0
        # Sequential + no loop: if sitting at the last slide, wrap to beginning
        if not self._random and not self._loop and self._current_index >= self._file_count - 1:
            self._current_index = 0
            self.advance.emit(0)
        self._running = True
        self._timer.start(self._interval)
        self.started.emit()

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        self.stopped.emit()

    def toggle(self) -> None:
        if self._running:
            self.stop()
        else:
            self.start()

    def is_running(self) -> bool:
        return self._running

    def set_current_index(self, index: int) -> None:
        self._current_index = index

    def _on_timeout(self) -> None:
        if self._file_count == 0:
            self.stop()
            return

        if self._random:
            if self._file_count == 1:
                next_idx = 0
            else:
                next_idx = self._current_index
                while next_idx == self._current_index:
                    next_idx = _rnd.randrange(self._file_count)
            self._slides_shown += 1
            if not self._loop and self._slides_shown >= self._file_count:
                self._current_index = next_idx
                self.advance.emit(next_idx)
                self.stop()
                return
        else:
            next_idx = self._current_index + 1
            if next_idx >= self._file_count:
                if self._loop:
                    next_idx = 0
                else:
                    self.stop()
                    return

        self._current_index = next_idx
        self.advance.emit(self._current_index)

    def get_state(self) -> dict[str, object]:
        return {
            "interval": self._interval,
            "loop": self._loop,
            "random": self._random,
            "running": self._running,
        }

    def restore_state(self, state: dict[str, object]) -> None:
        self._interval = state.get("interval", DEFAULT_SLIDESHOW_INTERVAL)
        self._loop = state.get("loop", DEFAULT_SLIDESHOW_LOOP)
        self._random = state.get("random", False)
