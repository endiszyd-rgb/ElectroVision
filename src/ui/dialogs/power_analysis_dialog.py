"""Power Analysis Dialog — power rail detection, current budget, decoupling checks."""
from __future__ import annotations
import re
from collections import defaultdict
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QWidget, QTabWidget, QComboBox, QFileDialog,
    QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project
from src.core.models.component import Component


# ── Power keywords ─────────────────────────────────────────────────────────────

_POWER_NET_RE = re.compile(
    r"(VCC|VDD|VIN|V\+|VBUS|VBAT|VCC_\w+|VDD_\w+|"
    r"3\.?3V?|5V?|12V?|1\.?8V?|2\.?5V?|24V?|48V?)",
    re.IGNORECASE,
)
_GND_NET_RE = re.compile(r"(GND|AGND|DGND|PGND|0V|VSS)", re.IGNORECASE)

# Estimated quiescent/typical current draw in mA per component type / keyword
_CURRENT_DB: list[tuple[str, float]] = [
    ("ESP32", 240), ("ESP8266", 80), ("STM32", 50), ("ATMEGA", 40),
    ("ATTINY", 5), ("RASPBERRYPI", 300), ("RP2040", 50),
    ("NRF52", 8), ("BLE", 15), ("WIFI", 120), ("LTE", 400),
    ("L298", 500), ("DRV8825", 150), ("TB6612", 200),
    ("LED", 20), ("OLED", 25), ("LCD", 80), ("TFT", 60),
    ("MOTOR", 500), ("SERVO", 200), ("FAN", 300),
    ("LM317", 5), ("LM7805", 5), ("LDO", 3), ("REG", 3), ("VREG", 3),
    ("AMS1117", 3), ("AP2112", 2), ("MIC5219", 2),
    ("OPAMP", 5), ("OP-AMP", 5), ("LM358", 3), ("LM741", 3),
    ("CAN", 40), ("RS485", 15), ("SPI", 5), ("I2C", 2),
    ("GATE", 2), ("NAND", 1), ("NOR", 1), ("BUFFER", 1),
    ("SSD1306", 10), ("MPU6050", 4), ("BMP280", 0.5),
]

_COMPONENT_DEFAULT_MA: dict[str, float] = {
    "ic": 20.0,
    "led": 20.0,
    "transistor": 2.0,
    "diode": 5.0,
    "crystal": 0.2,
    "connector": 0.5,
    "resistor": 0.0,
    "capacitor": 0.0,
    "inductor": 0.0,
    "switch": 0.1,
    "fuse": 0.0,
    "generic": 5.0,
}


def _estimate_current_ma(comp: Component) -> float:
    haystack = f"{comp.reference} {comp.value} {comp.footprint}".upper()
    for keyword, ma in _CURRENT_DB:
        if keyword in haystack:
            return ma
    return _COMPONENT_DEFAULT_MA.get(comp.component_type, 5.0)


def _is_power_net(name: str) -> bool:
    return bool(_POWER_NET_RE.search(name))


def _is_gnd_net(name: str) -> bool:
    return bool(_GND_NET_RE.search(name))


def _net_voltage(name: str) -> Optional[float]:
    m = re.search(r"(\d+\.?\d*)V", name, re.IGNORECASE)
    if m:
        return float(m.group(1))
    if "VCC" in name.upper() or "VDD" in name.upper():
        return 3.3
    if "VBUS" in name.upper():
        return 5.0
    if "VBAT" in name.upper():
        return 3.7
    return None


# ── Analysis engine ────────────────────────────────────────────────────────────

class PowerRail:
    def __init__(self, name: str):
        self.name = name
        self.voltage = _net_voltage(name)
        self.components: list[Component] = []
        self.total_ma: float = 0.0

    @property
    def total_mw(self) -> float:
        if self.voltage:
            return self.total_ma * self.voltage
        return 0.0


