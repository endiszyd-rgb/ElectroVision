"""PCB Layer Stackup Editor — define layer thicknesses and materials."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QDoubleSpinBox, QComboBox, QSplitter, QTextEdit, QWidget,
    QFormLayout, QMessageBox, QFileDialog, QAbstractItemView,
    QToolBar, QSizePolicy
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QLinearGradient
)

from src.core.project import Project


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class StackupLayer:
    name: str
    layer_type: str      # "copper", "core", "prepreg", "soldermask", "finish"
    thickness_mm: float
    er: float = 4.5      # dielectric constant (for prepreg/core)
    loss_tangent: float = 0.02
    material: str = ""

    @property
    def color(self) -> QColor:
        t = self.layer_type
        if t == "copper":
            return QColor("#c87941")
        if t == "soldermask":
            return QColor("#1a5c1a")
        if t == "finish":
            return QColor("#d4af37")
        if t == "core":
            return QColor("#f0d060")
        if t == "prepreg":
            return QColor("#e8c090")
        return QColor("#888888")

    @property
    def is_dielectric(self) -> bool:
        return self.layer_type in ("core", "prepreg")


# ── Presets ────────────────────────────────────────────────────────────────────

def _make_2layer() -> list[StackupLayer]:
    return [
        StackupLayer("F.Finish",  "finish",    0.030, material="HASL"),
        StackupLayer("F.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("F.Cu",      "copper",    0.035),
        StackupLayer("Core",      "core",      1.500, 4.5, 0.02, "FR4"),
        StackupLayer("B.Cu",      "copper",    0.035),
        StackupLayer("B.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("B.Finish",  "finish",    0.030, material="HASL"),
    ]


def _make_4layer() -> list[StackupLayer]:
    return [
        StackupLayer("F.Finish",  "finish",    0.030, material="HASL"),
        StackupLayer("F.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("F.Cu",      "copper",    0.035),
        StackupLayer("Prepreg1",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("In1.Cu",    "copper",    0.017),
        StackupLayer("Core",      "core",      1.200, 4.5, 0.02, "FR4"),
        StackupLayer("In2.Cu",    "copper",    0.017),
        StackupLayer("Prepreg2",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("B.Cu",      "copper",    0.035),
        StackupLayer("B.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("B.Finish",  "finish",    0.030, material="HASL"),
    ]


def _make_6layer() -> list[StackupLayer]:
    layers = [
        StackupLayer("F.Finish",  "finish",    0.030, material="HASL"),
        StackupLayer("F.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("F.Cu",      "copper",    0.035),
        StackupLayer("Prepreg1",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("In1.Cu",    "copper",    0.017),
        StackupLayer("Prepreg2",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("In2.Cu",    "copper",    0.017),
        StackupLayer("Core",      "core",      1.000, 4.5, 0.02, "FR4"),
        StackupLayer("In3.Cu",    "copper",    0.017),
        StackupLayer("Prepreg3",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("In4.Cu",    "copper",    0.017),
        StackupLayer("Prepreg4",  "prepreg",   0.100, 4.3, 0.02, "FR4 7628"),
        StackupLayer("B.Cu",      "copper",    0.035),
        StackupLayer("B.Mask",    "soldermask",0.025, material="LPI"),
        StackupLayer("B.Finish",  "finish",    0.030, material="HASL"),
    ]
    return layers


_PRESETS = {
    "2-warstwowa (standard FR4 1.6mm)": _make_2layer,
    "4-warstwowa (FR4 1.6mm, JLC)":     _make_4layer,
    "6-warstwowa (FR4 1.6mm)":          _make_6layer,
}

_MATERIALS = {
    "core":      ["FR4", "Rogers 4003C", "Rogers 4350B", "Rogers 3003", "Isola 370HR", "Megtron 6"],
    "prepreg":   ["FR4 7628", "FR4 2116", "FR4 1080", "Rogers 4450F", "Isola P96"],
    "copper":    ["Rolled copper", "Electrodeposited"],
    "soldermask":["LPI Green", "LPI Red", "LPI Blue", "LPI Black", "LPI White"],
    "finish":    ["HASL (SnPb)", "HASL Lead-free", "ENIG", "OSP", "Immersion Silver", "ENEPIG"],
}


# ── Stackup cross-section widget ───────────────────────────────────────────────

class _StackupView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layers: list[StackupLayer] = []
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_layers(self, layers: list[StackupLayer]) -> None:
        self._layers = layers
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#1a1a2e"))

        if not self._layers:
            p.setPen(QColor("#555"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak warstw")
            return

        total_mm = sum(l.thickness_mm for l in self._layers)
        if total_mm <= 0:
            return

        margin = 16
        avail_h = self.height() - 2 * margin
        avail_w = self.width() - 120

        y = margin
        for layer in self._layers:
            h_px = max(4, int(avail_h * layer.thickness_mm / total_mm))
            rect = QRectF(60, y, avail_w, h_px)

            # Fill with gradient
            grad = QLinearGradient(60, y, 60 + avail_w, y)
            c = layer.color
            grad.setColorAt(0, c.lighter(130))
            grad.setColorAt(1, c)
            p.fillRect(rect, grad)

            # Border
            p.setPen(QPen(QColor("#333"), 1))
            p.drawRect(rect)

            # Label left
            p.setPen(QColor("#ddd"))
            p.setFont(QFont("Consolas", 8))
            p.drawText(QRectF(2, y, 55, h_px),
                       Qt.AlignRight | Qt.AlignVCenter, layer.name)

            # Thickness right
            p.drawText(QRectF(60 + avail_w + 4, y, 50, h_px),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{layer.thickness_mm*1000:.0f}µm")

            y += h_px

        # Total thickness label
        p.setPen(QColor("#aaa"))
        p.setFont(QFont("Arial", 9))
        p.drawText(
            QRectF(0, self.height() - 14, self.width(), 14),
            Qt.AlignCenter,
            f"Całkowita grubość: {total_mm:.3f} mm"
        )


# ── Impedance calculator for stackup ──────────────────────────────────────────

def calc_microstrip_z0(w_mm: float, h_mm: float, t_mm: float, er: float) -> float:
    """IPC-2141A microstrip impedance."""
    if h_mm <= 0 or w_mm <= 0:
        return 0.0
    weff = w_mm + (t_mm / math.pi) * (1 + math.log(4 * math.e * h_mm / t_mm)) if t_mm > 0 else w_mm
    u = weff / h_mm
    a = 1 + (1 / 49) * math.log((u**4 + (u / 52)**2) / (u**4 + 0.432)) + \
        (1 / 18.7) * math.log(1 + (u / 18.1)**3)
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    z0 = (87 / math.sqrt(er_eff + 1.41)) * math.log(5.98 * h_mm / (0.8 * weff + t_mm))
    return z0


def calc_stripline_z0(w_mm: float, h_mm: float, t_mm: float, er: float) -> float:
    """Stripline (symmetric) impedance."""
    if h_mm <= 0 or w_mm <= 0:
        return 0.0
    weff = w_mm + (t_mm / math.pi) * math.log(4 * math.e / math.sqrt((t_mm / h_mm)**2 + (t_mm / (math.pi * w_mm))**2)) if t_mm > 0 else w_mm
    z0 = (60 / math.sqrt(er)) * math.log(4 * h_mm / (0.67 * math.pi * (0.8 * weff + t_mm)))
    return max(0, z0)


# ── Dialog ─────────────────────────────────────────────────────────────────────

class StackupEditorDialog(QDialog):
    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Edytor stosu warstw PCB (Stackup)")
        self.resize(980, 680)
        self._layers: list[StackupLayer] = []
        self._build_ui()
        self._load_preset("2-warstwowa (standard FR4 1.6mm)")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Preset ────────────────────────────────────────────────────────────
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Szablon:"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(list(_PRESETS.keys()))
        preset_row.addWidget(self._preset_combo, 1)
        btn_load = QPushButton("Załaduj")
        btn_load.clicked.connect(lambda: self._load_preset(self._preset_combo.currentText()))
        preset_row.addWidget(btn_load)
        layout.addLayout(preset_row)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: table ───────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Nazwa", "Typ", "Grubość (mm)", "εr", "tan δ", "Materiał"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.itemChanged.connect(self._on_table_changed)
        ll.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Dodaj warstwę")
        btn_add.clicked.connect(self._add_layer)
        btn_row.addWidget(btn_add)
        btn_del = QPushButton("− Usuń")
        btn_del.clicked.connect(self._del_layer)
        btn_row.addWidget(btn_del)
        btn_up = QPushButton("↑")
        btn_up.clicked.connect(self._move_up)
        btn_row.addWidget(btn_up)
        btn_dn = QPushButton("↓")
        btn_dn.clicked.connect(self._move_down)
        btn_row.addWidget(btn_dn)
        ll.addLayout(btn_row)

        splitter.addWidget(left)

        # ── Right: preview + impedance ────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self._stackup_view = _StackupView()
        rl.addWidget(self._stackup_view, 1)

        # Impedance calculator
        imp_box = QGroupBox("Kalkulator impedancji")
        imp_form = QFormLayout(imp_box)

        self._imp_type = QComboBox()
        self._imp_type.addItems(["Microstrip (F.Cu / B.Cu)", "Stripline (wewnętrzna)"])
        self._imp_type.currentIndexChanged.connect(self._calc_impedance)
        imp_form.addRow("Typ struktury:", self._imp_type)

        self._imp_width = QDoubleSpinBox()
        self._imp_width.setRange(0.05, 20)
        self._imp_width.setValue(0.2)
        self._imp_width.setSuffix(" mm")
        self._imp_width.setDecimals(3)
        self._imp_width.valueChanged.connect(self._calc_impedance)
        imp_form.addRow("Szerokość ścieżki (W):", self._imp_width)

        self._imp_layer_combo = QComboBox()
        self._imp_layer_combo.currentIndexChanged.connect(self._calc_impedance)
        imp_form.addRow("Warstwa sygnałowa:", self._imp_layer_combo)

        self._imp_result = QLabel("Z₀ = ? Ω")
        self._imp_result.setFont(QFont("Consolas", 14))
        self._imp_result.setAlignment(Qt.AlignCenter)
        self._imp_result.setStyleSheet("color: #60e060; padding: 6px;")
        imp_form.addRow("Impedancja:", self._imp_result)

        self._imp_detail = QTextEdit()
        self._imp_detail.setReadOnly(True)
        self._imp_detail.setFont(QFont("Consolas", 8))
        self._imp_detail.setMaximumHeight(90)
        imp_form.addRow("Szczegóły:", self._imp_detail)

        # Target 50 Ω width
        self._target_spin = QDoubleSpinBox()
        self._target_spin.setRange(1, 200)
        self._target_spin.setValue(50)
        self._target_spin.setSuffix(" Ω")
        self._target_spin.valueChanged.connect(self._calc_impedance)
        imp_form.addRow("Docelowa Z₀:", self._target_spin)

        self._target_width_label = QLabel("")
        self._target_width_label.setFont(QFont("Consolas", 10))
        imp_form.addRow("Szerokość dla Z₀:", self._target_width_label)

        rl.addWidget(imp_box)

        splitter.addWidget(right)
        splitter.setSizes([500, 480])
        layout.addWidget(splitter, 1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_export = QPushButton("📄 Eksportuj stackup")
        btn_export.clicked.connect(self._export)
        btn_row.addWidget(btn_export)

        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _load_preset(self, name: str) -> None:
        fn = _PRESETS.get(name)
        if fn:
            self._layers = fn()
            self._rebuild_table()
            self._update_view()

    def _rebuild_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for layer in self._layers:
            self._append_table_row(layer)
        self._table.blockSignals(False)
        self._rebuild_layer_combo()

    def _append_table_row(self, layer: StackupLayer) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(layer.name))

        type_combo = QComboBox()
        type_combo.addItems(["copper", "core", "prepreg", "soldermask", "finish"])
        type_combo.setCurrentText(layer.layer_type)
        type_combo.currentTextChanged.connect(self._on_type_changed)
        self._table.setCellWidget(row, 1, type_combo)

        self._table.setItem(row, 2, QTableWidgetItem(f"{layer.thickness_mm:.4f}"))
        self._table.setItem(row, 3, QTableWidgetItem(f"{layer.er:.2f}"))
        self._table.setItem(row, 4, QTableWidgetItem(f"{layer.loss_tangent:.4f}"))
        self._table.setItem(row, 5, QTableWidgetItem(layer.material))

        # Color row background
        clr = layer.color.darker(150)
        for col in range(6):
            item = self._table.item(row, col)
            if item:
                item.setBackground(QBrush(clr))

    def _on_type_changed(self) -> None:
        self._sync_from_table()

    def _on_table_changed(self, item) -> None:
        self._sync_from_table()

    def _sync_from_table(self) -> None:
        new_layers = []
        for row in range(self._table.rowCount()):
            name = (self._table.item(row, 0) or QTableWidgetItem("")).text()
            type_w = self._table.cellWidget(row, 1)
            ltype = type_w.currentText() if type_w else "core"
            try:
                t = float((self._table.item(row, 2) or QTableWidgetItem("0")).text())
            except ValueError:
                t = 0.1
            try:
                er = float((self._table.item(row, 3) or QTableWidgetItem("4.5")).text())
            except ValueError:
                er = 4.5
            try:
                lt = float((self._table.item(row, 4) or QTableWidgetItem("0.02")).text())
            except ValueError:
                lt = 0.02
            mat = (self._table.item(row, 5) or QTableWidgetItem("")).text()
            new_layers.append(StackupLayer(name, ltype, t, er, lt, mat))
        self._layers = new_layers
        self._update_view()

    def _update_view(self) -> None:
        self._stackup_view.set_layers(self._layers)
        self._rebuild_layer_combo()
        self._calc_impedance()

    def _rebuild_layer_combo(self) -> None:
        self._imp_layer_combo.blockSignals(True)
        self._imp_layer_combo.clear()
        for l in self._layers:
            if l.layer_type == "copper":
                self._imp_layer_combo.addItem(l.name)
        self._imp_layer_combo.blockSignals(False)
        self._calc_impedance()

    def _get_dielectric_below(self, copper_name: str) -> tuple[float, float]:
        """Return (h_mm, er) of first dielectric below given copper layer."""
        idx = next((i for i, l in enumerate(self._layers) if l.name == copper_name), -1)
        if idx < 0:
            return 1.6, 4.5
        for l in self._layers[idx + 1:]:
            if l.is_dielectric:
                return l.thickness_mm, l.er
        return 1.6, 4.5

    def _calc_impedance(self) -> None:
        w = self._imp_width.value()
        copper_name = self._imp_layer_combo.currentText()
        t = 0.035
        for l in self._layers:
            if l.name == copper_name:
                t = l.thickness_mm
                break

        imp_type = self._imp_type.currentIndex()

        if imp_type == 0:  # microstrip
            h, er = self._get_dielectric_below(copper_name)
            z0 = calc_microstrip_z0(w, h, t, er)
            detail = (
                f"Microstrip: W={w:.3f}mm, H={h:.3f}mm, T={t:.3f}mm, εr={er:.1f}\n"
                f"Z₀ = {z0:.2f} Ω"
            )
        else:  # stripline
            # Find dielectrics above and below
            idx = next((i for i, l in enumerate(self._layers) if l.name == copper_name), -1)
            h_above = sum(l.thickness_mm for l in self._layers[:idx] if l.is_dielectric)
            h_below = sum(l.thickness_mm for l in self._layers[idx+1:] if l.is_dielectric)
            h_total = h_above + h_below
            er_vals = [l.er for l in self._layers if l.is_dielectric]
            er = sum(er_vals) / len(er_vals) if er_vals else 4.5
            z0 = calc_stripline_z0(w, h_total, t, er)
            detail = (
                f"Stripline: W={w:.3f}mm, H={h_total:.3f}mm, T={t:.3f}mm, εr={er:.1f}\n"
                f"Z₀ = {z0:.2f} Ω"
            )

        self._imp_result.setText(f"Z₀ = {z0:.1f} Ω")
        color = "#60e060" if abs(z0 - 50) < 5 else ("#f0a040" if abs(z0 - 50) < 15 else "#e06060")
        self._imp_result.setStyleSheet(f"color: {color}; padding: 6px; font-size: 16px;")
        self._imp_detail.setPlainText(detail)

        # Solve for target width (binary search)
        target = self._target_spin.value()
        if imp_type == 0:
            h, er = self._get_dielectric_below(copper_name)
            w_target = self._solve_width_microstrip(target, h, t, er)
            self._target_width_label.setText(f"{w_target:.3f} mm")
        else:
            self._target_width_label.setText("(brak dla stripline)")

    def _solve_width_microstrip(self, z0_target: float, h: float, t: float, er: float) -> float:
        lo, hi = 0.01, 20.0
        for _ in range(50):
            mid = (lo + hi) / 2
            z = calc_microstrip_z0(mid, h, t, er)
            if z > z0_target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def _add_layer(self) -> None:
        self._table.blockSignals(True)
        layer = StackupLayer("Nowa", "core", 0.100, 4.5, 0.02, "FR4")
        self._layers.append(layer)
        self._append_table_row(layer)
        self._table.blockSignals(False)
        self._update_view()

    def _del_layer(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._sync_from_table()

    def _move_up(self) -> None:
        row = self._table.currentRow()
        if row <= 0:
            return
        self._layers[row], self._layers[row-1] = self._layers[row-1], self._layers[row]
        self._rebuild_table()
        self._table.selectRow(row - 1)

    def _move_down(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._layers) - 1:
            return
        self._layers[row], self._layers[row+1] = self._layers[row+1], self._layers[row]
        self._rebuild_table()
        self._table.selectRow(row + 1)

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj stackup", "stackup.txt", "Tekst (*.txt)"
        )
        if not path:
            return
        total = sum(l.thickness_mm for l in self._layers)
        lines = ["PCB STACKUP — ElectroVision", "=" * 50, ""]
        for i, l in enumerate(self._layers, 1):
            lines.append(
                f"{i:2d}. {l.name:20s}  {l.layer_type:12s}  "
                f"{l.thickness_mm*1000:6.1f} µm  "
                f"εr={l.er:.2f}  mat={l.material}"
            )
        lines.append(f"\nCałkowita grubość: {total:.3f} mm")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Eksport", f"Stackup zapisany:\n{path}")
