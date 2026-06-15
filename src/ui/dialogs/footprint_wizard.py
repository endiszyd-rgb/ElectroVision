"""Footprint Wizard — generate custom SMD/THT footprints from datasheet specs."""
from __future__ import annotations
import math
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
    QComboBox, QLineEdit, QCheckBox, QTabWidget, QWidget,
    QSplitter, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from src.core.project import Project
from src.core.models.component import Component, Pad


# ── Pad placement generators ──────────────────────────────────────────────────

@dataclass
class FootprintSpec:
    name: str
    description: str
    pads: list[Pad] = field(default_factory=list)
    courtyard_w: float = 0.0
    courtyard_h: float = 0.0


def gen_smd_passive(pitch: float, pad_w: float, pad_h: float) -> list[Pad]:
    """Two-pad SMD resistor/capacitor/inductor."""
    return [
        Pad("1", "smd", "rect", -pitch / 2, 0.0, pad_w, pad_h, net_name=""),
        Pad("2", "smd", "rect",  pitch / 2, 0.0, pad_w, pad_h, net_name=""),
    ]


def gen_soic(
    n_pins: int,          # must be even, total pin count
    pitch: float,         # pin pitch mm (usually 1.27)
    row_spacing: float,   # distance between rows (body width + 2*land)
    pad_w: float,
    pad_h: float,
) -> list[Pad]:
    """SOIC/SOP/TSSOP dual row package (pins numbered CCW from pin 1 top-left)."""
    pads = []
    half = n_pins // 2
    for i in range(half):
        y = -(half - 1) * pitch / 2 + i * pitch
        pads.append(Pad(str(i + 1), "smd", "rect",
                        -row_spacing / 2, y, pad_w, pad_h))
    for i in range(half):
        y = (half - 1) * pitch / 2 - i * pitch
        pads.append(Pad(str(half + i + 1), "smd", "rect",
                         row_spacing / 2, y, pad_w, pad_h))
    return pads


def gen_qfp(
    n_pins: int,          # total, divisible by 4
    pitch: float,
    body_size: float,     # square body side
    pad_w: float,
    pad_h: float,
) -> list[Pad]:
    """QFP/TQFP/LQFP square packages."""
    side = n_pins // 4
    pads = []
    start = -(side - 1) * pitch / 2
    span  = body_size / 2 + pad_h / 2 + 0.3

    # Bottom side (pins 1..)
    for i in range(side):
        pads.append(Pad(str(i + 1), "smd", "rect",
                        start + i * pitch, span, pad_w, pad_h))
    # Right side
    for i in range(side):
        pads.append(Pad(str(side + i + 1), "smd", "rect",
                        span, -(start + i * pitch), pad_h, pad_w))
    # Top side
    for i in range(side):
        pads.append(Pad(str(2 * side + i + 1), "smd", "rect",
                        -(start + i * pitch), -span, pad_w, pad_h))
    # Left side
    for i in range(side):
        pads.append(Pad(str(3 * side + i + 1), "smd", "rect",
                        -span, start + i * pitch, pad_h, pad_w))
    return pads


def gen_dip(
    n_pins: int,          # even, total
    pitch: float = 2.54,
    row_spacing: float = 7.62,
    drill: float = 0.8,
    pad_dia: float = 1.6,
) -> list[Pad]:
    """DIP through-hole package."""
    pads = []
    half = n_pins // 2
    for i in range(half):
        y = -(half - 1) * pitch / 2 + i * pitch
        pads.append(Pad(str(i + 1), "thru_hole", "circle",
                        -row_spacing / 2, y, pad_dia, pad_dia,
                        net_name="", drill=drill))
    for i in range(half):
        y = (half - 1) * pitch / 2 - i * pitch
        pads.append(Pad(str(half + i + 1), "thru_hole", "circle",
                         row_spacing / 2, y, pad_dia, pad_dia,
                         net_name="", drill=drill))
    return pads


