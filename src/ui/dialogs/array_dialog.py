"""Component Array Dialog — generate grids or linear arrays of components."""
from __future__ import annotations
import re
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
    QComboBox, QCheckBox, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from src.core.project import Project
from src.core.models.component import Component, Pad


# ── Preview widget ─────────────────────────────────────────────────────────────

class _ArrayPreview(QWidget):
    BG   = QColor("#0d1117")
    COMP = QColor("#2a4060")
    BDR  = QColor("#4080b0")
    SEL  = QColor("#60ff80")
    TXT  = QColor("#c0d0e0")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._placements: list[tuple[str, float, float]] = []  # (ref, x, y)
        self.setMinimumSize(280, 200)

    def set_placements(self, placements: list[tuple[str, float, float]]) -> None:
        self._placements = placements
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._placements:
            p.setPen(QColor("#555"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak danych")
            return

        xs = [x for _, x, y in self._placements]
        ys = [y for _, x, y in self._placements]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        w_data = max(x1 - x0, 1.0)
        h_data = max(y1 - y0, 1.0)
        margin = 28
        sx = (self.width()  - margin * 2) / w_data
        sy = (self.height() - margin * 2) / h_data
        scale = min(sx, sy, 10.0)

        def tx(x): return margin + (x - x0) * scale
        def ty(y): return margin + (y - y0) * scale

        comp_w = max(6, 3 * scale)
        comp_h = max(4, 2 * scale)

        for i, (ref, cx, cy) in enumerate(self._placements):
            rx = tx(cx) - comp_w / 2
            ry = ty(cy) - comp_h / 2
            fill = self.SEL if i == 0 else self.COMP
            p.setPen(QPen(self.BDR, 1))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(QRectF(rx, ry, comp_w, comp_h), 2, 2)

            if scale > 3:
                p.setPen(self.TXT)
                p.setFont(QFont("Consolas", max(5, int(scale * 1.2))))
                p.drawText(QRectF(rx, ry, comp_w, comp_h), Qt.AlignCenter, ref)


# ── Renaming logic ─────────────────────────────────────────────────────────────

def _extract_prefix_num(ref: str) -> tuple[str, int]:
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref)
    if m:
        return m.group(1), int(m.group(2))
    return ref, 0


def _find_free_ref(prefix: str, start: int, used: set[str]) -> str:
    n = start
    while True:
        r = f"{prefix}{n}"
        if r not in used:
            return r
        n += 1


def generate_array(
    source: Component,
    all_refs: set[str],
    mode: str,          # "grid" | "linear_h" | "linear_v"
    cols: int,
    rows: int,
    step_x: float,
    step_y: float,
    start_ref_num: int,
    net_increment: bool,
    net_pattern: str,   # e.g. "LED{n}" — {n} substituted per copy
) -> list[tuple[Component, str]]:
    """Return list of (new_component, suggested_reference) for each array cell."""
    prefix, _ = _extract_prefix_num(source.reference)
    used = set(all_refs)
    used.discard(source.reference)  # source can be reused

    placements: list[tuple[float, float]] = []
    if mode == "grid":
        for r in range(rows):
            for c in range(cols):
                placements.append((source.x + c * step_x, source.y + r * step_y))
    elif mode == "linear_h":
        for i in range(cols):
            placements.append((source.x + i * step_x, source.y))
    else:  # linear_v
        for i in range(rows):
            placements.append((source.x, source.y + i * step_y))

    result = []
    num = start_ref_num
    for i, (nx, ny) in enumerate(placements):
        new_ref = _find_free_ref(prefix, num, used)
        used.add(new_ref)
        num += 1

        # Clone component
        new_comp = Component(
            reference=new_ref,
            value=source.value,
            footprint=source.footprint,
            x=nx,
            y=ny,
            rotation=source.rotation,
            layer=source.layer,
            description=source.description,
            manufacturer=source.manufacturer,
            manufacturer_pn=source.manufacturer_pn,
        )
        # Clone pads with optional net substitution
        new_comp.pads = []
        for pad in source.pads:
            new_net = pad.net_name
            if net_increment and net_pattern and "{n}" in net_pattern:
                new_net = net_pattern.replace("{n}", str(i + 1))
            new_comp.pads.append(Pad(
                number=pad.number,
                pad_type=pad.pad_type,
                shape=pad.shape,
                x=pad.x,
                y=pad.y,
                width=pad.width,
                height=pad.height,
                net_name=new_net,
                drill=pad.drill,
            ))
        result.append((new_comp, new_ref))

    return result


# ── Dialog ─────────────────────────────────────────────────────────────────────

class ArrayDialog(QDialog):
    components_added = Signal(list)   # list[Component]

    def __init__(self, project: Project, source_comp: Component | None = None, parent=None):
        super().__init__(parent)
        self._project = project
        self._source  = source_comp
        self._preview_data: list[tuple[str, float, float]] = []
        self.setWindowTitle("Generator tablicy komponentów")
        self.resize(800, 580)
        self._build_ui()
        if source_comp:
            self._src_combo.setCurrentText(source_comp.reference)
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Source component ─────────────────────────────────────────────────
        src_box = QGroupBox("Komponent źródłowy")
        sf = QFormLayout(src_box)
        self._src_combo = QComboBox()
        board = self._project.board if self._project else None
        if board:
            for comp in sorted(board.components, key=lambda c: c.reference):
                self._src_combo.addItem(f"{comp.reference} — {comp.value}", comp.reference)
        self._src_combo.currentIndexChanged.connect(self._on_src_changed)
        sf.addRow("Komponent:", self._src_combo)
        self._src_info = QLabel()
        self._src_info.setStyleSheet("color: #aaa; font-size: 10px;")
        sf.addRow(self._src_info)
        layout.addWidget(src_box)

        # ── Array parameters ─────────────────────────────────────────────────
        arr_box = QGroupBox("Parametry tablicy")
        af = QFormLayout(arr_box)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems([
            "Siatka 2D (rows × cols)",
            "Liniowy poziomy (1 × cols)",
            "Liniowy pionowy (rows × 1)",
        ])
        self._mode_combo.currentIndexChanged.connect(self._update_preview)
        af.addRow("Tryb:", self._mode_combo)

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 50)
        self._cols_spin.setValue(4)
        self._cols_spin.valueChanged.connect(self._update_preview)
        af.addRow("Kolumny:", self._cols_spin)

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 50)
        self._rows_spin.setValue(2)
        self._rows_spin.valueChanged.connect(self._update_preview)
        af.addRow("Wiersze:", self._rows_spin)

        self._step_x_spin = QDoubleSpinBox()
        self._step_x_spin.setRange(0.1, 200.0)
        self._step_x_spin.setValue(5.0)
        self._step_x_spin.setSuffix(" mm")
        self._step_x_spin.setSingleStep(0.5)
        self._step_x_spin.valueChanged.connect(self._update_preview)
        af.addRow("Odstęp X:", self._step_x_spin)

        self._step_y_spin = QDoubleSpinBox()
        self._step_y_spin.setRange(0.1, 200.0)
        self._step_y_spin.setValue(5.0)
        self._step_y_spin.setSuffix(" mm")
        self._step_y_spin.setSingleStep(0.5)
        self._step_y_spin.valueChanged.connect(self._update_preview)
        af.addRow("Odstęp Y:", self._step_y_spin)

        self._start_spin = QSpinBox()
        self._start_spin.setRange(1, 9999)
        self._start_spin.setValue(1)
        self._start_spin.valueChanged.connect(self._update_preview)
        af.addRow("Numeracja od:", self._start_spin)

        layout.addWidget(arr_box)

        # ── Net assignment ────────────────────────────────────────────────────
        net_box = QGroupBox("Przypisanie sieci (opcjonalne)")
        nf = QFormLayout(net_box)
        self._net_inc_cb = QCheckBox("Automatyczne sieci per element")
        self._net_inc_cb.toggled.connect(self._update_preview)
        nf.addRow(self._net_inc_cb)
        self._net_pattern = QLineEdit()
        self._net_pattern.setPlaceholderText("np. LED{n}  lub  PWM{n}")
        self._net_pattern.setToolTip("{n} zostanie zastąpione numerem elementu (1-N)")
        self._net_pattern.textChanged.connect(self._update_preview)
        nf.addRow("Wzorzec sieci:", self._net_pattern)
        layout.addWidget(net_box)

        # ── Preview split: table + canvas ─────────────────────────────────────
        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Horizontal)

        self._preview = _ArrayPreview()
        splitter.addWidget(self._preview)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Referencja", "X (mm)", "Y (mm)", "Wartość"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        splitter.addWidget(self._table)

        splitter.setSizes([280, 380])
        layout.addWidget(splitter, 1)

        # ── Summary ───────────────────────────────────────────────────────────
        self._summary = QLabel()
        self._summary.setStyleSheet("color: #aaa; font-size: 10px; padding: 2px;")
        layout.addWidget(self._summary)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("✔ Dodaj tablicę do płytki")
        btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)
        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_src_changed(self) -> None:
        ref = self._src_combo.currentData()
        board = self._project.board if self._project else None
        if board and ref:
            comp = next((c for c in board.components if c.reference == ref), None)
            if comp:
                self._source = comp
                self._src_info.setText(
                    f"Typ: {comp.component_type}  |  Footprint: {comp.footprint.split(':')[-1]}  |  "
                    f"Pady: {len(comp.pads)}  |  Pozycja: ({comp.x:.2f}, {comp.y:.2f})"
                )
        self._update_preview()

    def _mode_str(self) -> str:
        idx = self._mode_combo.currentIndex()
        return ["grid", "linear_h", "linear_v"][idx]

    def _update_preview(self) -> None:
        if not self._source:
            return
        board = self._project.board if self._project else None
        all_refs = {c.reference for c in board.components} if board else set()

        try:
            comps = generate_array(
                self._source, all_refs,
                mode=self._mode_str(),
                cols=self._cols_spin.value(),
                rows=self._rows_spin.value(),
                step_x=self._step_x_spin.value(),
                step_y=self._step_y_spin.value(),
                start_ref_num=self._start_spin.value(),
                net_increment=self._net_inc_cb.isChecked(),
                net_pattern=self._net_pattern.text(),
            )
        except Exception:
            return

        self._preview_data = [(ref, c.x, c.y) for c, ref in comps]
        self._preview.set_placements(self._preview_data)

        # Populate table
        self._table.setRowCount(0)
        for comp, ref in comps:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(ref))
            self._table.setItem(row, 1, QTableWidgetItem(f"{comp.x:.3f}"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{comp.y:.3f}"))
            self._table.setItem(row, 3, QTableWidgetItem(comp.value))

        n = len(comps)
        mode_labels = {"grid": "siatka", "linear_h": "liniowy H", "linear_v": "liniowy V"}
        self._summary.setText(
            f"Łącznie: {n} komponentów  |  Tryb: {mode_labels[self._mode_str()]}  |  "
            f"Pokryty obszar: {(self._cols_spin.value()-1)*self._step_x_spin.value():.1f} × "
            f"{(self._rows_spin.value()-1)*self._step_y_spin.value():.1f} mm"
        )

    def _apply(self) -> None:
        if not self._source:
            QMessageBox.warning(self, "Błąd", "Wybierz komponent źródłowy.")
            return
        board = self._project.board if self._project else None
        if not board:
            return
        all_refs = {c.reference for c in board.components}

        comps = generate_array(
            self._source, all_refs,
            mode=self._mode_str(),
            cols=self._cols_spin.value(),
            rows=self._rows_spin.value(),
            step_x=self._step_x_spin.value(),
            step_y=self._step_y_spin.value(),
            start_ref_num=self._start_spin.value(),
            net_increment=self._net_inc_cb.isChecked(),
            net_pattern=self._net_pattern.text(),
        )

        if not comps:
            QMessageBox.information(self, "Info", "Brak komponentów do dodania.")
            return

        reply = QMessageBox.question(
            self, "Potwierdź",
            f"Dodać {len(comps)} komponentów do płytki?\n"
            f"Pierwszy: {comps[0][1]}, Ostatni: {comps[-1][1]}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        new_comps = [c for c, _ in comps]
        board.components.extend(new_comps)
        self.components_added.emit(new_comps)
        self.accept()
