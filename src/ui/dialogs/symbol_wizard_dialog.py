"""Schematic Symbol Generator — kreator symboli KiCad 7 (.kicad_sym)."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QComboBox, QLineEdit, QSplitter, QWidget,
    QMessageBox, QFileDialog, QCheckBox, QSpinBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QFontMetricsF, QPolygonF
)

from src.core.project import Project


# ── Model pinu ──────────────────────────────────────────────────────────────────

PIN_TYPES = [
    "input", "output", "bidirectional", "tristate",
    "passive", "power_in", "power_out", "open_collector",
    "no_connect", "unspecified",
]
PIN_TYPE_SHORT = {
    "input":          "I",
    "output":         "O",
    "bidirectional":  "B",
    "tristate":       "T",
    "passive":        "P",
    "power_in":       "W",
    "power_out":      "w",
    "open_collector": "C",
    "no_connect":     "N",
    "unspecified":    "U",
}
PIN_TYPE_CLR = {
    "input":         "#4fa0e0",
    "output":        "#e06040",
    "bidirectional": "#80c060",
    "tristate":      "#c0a030",
    "passive":       "#aaaaaa",
    "power_in":      "#e04040",
    "power_out":     "#e04040",
    "open_collector":"#c06080",
    "no_connect":    "#888888",
    "unspecified":   "#888888",
}
SIDES = ["Lewy", "Prawy", "Górny", "Dolny"]
SIDE_CODE = {"Lewy": "L", "Prawy": "R", "Górny": "T", "Dolny": "B"}


@dataclass
class SymPin:
    number: str
    name: str
    pin_type: str = "passive"
    side: str = "Lewy"       # Lewy / Prawy / Górny / Dolny
    length_mm: float = 2.54

    def to_row(self) -> list[str]:
        return [self.number, self.name, self.pin_type, self.side, f"{self.length_mm:.2f}"]


@dataclass
class SymbolDef:
    name: str
    reference: str = "U"
    description: str = ""
    body_width_mm: float = 10.0
    body_height_mm: float = 5.0
    pins: list[SymPin] = field(default_factory=list)

    def auto_layout(self) -> None:
        """Rozdziela piny na strony wg typu."""
        left_types  = {"input", "power_in", "passive", "unspecified", "bidirectional"}
        right_types = {"output", "power_out", "tristate", "open_collector"}
        top_types   = {"power_in"}
        nc_types    = {"no_connect"}

        for pin in self.pins:
            if pin.pin_type in nc_types:
                pin.side = "Prawy"
            elif pin.name.upper() in ("VCC", "VDD", "AVDD", "DVDD", "V+", "3.3V", "5V"):
                pin.side = "Górny"
            elif pin.name.upper() in ("GND", "AGND", "PGND", "DGND", "VSS", "V-"):
                pin.side = "Dolny"
            elif pin.pin_type in right_types:
                pin.side = "Prawy"
            else:
                pin.side = "Lewy"


# ── Podgląd canvas ──────────────────────────────────────────────────────────────

class _SymPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sym: SymbolDef | None = None
        self.setMinimumSize(360, 300)
        self.setStyleSheet("background: #18181e;")

    def set_symbol(self, sym: SymbolDef) -> None:
        self._sym = sym
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self._sym:
            p.end()
            return

        sym = self._sym
        W, H = self.width(), self.height()

        # Group pins by side
        by_side: dict[str, list[SymPin]] = {s: [] for s in SIDES}
        for pin in sym.pins:
            by_side[pin.side].append(pin)

        PIN_LEN = 30        # px
        PIN_MARGIN = 20     # px between pins
        LABEL_PAD = 6       # px body padding

        n_left  = max(len(by_side["Lewy"]),  1)
        n_right = max(len(by_side["Prawy"]), 1)
        n_top   = max(len(by_side["Górny"]), 1)
        n_bot   = max(len(by_side["Dolny"]), 1)

        body_h = max(n_left, n_right) * PIN_MARGIN + PIN_MARGIN
        body_w = max(n_top, n_bot) * PIN_MARGIN + PIN_MARGIN

        bx = W / 2 - body_w / 2
        by = H / 2 - body_h / 2

        # Body
        p.setPen(QPen(QColor("#5080c0"), 2))
        p.setBrush(QBrush(QColor("#1e2a3a")))
        p.drawRect(QRectF(bx, by, body_w, body_h))

        # Component name
        fnt = QFont("Consolas", 9, QFont.Bold)
        p.setFont(fnt)
        p.setPen(QColor("#e0e0e0"))
        p.drawText(QRectF(bx, by, body_w, body_h), Qt.AlignCenter, sym.name)

        # Ref below name
        fnt2 = QFont("Consolas", 7)
        p.setFont(fnt2)
        p.setPen(QColor("#888"))
        p.drawText(QRectF(bx, by + body_h / 2 + 4, body_w, 16), Qt.AlignCenter,
                   sym.reference + "?")

        def draw_pins(pins: list[SymPin], side: str) -> None:
            n = len(pins)
            if n == 0:
                return
            fnt_p = QFont("Consolas", 7)
            p.setFont(fnt_p)
            for i, pin in enumerate(pins):
                clr = QColor(PIN_TYPE_CLR.get(pin.pin_type, "#aaa"))
                p.setPen(QPen(clr, 1.5))
                if side == "Lewy":
                    step = body_h / (n + 1)
                    px1 = bx
                    py1 = by + step * (i + 1)
                    px2 = bx - PIN_LEN
                    py2 = py1
                    p.drawLine(QPointF(px1, py1), QPointF(px2, py2))
                    p.setPen(QColor("#cccccc"))
                    p.drawText(QRectF(px1 + 3, py1 - 8, body_w / 2 - 6, 14),
                               Qt.AlignLeft | Qt.AlignVCenter, pin.name)
                    p.setPen(QColor("#666"))
                    p.drawText(QRectF(px2 - 26, py2 - 7, 24, 14),
                               Qt.AlignRight | Qt.AlignVCenter, pin.number)
                elif side == "Prawy":
                    step = body_h / (n + 1)
                    px1 = bx + body_w
                    py1 = by + step * (i + 1)
                    px2 = px1 + PIN_LEN
                    py2 = py1
                    p.drawLine(QPointF(px1, py1), QPointF(px2, py2))
                    p.setPen(QColor("#cccccc"))
                    p.drawText(QRectF(px1 - body_w / 2 + 3, py1 - 8, body_w / 2 - 6, 14),
                               Qt.AlignRight | Qt.AlignVCenter, pin.name)
                    p.setPen(QColor("#666"))
                    p.drawText(QRectF(px2 + 2, py2 - 7, 26, 14),
                               Qt.AlignLeft | Qt.AlignVCenter, pin.number)
                elif side == "Górny":
                    step = body_w / (n + 1)
                    px1 = bx + step * (i + 1)
                    py1 = by
                    px2 = px1
                    py2 = py1 - PIN_LEN
                    p.drawLine(QPointF(px1, py1), QPointF(px2, py2))
                    p.setPen(QColor("#cccccc"))
                    p.save()
                    p.translate(px2, py2 - 4)
                    p.rotate(-90)
                    p.drawText(QRectF(0, -8, 50, 14), Qt.AlignLeft | Qt.AlignVCenter, pin.name)
                    p.restore()
                elif side == "Dolny":
                    step = body_w / (n + 1)
                    px1 = bx + step * (i + 1)
                    py1 = by + body_h
                    px2 = px1
                    py2 = py1 + PIN_LEN
                    p.drawLine(QPointF(px1, py1), QPointF(px2, py2))
                    p.setPen(QColor("#cccccc"))
                    p.save()
                    p.translate(px2, py2 + 4)
                    p.rotate(90)
                    p.drawText(QRectF(0, -8, 50, 14), Qt.AlignLeft | Qt.AlignVCenter, pin.name)
                    p.restore()

        draw_pins(by_side["Lewy"],   "Lewy")
        draw_pins(by_side["Prawy"],  "Prawy")
        draw_pins(by_side["Górny"],  "Górny")
        draw_pins(by_side["Dolny"],  "Dolny")

        p.end()


# ── KiCad 7 .kicad_sym eksport ──────────────────────────────────────────────────

def _kicad_pin_type(pt: str) -> str:
    mapping = {
        "input":          "input",
        "output":         "output",
        "bidirectional":  "bidirectional",
        "tristate":       "tri_state",
        "passive":        "passive",
        "power_in":       "power_in",
        "power_out":      "power_out",
        "open_collector": "open_collector",
        "no_connect":     "no_connect",
        "unspecified":    "unspecified",
    }
    return mapping.get(pt, "unspecified")


def export_kicad_sym(sym: SymbolDef) -> str:
    """Generuje zawartość pliku .kicad_sym (KiCad 7 format)."""
    MIL = 2.54  # 1 grid unit = 2.54 mm = 100 mil

    def mm(v: float) -> str:
        return f"{v:.2f}"

    # Assign positions to pins
    by_side: dict[str, list[SymPin]] = {s: [] for s in SIDES}
    for pin in sym.pins:
        by_side[pin.side].append(pin)

    body_w = sym.body_width_mm
    body_h = sym.body_height_mm

    bx = -body_w / 2
    by = -body_h / 2

    lines = []
    lines.append(f'(kicad_symbol_lib (version 20231120) (generator "electrovision")')
    lines.append(f'  (symbol "{sym.name}"')
    lines.append(f'    (pin_names (offset 1.016))')
    lines.append(f'    (in_bom yes) (on_board yes)')

    # Symbol unit 1
    lines.append(f'    (symbol "{sym.name}_0_1"')
    # Body rectangle
    lines.append(
        f'      (rectangle (start {mm(bx)} {mm(-by)}) (end {mm(bx+body_w)} {mm(-by-body_h)})'
    )
    lines.append(
        f'        (stroke (width 0) (type default))'
    )
    lines.append(
        f'        (fill (type background))'
    )
    lines.append(f'      )')

    # Reference and value properties
    lines.append(f'    )')
    lines.append(f'    (symbol "{sym.name}_1_1"')

    # Pins
    def pin_at(side: str, i: int, n: int) -> tuple[float, float, float]:
        """Returns (x, y, angle_deg) for pin endpoint (outside body)."""
        if side == "Lewy":
            step = body_h / (n + 1)
            y = by + body_h - step * (i + 1)
            return (bx - sym.pins[0].length_mm, y, 0)
        elif side == "Prawy":
            step = body_h / (n + 1)
            y = by + body_h - step * (i + 1)
            return (bx + body_w + sym.pins[0].length_mm, y, 180)
        elif side == "Górny":
            step = body_w / (n + 1)
            x = bx + step * (i + 1)
            return (x, -by + sym.pins[0].length_mm, 270)
        else:  # Dolny
            step = body_w / (n + 1)
            x = bx + step * (i + 1)
            return (x, -by - body_h - sym.pins[0].length_mm, 90)

    for side in SIDES:
        pins = by_side[side]
        for i, pin in enumerate(pins):
            px, py, angle = pin_at(side, i, len(pins))
            ktype = _kicad_pin_type(pin.pin_type)
            lines.append(
                f'      (pin {ktype} line'
                f' (at {mm(px)} {mm(py)} {angle})'
                f' (length {mm(pin.length_mm)})'
            )
            lines.append(f'        (name "{pin.name}" (effects (font (size 1.27 1.27))))')
            lines.append(f'        (number "{pin.number}" (effects (font (size 1.27 1.27))))')
            lines.append(f'      )')

    lines.append(f'    )')

    # Properties
    lines.append(
        f'    (property "Reference" "{sym.reference}"'
        f' (at {mm(bx + body_w/2)} {mm(-by + 2)} 0)'
        f' (effects (font (size 1.27 1.27))))'
    )
    lines.append(
        f'    (property "Value" "{sym.name}"'
        f' (at {mm(bx + body_w/2)} {mm(-by - body_h - 2)} 0)'
        f' (effects (font (size 1.27 1.27))))'
    )
    lines.append(
        f'    (property "Footprint" ""'
        f' (at 0 0 0)'
        f' (effects (font (size 1.27 1.27)) hide))'
    )
    lines.append(
        f'    (property "Description" "{sym.description}"'
        f' (at 0 0 0)'
        f' (effects (font (size 1.27 1.27)) hide))'
    )

    lines.append(f'  )')  # symbol
    lines.append(f')')    # library

    return "\n".join(lines)


# ── Gotowe presety ───────────────────────────────────────────────────────────────

def _preset_opamp() -> SymbolDef:
    s = SymbolDef(name="OPAMP", reference="U", description="Wzmacniacz operacyjny")
    s.pins = [
        SymPin("1", "IN-", "input",    "Lewy"),
        SymPin("2", "IN+", "input",    "Lewy"),
        SymPin("3", "V+",  "power_in", "Górny"),
        SymPin("4", "V-",  "power_in", "Dolny"),
        SymPin("5", "OUT", "output",   "Prawy"),
    ]
    return s


def _preset_nmos() -> SymbolDef:
    s = SymbolDef(name="NMOS", reference="Q", description="Tranzystor N-MOSFET")
    s.pins = [
        SymPin("1", "G", "input",   "Lewy"),
        SymPin("2", "D", "passive", "Górny"),
        SymPin("3", "S", "passive", "Dolny"),
    ]
    return s


def _preset_mcu8() -> SymbolDef:
    s = SymbolDef(name="MCU8", reference="U", description="Mikrokontroler 8-pin")
    s.pins = [
        SymPin("1",  "VCC",  "power_in",     "Górny"),
        SymPin("2",  "GND",  "power_in",     "Dolny"),
        SymPin("3",  "PA0",  "bidirectional","Lewy"),
        SymPin("4",  "PA1",  "bidirectional","Lewy"),
        SymPin("5",  "PA2",  "bidirectional","Lewy"),
        SymPin("6",  "PB0",  "bidirectional","Prawy"),
        SymPin("7",  "PB1",  "bidirectional","Prawy"),
        SymPin("8",  "NRST", "input",        "Prawy"),
    ]
    return s


def _preset_connector4() -> SymbolDef:
    s = SymbolDef(name="CONN4", reference="J", description="Złącze 4-pin")
    s.pins = [
        SymPin("1", "Pin1", "passive", "Lewy"),
        SymPin("2", "Pin2", "passive", "Lewy"),
        SymPin("3", "Pin3", "passive", "Lewy"),
        SymPin("4", "Pin4", "passive", "Lewy"),
    ]
    return s


PRESETS = {
    "Op-Amp (5 pin)":          _preset_opamp,
    "N-MOSFET (3 pin)":        _preset_nmos,
    "MCU 8-pin (GPIO)":        _preset_mcu8,
    "Złącze 4-pin":            _preset_connector4,
}


# ── Dialog ──────────────────────────────────────────────────────────────────────

COL_NUM  = 0
COL_NAME = 1
COL_TYPE = 2
COL_SIDE = 3
COL_LEN  = 4


class SymbolWizardDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._sym = SymbolDef(name="NOWY_SYMBOL")
        self.setWindowTitle("Generator symboli schematycznych (.kicad_sym)")
        self.resize(1000, 640)
        self._build_ui()
        self._refresh_preview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: definition ─────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        # Preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItem("— własny —")
        self._preset_combo.addItems(list(PRESETS.keys()))
        self._preset_combo.currentIndexChanged.connect(self._load_preset)
        preset_row.addWidget(self._preset_combo, 1)
        ll.addLayout(preset_row)

        # Symbol meta
        meta_box = QGroupBox("Właściwości symbolu")
        mf = QFormLayout(meta_box)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("np. STM32F103, LM358, TLP785")
        self._name_edit.textChanged.connect(self._on_meta_changed)
        mf.addRow("Nazwa symbolu:", self._name_edit)

        self._ref_edit = QLineEdit("U")
        self._ref_edit.setMaximumWidth(80)
        self._ref_edit.textChanged.connect(self._on_meta_changed)
        mf.addRow("Prefiks ref.:", self._ref_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.textChanged.connect(self._on_meta_changed)
        mf.addRow("Opis:", self._desc_edit)

        self._bw_spin = QDoubleSpinBox()
        self._bw_spin.setRange(2.54, 100.0)
        self._bw_spin.setValue(10.0)
        self._bw_spin.setSuffix(" mm")
        self._bw_spin.setSingleStep(2.54)
        self._bw_spin.valueChanged.connect(self._on_meta_changed)
        mf.addRow("Szerokość korpusu:", self._bw_spin)

        self._bh_spin = QDoubleSpinBox()
        self._bh_spin.setRange(2.54, 100.0)
        self._bh_spin.setValue(5.0)
        self._bh_spin.setSuffix(" mm")
        self._bh_spin.setSingleStep(2.54)
        self._bh_spin.valueChanged.connect(self._on_meta_changed)
        mf.addRow("Wysokość korpusu:", self._bh_spin)

        ll.addWidget(meta_box)

        # Pin table
        ll.addWidget(QLabel("Piny:"))
        self._pin_table = QTableWidget()
        self._pin_table.setColumnCount(5)
        self._pin_table.setHorizontalHeaderLabels(["Nr", "Nazwa", "Typ", "Strona", "Dług. (mm)"])
        hdr = self._pin_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._pin_table.cellChanged.connect(self._on_pin_changed)
        ll.addWidget(self._pin_table, 1)

        pin_btns = QHBoxLayout()
        btn_add_pin = QPushButton("+ Pin")
        btn_add_pin.clicked.connect(self._add_pin)
        btn_del_pin = QPushButton("− Usuń")
        btn_del_pin.clicked.connect(self._del_pin)
        btn_auto = QPushButton("🔀 Auto-układ")
        btn_auto.clicked.connect(self._auto_layout)
        btn_bulk = QPushButton("➕ Wiele pinów…")
        btn_bulk.clicked.connect(self._bulk_add)
        pin_btns.addWidget(btn_add_pin)
        pin_btns.addWidget(btn_del_pin)
        pin_btns.addWidget(btn_auto)
        pin_btns.addWidget(btn_bulk)
        ll.addLayout(pin_btns)

        splitter.addWidget(left)

        # ── Right: preview ───────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        rl.addWidget(QLabel("Podgląd symbolu:"))
        self._preview = _SymPreview()
        rl.addWidget(self._preview, 1)

        # Legend
        legend = QGroupBox("Typy pinów")
        lf = QHBoxLayout(legend)
        for pt, clr in list(PIN_TYPE_CLR.items())[:5]:
            lbl = QLabel(f"■ {pt}")
            lbl.setStyleSheet(f"color: {clr}; font-size: 10px;")
            lf.addWidget(lbl)
        legend.setMaximumHeight(40)
        rl.addWidget(legend)

        splitter.addWidget(right)
        splitter.setSizes([420, 480])
        root.addWidget(splitter, 1)

        # ── Bottom ────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        btn_export = QPushButton("💾 Eksportuj .kicad_sym")
        btn_export.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 10px;")
        btn_export.clicked.connect(self._export_sym)
        bottom.addWidget(btn_export)
        bottom.addStretch()
        self._pin_count_lbl = QLabel()
        self._pin_count_lbl.setStyleSheet("color: #888; font-size: 10px;")
        bottom.addWidget(self._pin_count_lbl)
        bottom.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        self._loading = False

    # ── Presety ───────────────────────────────────────────────────────────────

    def _load_preset(self, idx: int) -> None:
        if idx == 0:
            return
        name = self._preset_combo.currentText()
        fn = PRESETS.get(name)
        if fn:
            self._sym = fn()
            self._load_sym_to_ui()
            self._refresh_preview()

    def _load_sym_to_ui(self) -> None:
        self._loading = True
        self._name_edit.setText(self._sym.name)
        self._ref_edit.setText(self._sym.reference)
        self._desc_edit.setText(self._sym.description)
        self._bw_spin.setValue(self._sym.body_width_mm)
        self._bh_spin.setValue(self._sym.body_height_mm)
        self._populate_pins()
        self._loading = False

    # ── Meta ─────────────────────────────────────────────────────────────────

    def _on_meta_changed(self) -> None:
        if self._loading:
            return
        self._sym.name = self._name_edit.text() or "SYMBOL"
        self._sym.reference = self._ref_edit.text() or "U"
        self._sym.description = self._desc_edit.text()
        self._sym.body_width_mm = self._bw_spin.value()
        self._sym.body_height_mm = self._bh_spin.value()
        self._refresh_preview()

    # ── Pins ─────────────────────────────────────────────────────────────────

    def _populate_pins(self) -> None:
        self._loading = True
        self._pin_table.setRowCount(0)
        for pin in self._sym.pins:
            self._add_pin_row(pin)
        self._loading = False

    def _add_pin_row(self, pin: SymPin) -> None:
        row = self._pin_table.rowCount()
        self._pin_table.insertRow(row)
        self._pin_table.setItem(row, COL_NUM, QTableWidgetItem(pin.number))
        self._pin_table.setItem(row, COL_NAME, QTableWidgetItem(pin.name))

        type_combo = QComboBox()
        type_combo.addItems(PIN_TYPES)
        type_combo.setCurrentText(pin.pin_type)
        type_combo.currentTextChanged.connect(self._on_combo_changed)
        self._pin_table.setCellWidget(row, COL_TYPE, type_combo)

        side_combo = QComboBox()
        side_combo.addItems(SIDES)
        side_combo.setCurrentText(pin.side)
        side_combo.currentTextChanged.connect(self._on_combo_changed)
        self._pin_table.setCellWidget(row, COL_SIDE, side_combo)

        self._pin_table.setItem(row, COL_LEN, QTableWidgetItem(f"{pin.length_mm:.2f}"))

    def _on_pin_changed(self, row: int, col: int) -> None:
        if self._loading:
            return
        self._sync_pins_from_table()
        self._refresh_preview()

    def _on_combo_changed(self) -> None:
        if not self._loading:
            self._sync_pins_from_table()
            self._refresh_preview()

    def _sync_pins_from_table(self) -> None:
        pins = []
        for row in range(self._pin_table.rowCount()):
            num_item  = self._pin_table.item(row, COL_NUM)
            name_item = self._pin_table.item(row, COL_NAME)
            len_item  = self._pin_table.item(row, COL_LEN)
            type_w = self._pin_table.cellWidget(row, COL_TYPE)
            side_w = self._pin_table.cellWidget(row, COL_SIDE)
            num   = num_item.text() if num_item else str(row + 1)
            name  = name_item.text() if name_item else f"P{row+1}"
            ptype = type_w.currentText() if type_w else "passive"
            side  = side_w.currentText() if side_w else "Lewy"
            try:
                length = float(len_item.text()) if len_item else 2.54
            except ValueError:
                length = 2.54
            pins.append(SymPin(number=num, name=name, pin_type=ptype, side=side, length_mm=length))
        self._sym.pins = pins

    def _add_pin(self) -> None:
        n = len(self._sym.pins) + 1
        pin = SymPin(number=str(n), name=f"P{n}")
        self._sym.pins.append(pin)
        self._loading = True
        self._add_pin_row(pin)
        self._loading = False
        self._refresh_preview()

    def _del_pin(self) -> None:
        row = self._pin_table.currentRow()
        if row < 0:
            return
        self._pin_table.removeRow(row)
        self._sync_pins_from_table()
        self._refresh_preview()

    def _auto_layout(self) -> None:
        self._sync_pins_from_table()
        self._sym.auto_layout()
        self._loading = True
        self._populate_pins()
        self._loading = False
        self._refresh_preview()

    def _bulk_add(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self, "Dodaj wiele pinów",
            "Format: NUMER NAZWA TYP STRONA (jeden pin na linię)\n"
            "Typ: input/output/bidirectional/passive/power_in/power_out/no_connect\n"
            "Strona: Lewy/Prawy/Górny/Dolny\n\nPrzykład:\n"
            "1 VCC power_in Górny\n2 GND power_in Dolny\n3 PA0 bidirectional Lewy\n4 OUT output Prawy",
            ""
        )
        if not ok or not text.strip():
            return
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            num   = parts[0]
            name  = parts[1]
            ptype = parts[2] if len(parts) > 2 else "passive"
            side  = parts[3] if len(parts) > 3 else "Lewy"
            if ptype not in PIN_TYPES:
                ptype = "passive"
            if side not in SIDES:
                side = "Lewy"
            pin = SymPin(number=num, name=name, pin_type=ptype, side=side)
            self._sym.pins.append(pin)
            self._loading = True
            self._add_pin_row(pin)
            self._loading = False
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._preview.set_symbol(self._sym)
        self._pin_count_lbl.setText(
            f"Pinów: {len(self._sym.pins)}  |  "
            f"L: {sum(1 for p in self._sym.pins if p.side=='Lewy')}  "
            f"P: {sum(1 for p in self._sym.pins if p.side=='Prawy')}  "
            f"G: {sum(1 for p in self._sym.pins if p.side=='Górny')}  "
            f"D: {sum(1 for p in self._sym.pins if p.side=='Dolny')}"
        )

    # ── Eksport ───────────────────────────────────────────────────────────────

    def _export_sym(self) -> None:
        self._sync_pins_from_table()
        if not self._sym.name:
            QMessageBox.warning(self, "Błąd", "Podaj nazwę symbolu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj symbol KiCad",
            f"{self._sym.name}.kicad_sym",
            "KiCad Symbol Library (*.kicad_sym)"
        )
        if not path:
            return
        content = export_kicad_sym(self._sym)
        Path(path).write_text(content, encoding="utf-8")
        QMessageBox.information(
            self, "Eksport",
            f"Symbol '{self._sym.name}' zapisany do:\n{path}\n\n"
            f"Piny: {len(self._sym.pins)}\n\n"
            "Otwórz plik w KiCad > Symbol Editor > File > Add Library, "
            "lub skopiuj do folderu bibliotek użytkownika."
        )
