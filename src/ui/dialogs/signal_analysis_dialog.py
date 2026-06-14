"""Signal Analysis Dialog — basic signal integrity checks for PCB traces."""
from __future__ import annotations
import math
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QDoubleSpinBox, QComboBox, QTextEdit, QFormLayout,
    QTabWidget, QWidget, QFileDialog, QMessageBox, QSlider
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF

from src.core.project import Project


# ── SI calculations ────────────────────────────────────────────────────────────

def calc_propagation_delay_ns_per_mm(er: float = 4.5) -> float:
    """Propagation delay in ns/mm for microstrip (Wadell approximation)."""
    # c = 3e8 m/s, effective er for microstrip
    c = 3e8  # m/s
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 * 1.0))
    return math.sqrt(er_eff) / c * 1e9 * 1e-3  # ns/mm


def calc_critical_length_mm(freq_mhz: float, er: float = 4.5) -> float:
    """Quarter-wave critical length above which termination is needed (mm)."""
    if freq_mhz <= 0:
        return float("inf")
    c = 3e8  # m/s
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 * 1.0))
    wavelength_m = c / (freq_mhz * 1e6 * math.sqrt(er_eff))
    return (wavelength_m / 4) * 1e3  # mm, lambda/4


def calc_rise_time_bandwidth_mhz(rise_time_ns: float) -> float:
    """Effective bandwidth from rise time: BW = 0.35 / Tr."""
    if rise_time_ns <= 0:
        return 0.0
    return 0.35 / (rise_time_ns * 1e-9) / 1e6  # MHz


def calc_crosstalk_db(
    trace_width_mm: float, trace_spacing_mm: float,
    trace_length_mm: float, freq_mhz: float
) -> float:
    """Rough NEXT/FEXT estimate in dB (simplified lumped model)."""
    if trace_spacing_mm <= 0:
        return 0.0
    # coupling coefficient k ~ W / (W + 2*S)
    k = trace_width_mm / (trace_width_mm + 2.0 * trace_spacing_mm)
    # NEXT ~ 20*log10(k * l * f / c_eff)
    c_eff = 3e8 / math.sqrt(4.5)
    coupling = k * (trace_length_mm * 1e-3) * (freq_mhz * 1e6) / c_eff
    if coupling <= 0:
        return -999.0
    return 20 * math.log10(coupling)


def calc_via_inductance_nh(via_height_mm: float, via_drill_mm: float) -> float:
    """Via inductance in nH (IPC-2141A approximation)."""
    h = via_height_mm
    d = via_drill_mm
    if d <= 0 or h <= 0:
        return 0.0
    return 5.08e-3 * h * (math.log(4 * h / d) + 1)  # nH


def calc_via_reactance_ohm(via_height_mm: float, via_drill_mm: float,
                            freq_mhz: float) -> float:
    L_nh = calc_via_inductance_nh(via_height_mm, via_drill_mm)
    return 2 * math.pi * freq_mhz * 1e6 * L_nh * 1e-9


# ── Dialog ─────────────────────────────────────────────────────────────────────

class SignalAnalysisDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Analiza sygnałowa / SI")
        self.resize(880, 640)
        self._build_ui()
        self._update_all()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        tabs = QTabWidget()

        # ── Tab 1: Propagation & Critical Length ─────────────────────────────
        prop_w = QWidget()
        prop_lyt = QVBoxLayout(prop_w)

        params_box = QGroupBox("Parametry sygnału i PCB")
        form = QFormLayout(params_box)

        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(0.1, 10000)
        self._freq_spin.setValue(100)
        self._freq_spin.setSuffix(" MHz")
        self._freq_spin.setDecimals(1)
        self._freq_spin.valueChanged.connect(self._update_all)
        form.addRow("Częstotliwość sygnału:", self._freq_spin)

        self._rise_spin = QDoubleSpinBox()
        self._rise_spin.setRange(0.01, 1000)
        self._rise_spin.setValue(1.0)
        self._rise_spin.setSuffix(" ns")
        self._rise_spin.setDecimals(2)
        self._rise_spin.valueChanged.connect(self._update_all)
        form.addRow("Czas narastania (10→90%):", self._rise_spin)

        self._er_spin = QDoubleSpinBox()
        self._er_spin.setRange(1.0, 15.0)
        self._er_spin.setValue(4.5)
        self._er_spin.setDecimals(1)
        self._er_spin.valueChanged.connect(self._update_all)
        form.addRow("Stała dielektryczna (εr):", self._er_spin)

        self._trace_len_spin = QDoubleSpinBox()
        self._trace_len_spin.setRange(0.1, 5000)
        self._trace_len_spin.setValue(50)
        self._trace_len_spin.setSuffix(" mm")
        self._trace_len_spin.valueChanged.connect(self._update_all)
        form.addRow("Długość ścieżki:", self._trace_len_spin)

        prop_lyt.addWidget(params_box)

        self._prop_result = QTextEdit()
        self._prop_result.setReadOnly(True)
        self._prop_result.setFont(QFont("Consolas", 9))
        prop_lyt.addWidget(self._prop_result)

        tabs.addTab(prop_w, "Propagacja / Krytyczna długość")

        # ── Tab 2: Crosstalk ──────────────────────────────────────────────────
        ct_w = QWidget()
        ct_lyt = QVBoxLayout(ct_w)

        ct_params = QGroupBox("Parametry par ścieżek")
        ct_form = QFormLayout(ct_params)

        self._ct_width = QDoubleSpinBox()
        self._ct_width.setRange(0.05, 10)
        self._ct_width.setValue(0.2)
        self._ct_width.setSuffix(" mm")
        self._ct_width.valueChanged.connect(self._update_all)
        ct_form.addRow("Szerokość ścieżki:", self._ct_width)

        self._ct_spacing = QDoubleSpinBox()
        self._ct_spacing.setRange(0.05, 50)
        self._ct_spacing.setValue(0.2)
        self._ct_spacing.setSuffix(" mm")
        self._ct_spacing.valueChanged.connect(self._update_all)
        ct_form.addRow("Odstęp między ścieżkami:", self._ct_spacing)

        self._ct_length = QDoubleSpinBox()
        self._ct_length.setRange(1, 2000)
        self._ct_length.setValue(50)
        self._ct_length.setSuffix(" mm")
        self._ct_length.valueChanged.connect(self._update_all)
        ct_form.addRow("Długość równoległego odcinka:", self._ct_length)

        ct_lyt.addWidget(ct_params)

        self._ct_result = QTextEdit()
        self._ct_result.setReadOnly(True)
        self._ct_result.setFont(QFont("Consolas", 9))
        ct_lyt.addWidget(self._ct_result)

        tabs.addTab(ct_w, "Przesłuch (Crosstalk)")

        # ── Tab 3: Via inductance ─────────────────────────────────────────────
        via_w = QWidget()
        via_lyt = QVBoxLayout(via_w)

        via_params = QGroupBox("Parametry przelotki (via)")
        via_form = QFormLayout(via_params)

        self._via_h = QDoubleSpinBox()
        self._via_h.setRange(0.1, 10)
        self._via_h.setValue(1.6)
        self._via_h.setSuffix(" mm")
        self._via_h.valueChanged.connect(self._update_all)
        via_form.addRow("Wysokość vii (grubość PCB):", self._via_h)

        self._via_d = QDoubleSpinBox()
        self._via_d.setRange(0.05, 3)
        self._via_d.setValue(0.3)
        self._via_d.setSuffix(" mm")
        self._via_d.valueChanged.connect(self._update_all)
        via_form.addRow("Średnica wiercenia:", self._via_d)

        via_lyt.addWidget(via_params)

        self._via_result = QTextEdit()
        self._via_result.setReadOnly(True)
        self._via_result.setFont(QFont("Consolas", 9))
        via_lyt.addWidget(self._via_result)

        tabs.addTab(via_w, "Indukcyjność vii")

        # ── Tab 4: Board traces overview ──────────────────────────────────────
        board_w = QWidget()
        board_lyt = QVBoxLayout(board_w)

        self._board_table = QTableWidget()
        self._board_table.setColumnCount(6)
        self._board_table.setHorizontalHeaderLabels([
            "Warstwa", "Sieć", "Długość (mm)", "Tpd (ns)", "Kryt. dł. (mm)", "Stan"
        ])
        self._board_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._board_table.setEditTriggers(QTableWidget.NoEditTriggers)
        board_lyt.addWidget(self._board_table)

        btn_scan = QPushButton("🔍 Skanuj ścieżki projektu")
        btn_scan.clicked.connect(self._scan_board_traces)
        board_lyt.addWidget(btn_scan)

        tabs.addTab(board_w, "Ścieżki projektu")

        layout.addWidget(tabs)
        self._tabs = tabs

        # ── Close ─────────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _update_all(self) -> None:
        self._update_propagation()
        self._update_crosstalk()
        self._update_via()

    def _update_propagation(self) -> None:
        freq = self._freq_spin.value()
        rise = self._rise_spin.value()
        er = self._er_spin.value()
        length = self._trace_len_spin.value()

        tpd = calc_propagation_delay_ns_per_mm(er)
        total_delay = tpd * length
        bw = calc_rise_time_bandwidth_mhz(rise)
        crit_len = calc_critical_length_mm(freq, er)
        crit_len_bw = calc_critical_length_mm(bw, er)

        status = "OK — terminacja niepotrzebna"
        if length > crit_len:
            status = "WYMAGANA terminacja (długość > λ/4)"
        elif length > crit_len / 2:
            status = "Rozważ terminację (długość > λ/8)"

        lines = [
            f"=== PROPAGACJA SYGNAŁU ===",
            f"",
            f"Stała dielektryczna (εr):      {er:.1f}",
            f"Opóźnienie propagacji:          {tpd*1000:.3f} ps/mm  ({tpd:.4f} ns/mm)",
            f"Opóźnienie całkowite ({length:.0f} mm): {total_delay:.3f} ns",
            f"",
            f"Częstotliwość:                  {freq:.1f} MHz",
            f"Krytyczna długość (λ/4):        {crit_len:.1f} mm",
            f"Ścieżka {length:.0f} mm vs krytyczna {crit_len:.1f} mm: {status}",
            f"",
            f"Czas narastania:                {rise:.2f} ns",
            f"Efektywne pasmo (-3dB):         {bw:.1f} MHz",
            f"Kryt. długość dla BW ({bw:.0f} MHz): {crit_len_bw:.1f} mm",
            f"",
            f"WSKAZÓWKI:",
        ]

        if length > crit_len:
            lines.append("  ! Zastosuj terminację szeregową (22–47Ω przy źródle)")
            lines.append("  ! lub terminację równoległą na końcu linii (VCC/2)")
        else:
            lines.append("  ✓ Ścieżka poniżej krytycznej długości — brak potrzeby terminacji")

        if total_delay > rise * 0.5:
            lines.append(f"  ! Opóźnienie {total_delay:.2f} ns > 50% czasu narastania {rise:.2f} ns")
            lines.append("    Sygnał wygląda jak linia transmisyjna — zadbaj o impedancję 50Ω")

        self._prop_result.setPlainText("\n".join(lines))

    def _update_crosstalk(self) -> None:
        w = self._ct_width.value()
        s = self._ct_spacing.value()
        l = self._ct_length.value()
        freq = self._freq_spin.value()

        ct_db = calc_crosstalk_db(w, s, l, freq)
        ratio = w / (w + 2 * s) * 100

        lines = [
            f"=== ANALIZA PRZESŁUCHU (CROSSTALK) ===",
            f"",
            f"Szerokość ścieżki:   {w:.2f} mm",
            f"Odstęp:              {s:.2f} mm  (3W rule wymaga: {3*w:.2f} mm)",
            f"Długość par:         {l:.0f} mm",
            f"Współczynnik sprzęż.:{ratio:.1f}%",
            f"",
            f"NEXT (przesłuch):    {ct_db:.1f} dB przy {freq:.0f} MHz",
            f"",
        ]

        if s >= 3 * w:
            lines.append("✓ Reguła 3W spełniona — niskie ryzyko przesłuchu")
        elif s >= 2 * w:
            lines.append("⚠ Reguła 3W NIE jest spełniona (s < 3W)")
            lines.append("  Rozważ zwiększenie odstępu lub zmniejszenie długości par")
        else:
            lines.append("✗ Bardzo bliskie ścieżki — wysoki przesłuch!")
            lines.append(f"  Minimalne zalecane s = {3*w:.2f} mm (reguła 3W)")
            lines.append("  Lub przełóż ścieżki na różne warstwy z planem GND między nimi")

        lines.extend([
            f"",
            f"ZALECENIA REDUKCJI PRZESŁUCHU:",
            f"  1. Zachowaj s >= 3×W (reguła 3W): s = {3*w:.2f} mm",
            f"  2. Skróć równoległe odcinki do minimum",
            f"  3. Umieść plan GND między warstwami",
            f"  4. Nie układaj ścieżek równolegle na sąsiednich warstwach",
            f"  5. Dla >100 MHz: odwróć kierunek tras na warstwach int.",
        ])

        self._ct_result.setPlainText("\n".join(lines))

    def _update_via(self) -> None:
        h = self._via_h.value()
        d = self._via_d.value()
        freq = self._freq_spin.value()

        L_nh = calc_via_inductance_nh(h, d)
        X_ohm = calc_via_reactance_ohm(h, d, freq)
        X_1ghz = calc_via_reactance_ohm(h, d, 1000)

        lines = [
            f"=== INDUKCYJNOŚĆ PRZELOTKI (VIA) ===",
            f"",
            f"Grubość płytki (h):  {h:.2f} mm",
            f"Średnica wiercenia:  {d:.2f} mm",
            f"",
            f"Indukcyjność vii:    {L_nh:.3f} nH",
            f"Reaktancja @ {freq:.0f} MHz:  {X_ohm*1000:.1f} mΩ  ({X_ohm:.3f} Ω)",
            f"Reaktancja @ 1 GHz:  {X_1ghz*1000:.1f} mΩ  ({X_1ghz:.3f} Ω)",
            f"",
        ]

        if X_ohm > 5:
            lines.append("! Wysoka reaktancja vii — problematyczne dla sygnałów HF")
            lines.append("  Używaj mniejszych przelotki lub buried/blind vias")
        elif X_ohm > 1:
            lines.append("⚠ Zauważalna reaktancja — dla sygnałów >500 MHz")
            lines.append("  dodaj kondensatory odsprzęgające przy vii")
        else:
            lines.append("✓ Reaktancja niska — via OK dla tej częstotliwości")

        lines.extend([
            f"",
            f"OPTYMALIZACJA VIA:",
            f"  - Mniej warstw = mniej indukcyjności",
            f"  - Back-drill (usunięcie stub) dla sygnałów >2 GHz",
            f"  - Via-in-pad dla gęstych BGA",
            f"  - Condenser via (wypełnienie) dla RF",
        ])

        self._via_result.setPlainText("\n".join(lines))

    def _scan_board_traces(self) -> None:
        board = self._project.board if self._project else None
        if not board:
            QMessageBox.warning(self, "Brak projektu", "Załaduj projekt PCB.")
            return

        freq = self._freq_spin.value()
        er = self._er_spin.value()
        tpd = calc_propagation_delay_ns_per_mm(er)
        crit = calc_critical_length_mm(freq, er)

        self._board_table.setRowCount(0)
        for tr in board.traces:
            length = math.hypot(tr.x2 - tr.x1, tr.y2 - tr.y1)
            delay = tpd * length
            status = "OK"
            color = QColor("#2d6a2d")
            if length > crit:
                status = "Terminacja!"
                color = QColor("#8b0000")
            elif length > crit / 2:
                status = "Sprawdź"
                color = QColor("#7a4d00")

            row = self._board_table.rowCount()
            self._board_table.insertRow(row)
            self._board_table.setItem(row, 0, QTableWidgetItem(tr.layer))
            self._board_table.setItem(row, 1, QTableWidgetItem(tr.net_name or ""))
            self._board_table.setItem(row, 2, QTableWidgetItem(f"{length:.2f}"))
            self._board_table.setItem(row, 3, QTableWidgetItem(f"{delay:.3f}"))
            self._board_table.setItem(row, 4, QTableWidgetItem(f"{crit:.1f}"))
            si = QTableWidgetItem(status)
            si.setBackground(QBrush(color))
            self._board_table.setItem(row, 5, si)

        self._tabs.setCurrentIndex(3)