def gen_sot23(pins: int = 3) -> list[Pad]:
    """SOT-23 / SOT-23-5 / SOT-23-6."""
    pad_w, pad_h = 0.9, 1.3
    if pins == 3:
        return [
            Pad("1", "smd", "rect", -0.95, 0.95,  pad_w, pad_h),
            Pad("2", "smd", "rect",  0.95, 0.95,  pad_w, pad_h),
            Pad("3", "smd", "rect",  0.0,  -0.95, pad_w, pad_h),
        ]
    elif pins == 5:
        return [
            Pad("1", "smd", "rect", -0.95, 1.4,  pad_w, pad_h),
            Pad("2", "smd", "rect", -0.95, 0.0,  pad_w, pad_h),
            Pad("3", "smd", "rect", -0.95, -1.4, pad_w, pad_h),
            Pad("4", "smd", "rect",  0.95, -0.7, pad_w, pad_h),
            Pad("5", "smd", "rect",  0.95,  0.7, pad_w, pad_h),
        ]
    else:
        return gen_soic(pins, 0.95, 2.3, pad_w, pad_h)


def gen_to92(drill: float = 0.8) -> list[Pad]:
    """TO-92 transistor (3 pins)."""
    r = 1.0
    return [
        Pad("1", "thru_hole", "circle", -r, 0, 1.6, 1.6, drill=drill),
        Pad("2", "thru_hole", "circle",  0, 0, 1.6, 1.6, drill=drill),
        Pad("3", "thru_hole", "circle",  r, 0, 1.6, 1.6, drill=drill),
    ]


def gen_qfn(n_pins: int, pitch: float, body: float,
            pad_w: float = 0.25, pad_h: float = 0.7,
            thermal: bool = True, thermal_size: float = 0) -> list[Pad]:
    """QFN/MLF package with optional thermal pad."""
    side = n_pins // 4
    pads = gen_qfp(n_pins, pitch, body, pad_w, pad_h)
    # QFN pads sit along the edge (not extended)
    # Recalculate positions for QFN (pads flush with body edge)
    pads2 = []
    start = -(side - 1) * pitch / 2
    e = body / 2  # pad center offset from body center

    def _side_pads(n, x_fixed, y_start, pitch, transpose):
        result = []
        for i in range(n):
            y = y_start + i * pitch
            if transpose:
                result.append(Pad(str(i), "smd", "rect", y, x_fixed, pad_h, pad_w))
            else:
                result.append(Pad(str(i), "smd", "rect", x_fixed, y, pad_w, pad_h))
        return result

    # Bottom
    for i in range(side):
        pads2.append(Pad(str(i + 1), "smd", "rect",
                         start + i * pitch, e, pad_w, pad_h))
    # Right
    for i in range(side):
        pads2.append(Pad(str(side + i + 1), "smd", "rect",
                         e, -(start + i * pitch), pad_h, pad_w))
    # Top
    for i in range(side):
        pads2.append(Pad(str(2 * side + i + 1), "smd", "rect",
                         -(start + i * pitch), -e, pad_w, pad_h))
    # Left
    for i in range(side):
        pads2.append(Pad(str(3 * side + i + 1), "smd", "rect",
                         -e, start + i * pitch, pad_h, pad_w))
    # Thermal pad
    if thermal:
        ts = thermal_size or (body * 0.65)
        pads2.append(Pad("EP", "smd", "rect", 0, 0, ts, ts, net_name="GND"))

    return pads2


# ── Preview widget ─────────────────────────────────────────────────────────────

