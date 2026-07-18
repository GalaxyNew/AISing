import sys

from PySide6.QtWidgets import QApplication

from aising_client.branding import APP_ICON_PATH, APP_NAME
from aising_client.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    if APP_ICON_PATH.exists():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
