#!/usr/bin/env python3
"""Entry point for Royal Kludge M87 Studio GUI Application."""

import os
import signal
import sys
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon

from gui.main_window import MainWindow


def main():
    # Allow clean exit with Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("RK M87 Studio")
    app.setQuitOnLastWindowClosed(False)

    icon_path = os.path.join(os.path.dirname(__file__), "data", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()

    start_minimized = ("--tray" in sys.argv or "--minimized" in sys.argv or "-m" in sys.argv)
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()

    # If requested to start in tray AND system tray is supported by the desktop environment:
    # Keep window hidden initially (accessible via tray). Otherwise show the window.
    if not (start_minimized and tray_available):
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
