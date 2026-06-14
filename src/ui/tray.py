"""System tray icon — minimize to tray, quick actions."""
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import QSize, Qt


def _make_tray_icon() -> QIcon:
    """Generate a simple 'EV' icon programmatically."""
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    # Background circle
    p.setBrush(QColor("#1a6faf"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 30, 30)
    # Text
    p.setPen(QColor("#ffffff"))
    f = QFont("Arial", 10, QFont.Bold)
    p.setFont(f)
    p.drawText(px.rect(), Qt.AlignCenter, "EV")
    p.end()
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, main_window, parent=None):
        super().__init__(_make_tray_icon(), parent)
        self._win = main_window
        self.setToolTip("ElectroVision")
        self._build_menu()
        self.activated.connect(self._on_activated)
        self.show()

    def _build_menu(self) -> None:
        menu = QMenu()
        act_show = menu.addAction("Pokaż okno")
        act_show.triggered.connect(self._show_window)

        menu.addSeparator()

        act_pcb   = menu.addAction("📐 PCB 2D/3D")
        act_bom   = menu.addAction("📋 BOM")
        act_code  = menu.addAction("💻 Kod MCU")
        act_stl   = menu.addAction("📦 STL/STEP")
        act_pcb.triggered.connect(lambda: self._switch_tab(0))
        act_bom.triggered.connect(lambda: self._switch_tab(1))
        act_code.triggered.connect(lambda: self._switch_tab(2))
        act_stl.triggered.connect(lambda: self._switch_tab(3))

        menu.addSeparator()
        act_quit = menu.addAction("Wyjdź")
        act_quit.triggered.connect(QApplication.quit)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self) -> None:
        self._win.showNormal()
        self._win.activateWindow()
        self._win.raise_()

    def _switch_tab(self, index: int) -> None:
        self._show_window()
        tabs = self._win.findChild(type(self._win._tabs))
        if tabs:
            tabs.setCurrentIndex(index)
