"""ShadowDance — multi-instance photo viewer and slideshow manager."""

import sys

from PySide6.QtWidgets import QApplication

from settings import APP_NAME

_CASCADE_OFFSET = 30


class ShadowDanceApp:
    def __init__(self, argv: list[str]):
        self._qapp = QApplication(argv)
        self._qapp.setApplicationName(APP_NAME)
        self._qapp.setOrganizationName("shadowdance")
        self._qapp.setQuitOnLastWindowClosed(True)
        self._windows: dict[str, object] = {}
        self._next_cascade = 0

    def open_new_window(self, session_id: str | None = None):
        from viewer_window import ViewerWindow

        win = ViewerWindow(session_id=session_id)
        win.window_closed.connect(self._on_window_closed)
        win.request_new_window.connect(self.open_new_window)
        self._windows[win.session_id] = win

        offset = _CASCADE_OFFSET * self._next_cascade
        self._next_cascade = (self._next_cascade + 1) % 10
        pos = win.pos()
        win.move(pos.x() + offset, pos.y() + offset)

        win.show()
        return win

    def _on_window_closed(self, session_id: str) -> None:
        self._windows.pop(session_id, None)

    def run(self) -> int:
        self.open_new_window()
        return self._qapp.exec()


def main() -> None:
    app = ShadowDanceApp(sys.argv)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
