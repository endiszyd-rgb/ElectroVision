import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from src.ui.main_window import MainWindow


def _apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    dark = QColor(30, 30, 30)
    mid = QColor(45, 45, 45)
    light = QColor(60, 60, 60)
    text = QColor(220, 220, 220)
    highlight = QColor(0, 122, 204)
    palette.setColor(QPalette.Window, dark)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, mid)
    palette.setColor(QPalette.AlternateBase, light)
    palette.setColor(QPalette.ToolTipBase, dark)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, mid)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ElectroVision")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("ElectroVision")
    _apply_dark_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