class _FPPreview(QWidget):
    BG      = QColor("#0d1117")
    PAD_SMD = QColor("#c87941")
    PAD_THT = QColor("#4080c0")
    PAD_THM = QColor("#c04040")
    BODY    = QColor("#1e2830")
    BODY_BD = QColor("#304848")
    TEXT    = QColor("#c0d0e0")
    PIN1    = QColor("#60e060")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pads: list[Pad] = []
        self._body_w = 0.0
        self._body_h = 0.0
        self.setMinimumSize(260, 220)

    def set_pads(self, pads: list[Pad], body_w: float = 0, body_h: float = 0) -> None:
        self._pads   = pads
        self._body_w = body_w
        self._body_h = body_h
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._pads:
            p.setPen(QColor("#555"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak padów")
            return

        xs = [pad.x for pad in self._pads]
        ys = [pad.y for pad in self._pads]
        ws = [max(pad.width, pad.height, 0.1) for pad in self._pads]
        x_min = min(xs) - max(ws) * 0.7
        x_max = max(xs) + max(ws) * 0.7
        y_min = min(ys) - max(ws) * 0.7
        y_max = max(ys) + max(ws) * 0.7

        margin = 20
        W = self.width()  - 2 * margin
        H = self.height() - 2 * margin
        w_data = max(x_max - x_min, 0.1)
        h_data = max(y_max - y_min, 0.1)
        scale = min(W / w_data, H / h_data, 40.0)

        def tx(x): return margin + (x - x_min) * scale
        def ty(y): return margin + (y - y_min) * scale

        # Body
        if self._body_w > 0 and self._body_h > 0:
            bx0 = tx(-self._body_w / 2)
            by0 = ty(-self._body_h / 2)
            bw  = self._body_w * scale
            bh  = self._body_h * scale
            p.setPen(QPen(self.BODY_BD, 1))
            p.setBrush(QBrush(self.BODY))
            p.drawRect(QRectF(bx0, by0, bw, bh))
            # Pin 1 marker
            p.setPen(QPen(self.PIN1, 1))
            p.drawLine(int(bx0), int(by0), int(bx0 + bw * 0.15), int(by0))
            p.drawLine(int(bx0), int(by0), int(bx0), int(by0 + bh * 0.15))

        # Pads
        for pad in self._pads:
            pw = max(2, pad.width  * scale)
            ph = max(2, pad.height * scale)
            cx = tx(pad.x)
            cy = ty(pad.y)
            is_ep = pad.number == "EP"
            if is_ep:
                color = self.PAD_THM
            elif pad.drill > 0:
                color = self.PAD_THT
            else:
                color = self.PAD_SMD

            p.setPen(QPen(QColor("#000"), 0.5))
            p.setBrush(QBrush(color))
            if pad.shape == "circle" or pad.drill > 0:
                r = min(pw, ph) / 2
                p.drawEllipse(QPointF(cx, cy), r, r)
                if pad.drill > 0:
                    dr = max(1, pad.drill * scale / 2)
                    p.setBrush(QBrush(self.BG))
                    p.drawEllipse(QPointF(cx, cy), dr, dr)
            else:
                p.drawRect(QRectF(cx - pw / 2, cy - ph / 2, pw, ph))

            # Pin number
            if scale > 5:
                p.setPen(self.TEXT)
                p.setFont(QFont("Arial", max(5, int(min(pw, ph) * 0.4))))
                p.drawText(QRectF(cx - pw/2, cy - ph/2, pw, ph),
                           Qt.AlignCenter, pad.number)


# ── Dialog ─────────────────────────────────────────────────────────────────────

_PACKAGE_PRESETS = {
    "SMD — Rezystor / Kondensator": "passive",
    "SOIC-8":          "soic8",
    "SOIC-14":         "soic14",
    "SOIC-16":         "soic16",
    "SOIC-20":         "soic20",
    "TSSOP-8":         "tssop8",
    "TSSOP-16":        "tssop16",
    "QFP-32":          "qfp32",
    "QFP-44":          "qfp44",
    "QFP-64":          "qfp64",
    "QFP-100":         "qfp100",
    "QFN-16":          "qfn16",
    "QFN-32":          "qfn32",
    "QFN-48":          "qfn48",
    "SOT-23 (3 piny)": "sot23_3",
    "SOT-23-5":        "sot23_5",
    "DIP-8":           "dip8",
    "DIP-14":          "dip14",
    "DIP-16":          "dip16",
    "DIP-20":          "dip20",
    "DIP-28":          "dip28",
    "TO-92":           "to92",
    "Własny (QFP)":    "custom_qfp",
    "Własny (SOIC)":   "custom_soic",
    "Własny (DIP)":    "custom_dip",
    "Własny (pasywny)":"custom_passive",
}

_PASSIVE_SIZES = {
    "0201": (0.5,  0.3,  0.25, 0.3),
    "0402": (0.8,  0.5,  0.5,  0.5),
    "0603": (1.0,  0.8,  0.7,  0.8),
    "0805": (1.3,  0.8,  1.0,  1.3),
    "1206": (1.8,  1.0,  1.5,  1.6),
    "2010": (2.4,  0.8,  1.8,  1.0),
    "2512": (3.0,  1.2,  2.0,  1.2),
}


class FootprintWizardDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._pads: list[Pad] = []
        self.setWindowTitle("Kreator footprintu — Generator obudowy")
        self.resize(860, 580)
        self._build_ui()
        self._on_preset_changed()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: configuration ────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        # Component info
        info_box = QGroupBox("Informacje o komponencie")
        inf = QFormLayout(info_box)

        self._ref_edit = QLineEdit("U1")
        inf.addRow("Referencja:", self._ref_edit)

        self._val_edit = QLineEdit()
        self._val_edit.setPlaceholderText("np. 10k, 100nF, MCU32…")
        inf.addRow("Wartość:", self._val_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Opcjonalny opis")
        inf.addRow("Opis:", self._desc_edit)

        ll.addWidget(info_box)

        # Package selector
        pkg_box = QGroupBox("Typ obudowy")
        pf = QFormLayout(pkg_box)

        self._preset_combo = QComboBox()
        self._preset_combo.addItems(list(_PACKAGE_PRESETS.keys()))
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        pf.addRow("Preset:", self._preset_combo)

        self._size_combo = QComboBox()
        self._size_combo.addItems(list(_PASSIVE_SIZES.keys()))
        self._size_combo.setCurrentText("0402")
        self._size_combo.currentTextChanged.connect(self._on_preset_changed)
        pf.addRow("Rozmiar SMD:", self._size_combo)

        ll.addWidget(pkg_box)

        # Custom params
        custom_box = QGroupBox("Parametry niestandardowe")
        cf = QFormLayout(custom_box)

        self._n_pins_spin = QSpinBox()
        self._n_pins_spin.setRange(2, 256)
        self._n_pins_spin.setValue(8)
        self._n_pins_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Liczba pinów:", self._n_pins_spin)

        self._pitch_spin = QDoubleSpinBox()
        self._pitch_spin.setRange(0.1, 5.0)
        self._pitch_spin.setValue(1.27)
        self._pitch_spin.setSingleStep(0.05)
        self._pitch_spin.setSuffix(" mm")
        self._pitch_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Pitch (rozstaw):", self._pitch_spin)

        self._row_span_spin = QDoubleSpinBox()
        self._row_span_spin.setRange(0.5, 30.0)
        self._row_span_spin.setValue(5.4)
        self._row_span_spin.setSuffix(" mm")
        self._row_span_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Rozstaw rzędów:", self._row_span_spin)

        self._body_spin = QDoubleSpinBox()
        self._body_spin.setRange(0.5, 40.0)
        self._body_spin.setValue(5.0)
        self._body_spin.setSuffix(" mm")
        self._body_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Wymiar ciała:", self._body_spin)

        self._pad_w_spin = QDoubleSpinBox()
        self._pad_w_spin.setRange(0.05, 5.0)
        self._pad_w_spin.setValue(0.5)
        self._pad_w_spin.setSuffix(" mm")
        self._pad_w_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Szerokość pada:", self._pad_w_spin)

        self._pad_h_spin = QDoubleSpinBox()
        self._pad_h_spin.setRange(0.05, 5.0)
        self._pad_h_spin.setValue(1.2)
        self._pad_h_spin.setSuffix(" mm")
        self._pad_h_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Długość pada:", self._pad_h_spin)

        self._drill_spin = QDoubleSpinBox()
        self._drill_spin.setRange(0.1, 3.0)
        self._drill_spin.setValue(0.8)
        self._drill_spin.setSuffix(" mm")
        self._drill_spin.valueChanged.connect(self._update_preview)
        cf.addRow("Wiercenie (THT):", self._drill_spin)

        self._thermal_cb = QCheckBox("Dodaj pad termiczny (EP)")
        self._thermal_cb.setChecked(True)
        self._thermal_cb.toggled.connect(self._update_preview)
        cf.addRow(self._thermal_cb)

        ll.addWidget(custom_box)
        ll.addStretch()

        splitter.addWidget(left)

        # ── Right: preview + pad list ──────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self._preview = _FPPreview()
        rl.addWidget(self._preview, 1)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px;")
        rl.addWidget(self._info_label)

        splitter.addWidget(right)
        splitter.setSizes([320, 420])
        layout.addWidget(splitter, 1)

        # ── Placement options ──────────────────────────────────────────────────
        place_box = QGroupBox("Umieszczenie na płytce")
        plf = QFormLayout(place_box)
        self._place_x_spin = QDoubleSpinBox()
        self._place_x_spin.setRange(-500, 500)
        self._place_x_spin.setValue(10.0)
        self._place_x_spin.setSuffix(" mm")
        plf.addRow("Pozycja X:", self._place_x_spin)
        self._place_y_spin = QDoubleSpinBox()
        self._place_y_spin.setRange(-500, 500)
        self._place_y_spin.setValue(10.0)
        self._place_y_spin.setSuffix(" mm")
        plf.addRow("Pozycja Y:", self._place_y_spin)
        layout.addWidget(place_box)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("✔ Dodaj do projektu")
        btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)
        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_preset_changed(self) -> None:
        key = _PACKAGE_PRESETS.get(self._preset_combo.currentText(), "passive")
        is_passive = "passive" in key
        self._size_combo.setEnabled(is_passive)
        self._update_preview()

    def _compute_pads(self) -> tuple[list[Pad], float, float]:
        """Return (pads, body_w, body_h) for current settings."""
        key = _PACKAGE_PRESETS.get(self._preset_combo.currentText(), "passive")
        n    = self._n_pins_spin.value()
        p    = self._pitch_spin.value()
        rs   = self._row_span_spin.value()
        body = self._body_spin.value()
        pw   = self._pad_w_spin.value()
        ph   = self._pad_h_spin.value()
        dr   = self._drill_spin.value()

        if key == "passive" or key == "custom_passive":
            size_str = self._size_combo.currentText()
            sp, _, spw, sph = _PASSIVE_SIZES.get(size_str, (1.0, 0.5, 0.5, 0.5))
            return gen_smd_passive(sp, spw, sph), sp * 0.5, sph

        if key in ("soic8",):  return gen_soic(8,  p, rs, pw, ph), rs * 0.3, 8  * p
        if key in ("soic14",): return gen_soic(14, p, rs, pw, ph), rs * 0.3, 14 * p / 2
        if key in ("soic16",): return gen_soic(16, p, rs, pw, ph), rs * 0.3, 16 * p / 2
        if key in ("soic20",): return gen_soic(20, p, rs, pw, ph), rs * 0.3, 20 * p / 2
        if key in ("tssop8",): return gen_soic(8,  0.65, 4.4, 0.3, 1.1), 4.4 * 0.3, 8 * 0.65
        if key in ("tssop16",):return gen_soic(16, 0.65, 4.4, 0.3, 1.1), 4.4 * 0.3, 16 * 0.65 / 2
        if key in ("qfp32",):  return gen_qfp(32, p, body, pw, ph), body, body
        if key in ("qfp44",):  return gen_qfp(44, p, body, pw, ph), body, body
        if key in ("qfp64",):  return gen_qfp(64, p, body, pw, ph), body, body
        if key in ("qfp100",): return gen_qfp(100,p, body, pw, ph), body, body
        if key in ("qfn16",):  return gen_qfn(16, p, body, pw, ph, self._thermal_cb.isChecked()), body, body
        if key in ("qfn32",):  return gen_qfn(32, p, body, pw, ph, self._thermal_cb.isChecked()), body, body
        if key in ("qfn48",):  return gen_qfn(48, p, body, pw, ph, self._thermal_cb.isChecked()), body, body
        if key in ("sot23_3",):return gen_sot23(3), 1.4, 2.9
        if key in ("sot23_5",):return gen_sot23(5), 1.7, 3.0
        if key in ("dip8",):   return gen_dip(8,  2.54, rs, dr, dr + 0.8), rs * 0.3, 8 * 2.54 / 2
        if key in ("dip14",):  return gen_dip(14, 2.54, rs, dr, dr + 0.8), rs * 0.3, 14 * 2.54 / 2
        if key in ("dip16",):  return gen_dip(16, 2.54, rs, dr, dr + 0.8), rs * 0.3, 16 * 2.54 / 2
        if key in ("dip20",):  return gen_dip(20, 2.54, rs, dr, dr + 0.8), rs * 0.3, 20 * 2.54 / 2
        if key in ("dip28",):  return gen_dip(28, 2.54, rs, dr, dr + 0.8), rs * 0.3, 28 * 2.54 / 2
        if key == "to92":      return gen_to92(dr), 2.4, 2.4
        if key == "custom_qfp":  return gen_qfp(n,  p, body, pw, ph), body, body
        if key == "custom_soic": return gen_soic(n, p, rs,   pw, ph), rs * 0.3, n * p / 2
        if key == "custom_dip":  return gen_dip(n, p, rs, dr, dr + 0.8), rs * 0.3, n * p / 2

        return gen_smd_passive(1.0, 0.5, 0.5), 1.0, 0.5

    def _update_preview(self) -> None:
        try:
            pads, bw, bh = self._compute_pads()
        except Exception:
            return
        self._pads = pads
        self._preview.set_pads(pads, bw, bh)
        n_tht = sum(1 for pad in pads if pad.drill > 0)
        n_smd = len(pads) - n_tht
        self._info_label.setText(
            f"Pady: {len(pads)}  (SMD: {n_smd}, THT: {n_tht})  |  "
            f"Ciało: {bw:.2f}×{bh:.2f} mm"
        )

    def _apply(self) -> None:
        if not self._pads:
            QMessageBox.warning(self, "Brak padów", "Wygeneruj footprint przed dodaniem.")
            return
        board = self._project.board if self._project else None
        if not board:
            QMessageBox.warning(self, "Błąd", "Brak płytki PCB w projekcie.")
            return

        ref = self._ref_edit.text().strip() or "U?"
        # Ensure unique ref
        existing = {c.reference for c in board.components}
        base_ref = ref
        counter = 1
        while ref in existing:
            ref = f"{base_ref}_{counter}"
            counter += 1

        pkg_name = self._preset_combo.currentText()
        comp = Component(
            reference=ref,
            value=self._val_edit.text() or pkg_name,
            footprint=f"Custom:{pkg_name.replace(' ', '_')}",
            x=self._place_x_spin.value(),
            y=self._place_y_spin.value(),
            description=self._desc_edit.text(),
        )
        # Translate pad positions by component origin
        comp.pads = self._pads

        board.components.append(comp)
        QMessageBox.information(
            self, "Dodano",
            f"Komponent {ref} ({len(self._pads)} padów) dodany do projektu."
        )
        self.accept()
