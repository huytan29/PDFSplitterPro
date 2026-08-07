import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def resource_path(relative_path):
    """Lay duong dan tai nguyen khi chay tu ma nguon hoac ban PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def main():
    app = QApplication(sys.argv)

    app.setApplicationName("PDF Splitter Pro")

    app.setWindowIcon(QIcon(resource_path("resources/pdf_lightning_logo.png")))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
