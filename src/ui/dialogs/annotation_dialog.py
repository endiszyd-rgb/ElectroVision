"""Auto-Annotation Dialog — renumber PCB components sequentially."""
from __future__ import annotations
import re
from collections import defaultdict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QCheckBox, QSpinBox, QTextEdit, QFormLayout,
    QMessageBox, QWidget, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project
from src.core.models.component import Component


# ── Annotation engine ──────────────────────────────────────────────────────────

_PREFIX_MAP = {
    "ic":        "U",
    "resistor":  "R",
    "capacitor": "C",
    "inductor":  "L",
    "led":       "LED",
    "diode":     "D",
    "transistor":"Q",
    "crystal":   "X",
    "connector": "J",
    "switch":    "SW",
    "fuse":      "F",
    "generic":   "U",
}

_SORT_MODES = {
    "Lewo → prawo, góra → dół (X, Y)": lambda c: (c.x, c.y),
    "Góra → dół, lewo → prawo (Y, X)": lambda c: (c.y, c.x),
    "Według referencji (alfanumerycznie)": lambda c: c.reference,
    "Warstwa: najpierw F.Cu": lambda c: (0 if c.layer == "F.Cu" else 1, c.x, c.y),
}


def annotate(components: list[Component],
             sort_key,
             start_num: int = 1,
             step: int = 1,
             scope: str = "all") -> list[tuple[Component, str, str]]:
    """Return list of (comp, old_ref, new_ref) tuples."""
    # Group by type prefix
    by_prefix: dict[str, list[Component]] = defaultdict(list)
    for comp in sorted(components, key=sort_key):
        prefix = _PREFIX_MAP.get(comp.component_type, "U")
        by_prefix[prefix].append(comp)

    result: list[tuple[Component, str, str]] = []
    counters: dict[str, int] = {}

    for comp in sorted(components, key=sort_key):
        prefix = _PREFIX_MAP.get(comp.component_type, "U")
        num = counters.get(prefix, start_num)
        new_ref = f"{prefix}{num}"
        counters[prefix] = num + step
        result.append((comp, comp.reference, new_ref))

    return result


# ── Dialog ─────────────────────────────────────────────────────────────────────

class AnnotationDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._pending: list[tuple[Component, str, str]] = []
        self.setWindowTitle("Auto-Annotation — Numerowanie komponentów")
        self.resize(780, 560)
        self._build_ui()
        self._preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Params ────────────────────────────────────────────────────────────
        params_box = QGroupBox("Parametry numerowania")
        pf = QFormLayout(params_box)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems(list(_SORT_MODES.keys()))
        self._sort_combo.currentIndexChanged.connect(self._preview)
        pf.addRow("Kolejność sortowania:", self._sort_combo)

        self._start_spin = QSpinBox()
        self._start_spin.setRange(1, 9999)
        self._start_spin.setValue(1)
        self._start_spin.valueChanged.connect(self._preview)
        pf.addRow("Numeracja od:", self._start_spin)

        self._step_spin = QSpinBox()
        self._step_spin.setRange(1, 100)
        self._step_spin.setValue(1)
        self._step_spin.valueChanged.connect(self._preview)
        pf.addRow("Krok:", self._step_spin)

        self._prefix_cb = QCheckBox("Zachowaj istniejące prefiksy (nie zmieniaj R→U itp.)")
        self._prefix_cb.setChecked(False)
        self._prefix_cb.toggled.connect(self._preview)
        pf.addRow(self._prefix_cb)

        layout.addWidget(params_box)

        # ── Preview table ─────────────────────────────────────────────────────
        lbl = QLabel("Podgląd zmian (przed → po):")
        lbl.setStyleSheet("color:#aaa; font-size:10px;")
        layout.addWidget(lbl)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Stara ref.", "Nowa ref.", "Typ", "Wartość"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

        # ── Summary ───────────────────────────────────────────────────────────
        self._summary = QLabel()
        self._summary.setStyleSheet("color:#aaa; font-size:10px; padding:4px;")
        layout.addWidget(self._summary)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_preview = QPushButton("🔄 Odśwież podgląd")
        btn_preview.clicked.connect(self._preview)
        btn_row.addWidget(btn_preview)

        self._btn_apply = QPushButton("✔ Zastosuj numerowanie")
        self._btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        self._btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(self._btn_apply)

        btn_close = QPushButton("Anuluj")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _preview(self) -> None:
        board = self._project.board if self._project else None
        if not board or not board.components:
            self._summary.setText("Brak komponentów w projekcie.")
            return

        sort_name = self._sort_combo.currentText()
        sort_key = _SORT_MODES.get(sort_name, lambda c: c.reference)
        start = self._start_spin.value()
        step  = self._step_spin.value()

        self._pending = annotate(board.components, sort_key, start, step)

        self._table.setRowCount(0)
        changed = 0
        for comp, old_ref, new_ref in self._pending:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(old_ref))
            item_new = QTableWidgetItem(new_ref)
            if old_ref != new_ref:
                item_new.setForeground(QColor("#60e060"))
                changed += 1
            self._table.setItem(row, 1, item_new)
            self._table.setItem(row, 2, QTableWidgetItem(comp.component_type))
            self._table.setItem(row, 3, QTableWidgetItem(comp.value))

        total = len(self._pending)
        self._summary.setText(
            f"Łącznie: {total} komponentów  |  Zmian: {changed}  |  "
            f"Bez zmian: {total - changed}"
        )

    def _apply(self) -> None:
        if not self._pending:
            return
        reply = QMessageBox.question(
            self, "Potwierdź",
            f"Zastosować numerowanie dla {len(self._pending)} komponentów?\n"
            "Operacja nie jest cofalna (użyj Ctrl+Z jeśli chcesz cofnąć).",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for comp, old_ref, new_ref in self._pending:
            comp.reference = new_ref

        QMessageBox.information(
            self, "Gotowe",
            f"Przemianowano {len(self._pending)} komponentów."
        )
        self.accept()
