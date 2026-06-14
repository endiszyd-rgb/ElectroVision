"""Thermal estimation dialog — junction temperature, heat dissipation per component."""
from __future__ import annotations
import re
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QDoubleSpinBox, QComboBox, QSplitter, QTextEdit, QWidget,
    QFormLayout, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project
from src.core.models.component import Component


# ── Thermal DB ────────────────────────────────────────────────────────────────

@dataclass
class ThermalSpec:
    theta_ja: float   # °C/W junction-to-ambient (package)
    power_w: float    # typical power dissipation W
    note: str = ""


_THERMAL_DB: list[tuple[str, ThermalSpec]] = [
    ("LM7805",   ThermalSpec(65, 1.0, "TO-220, bez radiatora")),
    ("LM317",    ThermalSpec(65, 0.8, "TO-220")),
    ("AMS1117",  ThermalSpec(178, 0.5, "SOT-223")),
    ("AP2112",   ThermalSpec(200, 0.3, "SOT-25")),
    ("L298",     ThermalSpec(50, 2.5, "Multiwatt, potrzebny radiator")),
    ("DRV8825",  ThermalSpec(28, 1.5, "HTSSOP-28")),
    ("TB6612",   ThermalSpec(45, 1.2, "SSOP-24")),
    ("ESP32",    ThermalSpec(35, 0.8, "QFN, z modułem")),
    ("STM32",    ThermalSpec(40, 0.5, "LQFP")),
    ("ATMEGA",   ThermalSpec(68, 0.3, "TQFP/DIP")),
    ("NRF52",    ThermalSpec(50, 0.1, "QFN")),
]

# Default theta_ja by package type inferred from footprint
_PACKAGE_THETA: dict[str, float] = {
    "QFN": 35.0, "BGA": 25.0, "LQFP": 40.0, "TQFP": 40.0,
    "SOT23": 300.0, "SOT223": 178.0, "SOT89": 130.0,
    "TO220": 65.0, "TO252": 80.0, "TO263": 70.0,
    "SOIC": 120.0, "DIP": 80.0, "SSOP": 80.0, "TSSOP": 100.0,
    "0402": 1000.0, "0603": 800.0, "0805": 600.0,
}


def _guess_theta_ja(comp: Component) -> float:
    haystack = f"{comp.value} {comp.footprint} {comp.reference}".upper()
    for keyword, spec in _THERMAL_DB:
        if keyword in haystack:
            return spec.theta_ja
    fp = comp.footprint.upper()
    for pkg, theta in _PACKAGE_THETA.items():
        if pkg in fp:
            return theta
    return 150.0  # generic small SMD


def _guess_power_w(comp: Component) -> float:
    from src.ui.dialogs.power_analysis_dialog import _estimate_current_ma, _net_voltage
    ma = _estimate_current_ma(comp)

    # Try to find supply voltage from any power pad
    v = 3.3
    for pad in comp.pads:
        if pad.net_name:
            vv = _net_voltage(pad.net_name)
            if vv:
                v = vv
                break
    return (ma / 1000.0) * v


def _parse_resistance_ohm(value: str) -> float:
    v = value.strip().upper()
    m = re.match(r"([\d.]+)\s*([KMGR]?)\s*Ω?", v)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "K":
        return num * 1e3
    if unit == "M":
        return num * 1e6
    if unit == "G":
        return num * 1e9
    return num


@dataclass
class ThermalResult:
    comp: Component
    theta_ja: float
    power_w: float
    t_ambient: float

    @property
    def t_junction(self) -> float:
        return self.t_ambient + self.theta_ja * self.power_w

    @property
    def status(self) -> str:
        tj = self.t_junction
        if tj > 150:
            return "KRYTYCZNY"
        if tj > 100:
            return "Wysoki"
        if tj > 70:
            return "Podwyższony"
        return "OK"

    @property
    def status_color(self) -> QColor:
        s = self.status
        if s == "KRYTYCZNY":
            return QColor("#8b0000")
        if s == "Wysoki":
            return QColor("#7a4d00")
        if s == "Podwyższony":
            return QColor("#4a5500")
        return QColor("#2d6a2d")


# ── Dialog ─────────────────────────────────────────────────────────────────────

class ThermalDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Estymacja termiczna PCB")
        self.resize(860, 600)
        self._results: list[ThermalResult] = []
        self._build_ui()
        self._run()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Params ────────────────────────────────────────────────────────────
        params_box = QGroupBox("Parametry środowiskowe")
        params_lyt = QFormLayout(params_box)

        self._t_amb_spin = QDoubleSpinBox()
        self._t_amb_spin.setRange(-40, 85)
        self._t_amb_spin.setValue(25.0)
        self._t_amb_spin.setSuffix(" °C")
        params_lyt.addRow("Temperatura otoczenia:", self._t_amb_spin)

        self._cooling_combo = QComboBox()
        self._cooling_combo.addItems([
            "Konwekcja naturalna (domyślnie)",
            "Przepływ powietrza 1 m/s (lekkie chłodzenie)",
            "Przepływ powietrza 2 m/s (wentylator)",
            "Plane miedziany (dodatkowe chłodzenie -20%)",
        ])
        params_lyt.addRow("Chłodzenie:", self._cooling_combo)

        btn_run = QPushButton("🔄 Przelicz")
        btn_run.clicked.connect(self._run)
        params_lyt.addRow("", btn_run)

        layout.addWidget(params_box)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Ref", "Wartość", "θ_JA (°C/W)", "P (mW)", "T_otoczenia", "T_złącza", "Stan"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table)

        # ── Notes ─────────────────────────────────────────────────────────────
        notes_box = QGroupBox("Wnioski i zalecenia")
        notes_lyt = QVBoxLayout(notes_box)
        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setFont(QFont("Consolas", 9))
        self._notes.setMaximumHeight(130)
        notes_lyt.addWidget(self._notes)
        layout.addWidget(notes_box)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_export = QPushButton("📄 Eksportuj")
        btn_export.clicked.connect(self._export)
        btn_row.addWidget(btn_export)
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _cooling_factor(self) -> float:
        idx = self._cooling_combo.currentIndex()
        return {0: 1.0, 1: 0.85, 2: 0.70, 3: 0.80}.get(idx, 1.0)

    def _run(self) -> None:
        board = self._project.board if self._project else None
        if not board or not board.components:
            self._notes.setPlainText("Brak płytki PCB lub komponentów w projekcie.")
            return

        t_amb = self._t_amb_spin.value()
        factor = self._cooling_factor()

        self._results = []
        for comp in board.components:
            if comp.component_type in ("resistor", "capacitor", "inductor",
                                       "connector", "fuse", "crystal"):
                pw = _guess_power_w(comp)
                if pw < 0.001:
                    continue
            theta = _guess_theta_ja(comp) * factor
            pw = _guess_power_w(comp)
            if pw < 0.001:
                continue
            self._results.append(ThermalResult(comp, theta, pw, t_amb))

        self._results.sort(key=lambda r: -r.t_junction)
        self._populate_table()
        self._generate_notes()

    def _populate_table(self) -> None:
        self._table.setRowCount(0)
        for res in self._results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(res.comp.reference))
            self._table.setItem(row, 1, QTableWidgetItem(res.comp.value))
            self._table.setItem(row, 2, QTableWidgetItem(f"{res.theta_ja:.0f}"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{res.power_w*1000:.0f}"))
            self._table.setItem(row, 4, QTableWidgetItem(f"{res.t_ambient:.0f} °C"))
            self._table.setItem(row, 5, QTableWidgetItem(f"{res.t_junction:.1f} °C"))
            status_item = QTableWidgetItem(res.status)
            status_item.setBackground(QBrush(res.status_color))
            self._table.setItem(row, 6, status_item)

    def _generate_notes(self) -> None:
        lines = []
        critical = [r for r in self._results if r.status == "KRYTYCZNY"]
        high = [r for r in self._results if r.status == "Wysoki"]

        if critical:
            lines.append(f"KRYTYCZNE ({len(critical)}):")
            for r in critical:
                lines.append(
                    f"  {r.comp.reference} ({r.comp.value}): T_j = {r.t_junction:.0f}°C "
                    f"— Wymagany radiator lub plane miedzi!"
                )
        if high:
            lines.append(f"Wysokie temperatury ({len(high)}):")
            for r in high:
                lines.append(
                    f"  {r.comp.reference}: T_j = {r.t_junction:.0f}°C "
                    f"— Rozważ lepsze chłodzenie lub odpowietrzenie obudowy."
                )
        if not critical and not high:
            lines.append("Wszystkie komponenty w normie termicznej (<100°C złącze).")

        max_tj = max((r.t_junction for r in self._results), default=0)
        lines.append(f"\nNajwyższa temperatura złącza: {max_tj:.1f}°C")
        lines.append("Uwaga: Wartości są szacunkowe. θ_JA może różnić się od rzeczywistego pakietu.")
        self._notes.setPlainText("\n".join(lines))

    def _export(self) -> None:
        if not self._results:
            QMessageBox.warning(self, "Eksport", "Brak danych.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj raport termiczny",
            f"{self._project.name}_thermal.txt", "Tekst (*.txt)"
        )
        if not path:
            return
        lines = ["RAPORT TERMICZNY — ElectroVision", "=" * 50, ""]
        for r in self._results:
            lines.append(
                f"{r.comp.reference:8s}  {r.comp.value:12s}  "
                f"θ_JA={r.theta_ja:.0f} °C/W  P={r.power_w*1000:.0f} mW  "
                f"T_j={r.t_junction:.1f}°C  [{r.status}]"
            )
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Eksport", f"Raport zapisany:\n{path}")
