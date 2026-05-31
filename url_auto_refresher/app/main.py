from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui_main import MainWindow
from utils import ensure_app_dirs


def main() -> int:
    ensure_app_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("URL Auto Refresher")
    app.setOrganizationName("Authorized Test Tools")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
