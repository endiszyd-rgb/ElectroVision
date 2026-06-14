"""OllamaErrorDialog — user-friendly dialog shown when Ollama is unavailable."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from src.ai.ollama_utils import try_start_ollama, is_ollama_running, friendly_error


class OllamaErrorDialog(QDialog):
    """Shows when Ollama is not reachable. Offers instructions + Start button."""

    def __init__(self, raw_error: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠  AI niedostępne — Ollama")
        self.setMinimumWidth(540)
        self.setMaximumWidth(620)
        self._build_ui(raw_error)

    def _build_ui(self, raw_error: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Icon + title
        title = QLabel("⚠  Nie można połączyć z Ollama")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #f0a050; "
            "background: #1a1000; padding: 10px 14px; border-radius: 4px;"
        )
        layout.addWidget(title)

        # Main explanation
        msg_text = friendly_error(raw_error)
        msg = QTextEdit()
        msg.setReadOnly(True)
        msg.setPlainText(msg_text)
        msg.setFont(QFont("Consolas", 9))
        msg.setStyleSheet(
            "background: #0d1117; color: #c0c0c0; "
            "border: 1px solid #2a2a3a; padding: 6px;"
        )
        msg.setFixedHeight(160)
        layout.addWidget(msg)

        # Progress bar (hidden, shown during start)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumHeight(5)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet("color: #78dcaa; font-size: 9px; font-family: Consolas;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()

        self._btn_start = QPushButton("▶  Uruchom Ollama (ollama serve)")
        self._btn_start.setStyleSheet(
            "QPushButton { background: #1a4a1a; color: white; "
            "padding: 7px 16px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background: #2a6a2a; }"
        )
        self._btn_start.clicked.connect(self._start_ollama)
        btn_row.addWidget(self._btn_start)

        self._btn_retry = QPushButton("🔄  Sprawdź ponownie")
        self._btn_retry.clicked.connect(self._check_again)
        btn_row.addWidget(self._btn_retry)

        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

        link = QLabel(
            '<a href="https://ollama.ai" style="color:#4a90d9;">Pobierz Ollama: https://ollama.ai</a>'
        )
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        layout.addWidget(link)

    def _start_ollama(self) -> None:
        self._btn_start.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Uruchamianie Ollama…")

        ok, msg = try_start_ollama()
        if ok:
            self._status.setText(f"✓  {msg}")
            # After 4s check if it's really up
            QTimer.singleShot(4000, self._check_after_start)
        else:
            self._status.setText(f"✗  {msg}")
            self._progress.setVisible(False)
            self._btn_start.setEnabled(True)

    def _check_after_start(self) -> None:
        self._progress.setVisible(False)
        if is_ollama_running():
            self._status.setText("✓  Ollama działa! Możesz zamknąć okno i spróbować ponownie.")
            self._btn_start.setEnabled(False)
        else:
            self._status.setText("⚠  Ollama nadal niedostępna. Uruchom ją ręcznie: ollama serve")
            self._btn_start.setEnabled(True)

    def _check_again(self) -> None:
        if is_ollama_running():
            self._status.setText("✓  Ollama działa!")
        else:
            self._status.setText("✗  Ollama nadal niedostępna.")


def show_ollama_error(raw_error: str = "", parent=None) -> None:
    """Convenience function — show OllamaErrorDialog and block."""
    dlg = OllamaErrorDialog(raw_error, parent)
    dlg.exec()
