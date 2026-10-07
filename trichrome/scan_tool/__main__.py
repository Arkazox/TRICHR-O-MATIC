"""Standalone entry point for testing the scan tool on its own, outside the
main app: ``python3 -m trichrome.scan_tool``."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .scan_window import ScanToolWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Trichr-o-matic Scan Tool (standalone test)")
    window = ScanToolWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