def analyze_power(board) -> tuple[list[PowerRail], list[str]]:
    """Return (rails, warnings) from a PCBBoard."""
    rails_map: dict[str, PowerRail] = {}
    comp_nets: dict[str, set[str]] = defaultdict(set)

    for comp in board.components:
        for pad in comp.pads:
            if pad.net_name:
                comp_nets[comp.reference].add(pad.net_name)

    for comp in board.components:
        nets = comp_nets.get(comp.reference, set())
        for net in nets:
            if _is_power_net(net):
                if net not in rails_map:
                    rails_map[net] = PowerRail(net)
                rail = rails_map[net]
                if comp not in rail.components:
                    rail.components.append(comp)
                    rail.total_ma += _estimate_current_ma(comp)

    warnings: list[str] = []

    # Warn: rails with no decoupling caps
    cap_refs = {c.reference for c in board.components if c.component_type == "capacitor"}
    for rail in rails_map.values():
        ics = [c for c in rail.components if c.component_type == "ic"]
        if ics and not any(c.component_type == "capacitor" for c in rail.components):
            warnings.append(
                f"Rail {rail.name}: brak kondensatorów blokujących przy IC "
                f"({', '.join(c.reference for c in ics)})"
            )

    # Warn: heavy rails with no bulk cap
    for rail in rails_map.values():
        if rail.total_ma > 200:
            bulk_caps = [c for c in rail.components
                         if c.component_type == "capacitor"
                         and _parse_capacitance_uf(c.value) >= 10.0]
            if not bulk_caps:
                warnings.append(
                    f"Rail {rail.name}: {rail.total_ma:.0f} mA — brak kondensatora bulk (>=10 µF)"
                )

    # Warn: very high consumption
    for rail in rails_map.values():
        if rail.total_ma > 2000:
            warnings.append(
                f"Rail {rail.name}: szacowane {rail.total_ma:.0f} mA — "
                "rozważ zasilacz dedykowany lub plane miedzi"
            )

    return list(rails_map.values()), warnings


def _parse_capacitance_uf(value: str) -> float:
    v = value.strip().upper()
    m = re.match(r"([\d.]+)\s*([NMUPF]*F?)", v)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2)
    if "UF" in unit or unit == "U":
        return num
    if "MF" in unit or unit == "M":
        return num * 1e6
    if "NF" in unit or unit == "N":
        return num / 1000.0
    if "PF" in unit or unit == "P":
        return num / 1e6
    return num


# ── Dialog ─────────────────────────────────────────────────────────────────────

class PowerAnalysisDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Analiza zasilania PCB")
        self.resize(900, 650)
        self._rails: list[PowerRail] = []
        self._warnings: list[str] = []
        self._build_ui()
        self._run_analysis()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        btn_reanalyze = QPushButton("🔄 Przelicz")
        btn_reanalyze.clicked.connect(self._run_analysis)
        toolbar.addWidget(btn_reanalyze)

        toolbar.addStretch()

        btn_export = QPushButton("📄 Eksportuj raport")
        btn_export.clicked.connect(self._export_report)
        toolbar.addWidget(btn_export)

        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        toolbar.addWidget(btn_close)
        layout.addLayout(toolbar)

        # ── Tabs ──────────────────────────────────────────────────────────────
        tabs = QTabWidget()

        # Tab 1: Rails overview
        rails_widget = QWidget()
        rails_layout = QVBoxLayout(rails_widget)

        self._rails_table = QTableWidget()
        self._rails_table.setColumnCount(6)
        self._rails_table.setHorizontalHeaderLabels([
            "Sieć zasilania", "Napięcie (V)", "Prąd (mA)", "Moc (mW)",
            "Komponenty", "Stan"
        ])
        self._rails_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._rails_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._rails_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._rails_table.itemSelectionChanged.connect(self._on_rail_selected)
        rails_layout.addWidget(self._rails_table)

        # Summary labels
        summary_box = QGroupBox("Podsumowanie budżetu mocy")
        summary_lyt = QVBoxLayout(summary_box)
        self._summary_label = QLabel("Brak danych")
        self._summary_label.setWordWrap(True)
        self._summary_label.setFont(QFont("Consolas", 9))
        summary_lyt.addWidget(self._summary_label)
        rails_layout.addWidget(summary_box)

        tabs.addTab(rails_widget, "Szyny zasilania")

        # Tab 2: Component detail
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)

        self._detail_label = QLabel("Wybierz sieć zasilania z listy po lewej")
        self._detail_label.setStyleSheet("color: #888;")
        detail_layout.addWidget(self._detail_label)

        self._detail_table = QTableWidget()
        self._detail_table.setColumnCount(5)
        self._detail_table.setHorizontalHeaderLabels([
            "Ref", "Wartość", "Typ", "Szac. prąd (mA)", "Footprint"
        ])
        self._detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        detail_layout.addWidget(self._detail_table)

        tabs.addTab(detail_widget, "Detale komponentów")

        # Tab 3: Warnings
        warn_widget = QWidget()
        warn_lyt = QVBoxLayout(warn_widget)
        self._warn_label = QLabel("Ostrzeżenia i zalecenia")
        warn_lyt.addWidget(self._warn_label)
        self._warn_text = QTextEdit()
        self._warn_text.setReadOnly(True)
        self._warn_text.setFont(QFont("Consolas", 9))
        warn_lyt.addWidget(self._warn_text)
        tabs.addTab(warn_widget, "Ostrzeżenia")

        # Tab 4: Recommendations
        rec_widget = QWidget()
        rec_lyt = QVBoxLayout(rec_widget)
        self._rec_text = QTextEdit()
        self._rec_text.setReadOnly(True)
        self._rec_text.setFont(QFont("Consolas", 9))
        rec_lyt.addWidget(self._rec_text)
        tabs.addTab(rec_widget, "Zalecenia projektowe")

        layout.addWidget(tabs)
        self._tabs = tabs

    def _run_analysis(self) -> None:
        board = self._project.board if self._project else None
        if not board or not board.components:
            self._summary_label.setText("Brak płytki PCB lub komponentów w projekcie.")
            return

        self._rails, self._warnings = analyze_power(board)
        self._populate_rails_table()
        self._populate_warnings()
        self._populate_recommendations()
        self._populate_summary()

    def _populate_rails_table(self) -> None:
        self._rails_table.setRowCount(0)
        for rail in sorted(self._rails, key=lambda r: -r.total_ma):
            row = self._rails_table.rowCount()
            self._rails_table.insertRow(row)

            self._rails_table.setItem(row, 0, QTableWidgetItem(rail.name))
            v_str = f"{rail.voltage:.1f}" if rail.voltage else "?"
            self._rails_table.setItem(row, 1, QTableWidgetItem(v_str))
            self._rails_table.setItem(row, 2, QTableWidgetItem(f"{rail.total_ma:.1f}"))
            self._rails_table.setItem(row, 3, QTableWidgetItem(f"{rail.total_mw:.0f}"))
            self._rails_table.setItem(row, 4, QTableWidgetItem(str(len(rail.components))))

            status = "OK"
            color = QColor("#2d6a2d")
            if rail.total_ma > 2000:
                status = "KRYTYCZNY"
                color = QColor("#8b0000")
            elif rail.total_ma > 500:
                status = "Wysoki prąd"
                color = QColor("#7a4d00")
            elif not rail.voltage:
                status = "Nieznane V"
                color = QColor("#444")

            status_item = QTableWidgetItem(status)
            status_item.setBackground(QBrush(color))
            self._rails_table.setItem(row, 5, status_item)

    def _on_rail_selected(self) -> None:
        row = self._rails_table.currentRow()
        if row < 0 or row >= len(self._rails):
            return
        sorted_rails = sorted(self._rails, key=lambda r: -r.total_ma)
        rail = sorted_rails[row]

        self._detail_label.setText(
            f"Sieć: <b>{rail.name}</b>  |  "
            f"Prąd: <b>{rail.total_ma:.1f} mA</b>  |  "
            f"Moc: <b>{rail.total_mw:.0f} mW</b>"
        )
        self._detail_label.setTextFormat(Qt.RichText)

        self._detail_table.setRowCount(0)
        for comp in sorted(rail.components, key=lambda c: c.reference):
            r = self._detail_table.rowCount()
            self._detail_table.insertRow(r)
            ma = _estimate_current_ma(comp)
            self._detail_table.setItem(r, 0, QTableWidgetItem(comp.reference))
            self._detail_table.setItem(r, 1, QTableWidgetItem(comp.value))
            self._detail_table.setItem(r, 2, QTableWidgetItem(comp.component_type))
            self._detail_table.setItem(r, 3, QTableWidgetItem(f"{ma:.1f}"))
            fp = comp.footprint.split(":")[-1] if ":" in comp.footprint else comp.footprint
            self._detail_table.setItem(r, 4, QTableWidgetItem(fp))

        self._tabs.setCurrentIndex(1)

    def _populate_warnings(self) -> None:
        if not self._warnings:
            self._warn_text.setPlainText("Brak ostrzeżeń. Projekt wygląda poprawnie pod kątem zasilania.")
            self._tabs.setTabText(2, "Ostrzeżenia (0)")
            return

        self._tabs.setTabText(2, f"Ostrzeżenia ({len(self._warnings)})")
        lines = []
        for i, w in enumerate(self._warnings, 1):
            lines.append(f"[{i}] {w}")
        self._warn_text.setPlainText("\n\n".join(lines))

    def _populate_recommendations(self) -> None:
        lines = ["=== ZALECENIA PROJEKTOWE — ZASILANIE ===\n"]

        total_ma = sum(r.total_ma for r in self._rails)
        total_mw = sum(r.total_mw for r in self._rails)
        lines.append(f"Łączny szacowany pobór prądu: {total_ma:.0f} mA ({total_mw/1000:.2f} W)")
        lines.append("")

        for rail in sorted(self._rails, key=lambda r: -r.total_ma):
            lines.append(f"--- Rail: {rail.name} ---")
            v_str = f"{rail.voltage:.1f}V" if rail.voltage else "V=?"
            lines.append(f"  Napięcie: {v_str}")
            lines.append(f"  Prąd: {rail.total_ma:.0f} mA")

            if rail.total_ma > 0:
                # Regulator recommendation
                if rail.total_ma < 100:
                    lines.append(f"  Regulator: LDO 100 mA (np. AMS1117-{v_str}, MIC5219)")
                elif rail.total_ma < 500:
                    lines.append(f"  Regulator: LDO 500 mA / 1A (np. AP2112K, XC6210)")
                elif rail.total_ma < 1500:
                    lines.append(f"  Regulator: LDO 2A lub buck converter (np. LM2596, MP1584)")
                else:
                    lines.append(f"  Regulator: Buck converter 3A+ (np. MP2307, LM25116)")

                # Decoupling cap recommendation (100nF per IC)
                ic_count = sum(1 for c in rail.components if c.component_type == "ic")
                if ic_count:
                    lines.append(f"  Kond. blok.: {ic_count}× 100nF (0402/0603) — po 1 przy każdym IC")

                # Bulk cap recommendation
                bulk_uf = max(10, round(rail.total_ma / 10))
                lines.append(f"  Kond. bulk: {bulk_uf} µF (elektrolityczny lub MLCC 6V3+)")

                # Trace width
                # IPC-2221: w = (I / (k * dT^0.44))^(1/0.725) / (1.378 * t)
                # simplified: ~0.5 mm per Amp for external, 1 mm per Amp for internal
                w_mm = rail.total_ma / 1000.0 * 0.5
                if w_mm < 0.2:
                    w_mm = 0.2
                lines.append(f"  Min. szer. ścieżki: {w_mm:.2f} mm (zewnętrzna, dT=10°C, t=35µm)")

            lines.append("")

        self._rec_text.setPlainText("\n".join(lines))

    def _populate_summary(self) -> None:
        if not self._rails:
            self._summary_label.setText("Brak sieci zasilania wykrytych w projekcie.")
            return

        total_ma = sum(r.total_ma for r in self._rails)
        total_mw = sum(r.total_mw for r in self._rails)
        rail_count = len(self._rails)
        warn_count = len(self._warnings)

        summary = (
            f"Wykryte szyny zasilania: <b>{rail_count}</b>  |  "
            f"Łączny prąd: <b>{total_ma:.0f} mA</b>  |  "
            f"Łączna moc: <b>{total_mw/1000:.2f} W</b>  |  "
            f"Ostrzeżenia: <b style='color:{'#f44' if warn_count else '#4f4'};'>{warn_count}</b>"
        )
        self._summary_label.setText(summary)
        self._summary_label.setTextFormat(Qt.RichText)

    def _export_report(self) -> None:
        if not self._rails:
            QMessageBox.warning(self, "Eksport", "Brak danych do eksportu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj raport zasilania",
            f"{self._project.name}_power_analysis.txt", "Tekst (*.txt)"
        )
        if not path:
            return
        lines = ["RAPORT ANALIZY ZASILANIA — ElectroVision", "=" * 50, ""]
        for rail in sorted(self._rails, key=lambda r: -r.total_ma):
            v = f"{rail.voltage:.1f}V" if rail.voltage else "V=?"
            lines.append(f"Rail: {rail.name}  ({v})")
            lines.append(f"  Prąd:     {rail.total_ma:.1f} mA")
            lines.append(f"  Moc:      {rail.total_mw:.0f} mW")
            lines.append(f"  Komp.:    {len(rail.components)}")
            for comp in sorted(rail.components, key=lambda c: c.reference):
                ma = _estimate_current_ma(comp)
                lines.append(f"    - {comp.reference:8s}  {comp.value:12s}  {ma:.1f} mA")
            lines.append("")
        if self._warnings:
            lines.append("OSTRZEŻENIA:")
            for w in self._warnings:
                lines.append(f"  ! {w}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Eksport", f"Raport zapisany:\n{path}")
