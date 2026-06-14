"""Electronics Calculator — impedance, trace current, RC filter, voltage divider, LED resistor."""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QDoubleSpinBox, QLabel, QPushButton,
    QGroupBox, QTextEdit, QComboBox, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spin(lo, hi, val, dec=3, suffix="") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setDecimals(dec)
    if suffix:
        sb.setSuffix(f" {suffix}")
    sb.setSingleStep(0.1)
    sb.setMinimumWidth(120)
    return sb


def _result_box() -> QTextEdit:
    te = QTextEdit()
    te.setReadOnly(True)
    te.setFont(QFont("Consolas", 10))
    te.setMaximumHeight(180)
    return te


# ── Calculations ──────────────────────────────────────────────────────────────

def calc_microstrip(w_mm: float, h_mm: float, t_mm: float, er: float) -> dict:
    """Microstrip impedance (IPC-2141A approximation)."""
    if w_mm <= 0 or h_mm <= 0:
        return {"error": "Szerokość i wysokość muszą być > 0"}
    w = w_mm / h_mm
    t = t_mm / h_mm
    # Effective width correction for copper thickness
    if t > 0:
        w_eff = w + (t / math.pi) * (1 + math.log(2 * h_mm / t_mm))
    else:
        w_eff = w
    # Effective dielectric constant
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / w_eff) ** -0.5
    # Impedance
    if w_eff <= 1:
        z0 = (60 / math.sqrt(er_eff)) * math.log(8 / w_eff + w_eff / 4)
    else:
        z0 = 120 * math.pi / (math.sqrt(er_eff) * (w_eff + 1.393 + 0.667 * math.log(w_eff + 1.444)))
    # Propagation delay (ps/mm)
    v_light = 299.792  # mm/ns
    t_delay = 1 / (v_light / math.sqrt(er_eff)) * 1000  # ps/mm
    return {"Z0": z0, "er_eff": er_eff, "delay_ps_mm": t_delay}


def calc_microstrip_width(z0_target: float, h_mm: float, t_mm: float, er: float) -> float:
    """Binary search for trace width that gives target impedance."""
    lo, hi = 0.01, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2
        res = calc_microstrip(mid, h_mm, t_mm, er)
        if "error" in res:
            break
        if res["Z0"] > z0_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def calc_stripline(w_mm: float, b_mm: float, t_mm: float, er: float) -> dict:
    """Symmetric stripline impedance (IPC-2141A)."""
    if w_mm <= 0 or b_mm <= 0:
        return {"error": "Szerokość i grubość dielektryka muszą być > 0"}
    x = 0.85 - 0.6 * (1 - t_mm / b_mm)
    z0 = (60 / math.sqrt(er)) * math.log(4 * b_mm / (0.67 * math.pi * (x * w_mm + t_mm)))
    return {"Z0": max(z0, 1.0), "er": er}


def calc_trace_current(w_mm: float, t_mm: float, dt: float, layer: str) -> dict:
    """Max trace current per IPC-2221 (A and B curves)."""
    area_mils2 = (w_mm / 0.0254) * (t_mm / 0.0254)  # convert mm to mils
    if layer == "external":
        i_max = 0.048 * (dt ** 0.44) * (area_mils2 ** 0.725)
    else:
        i_max = 0.024 * (dt ** 0.44) * (area_mils2 ** 0.725)
    r_per_mm = 1 / (0.01724 * (w_mm * t_mm))  # mΩ/mm (copper resistivity)
    v_drop_per_100mm = i_max * r_per_mm * 100 * 0.001  # V per 100mm
    return {"I_max_A": i_max, "R_mohm_per_mm": r_per_mm, "V_drop_per_100mm": v_drop_per_100mm}


def calc_rc_filter(r_ohm: float, c_uf: float) -> dict:
    """RC low-pass filter: corner frequency and time constant."""
    if r_ohm <= 0 or c_uf <= 0:
        return {"error": "R i C muszą być > 0"}
    c_f = c_uf * 1e-6
    tau = r_ohm * c_f
    fc = 1 / (2 * math.pi * tau)
    return {"tau_ms": tau * 1000, "fc_Hz": fc, "fc_kHz": fc / 1000}


def calc_voltage_divider(vin: float, r1: float, r2: float) -> dict:
    """Simple R1/R2 voltage divider."""
    if r1 + r2 <= 0:
        return {"error": "R1+R2 muszą być > 0"}
    vout = vin * r2 / (r1 + r2)
    i_ma = vin / (r1 + r2) * 1000
    p_r1 = (vin - vout) ** 2 / r1 if r1 > 0 else 0
    p_r2 = vout ** 2 / r2 if r2 > 0 else 0
    return {"Vout": vout, "I_mA": i_ma, "P_R1_mW": p_r1 * 1000, "P_R2_mW": p_r2 * 1000}


def calc_led_resistor(vsupply: float, vf: float, if_ma: float) -> dict:
    """LED current limiting resistor."""
    if if_ma <= 0:
        return {"error": "Prąd LED musi być > 0"}
    r = (vsupply - vf) / (if_ma / 1000)
    p = (vsupply - vf) * if_ma / 1000
    # Nearest standard E24
    e24 = [10,11,12,13,15,16,18,20,22,24,27,30,33,36,39,43,47,51,56,62,68,75,82,91]
    std = min((v * 10**m for v in e24 for m in range(5)), key=lambda x: abs(x - r) if x >= r else float('inf'))
    i_actual = (vsupply - vf) / std * 1000 if std > 0 else 0
    return {"R_ohm": r, "R_std_ohm": std, "P_mW": p * 1000, "I_actual_mA": i_actual}


# ── Dialog ────────────────────────────────────────────────────────────────────

class ElectronicsCalcDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kalkulator elektroniczny")
        self.setMinimumSize(560, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab_impedance(),  "Impedancja PCB")
        self._tabs.addTab(self._tab_current(),    "Prąd ścieżki")
        self._tabs.addTab(self._tab_rc(),         "Filtr RC")
        self._tabs.addTab(self._tab_divider(),    "Dzielnik napięcia")
        self._tabs.addTab(self._tab_led(),        "Rezystor LED")
        root.addWidget(self._tabs)

    # ── Impedance tab ─────────────────────────────────────────────────────────

    def _tab_impedance(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Typ:"))
        self._imp_mode = QComboBox()
        self._imp_mode.addItems(["Microstrip (zewnętrzna)", "Stripline (wewnętrzna)"])
        self._imp_mode.currentIndexChanged.connect(lambda _: self._calc_impedance())
        mode_row.addWidget(self._imp_mode); mode_row.addStretch()
        lay.addLayout(mode_row)

        form = QFormLayout()
        self._imp_w   = _spin(0.01, 20, 0.25, 3, "mm"); form.addRow("Szerokość ścieżki w:", self._imp_w)
        self._imp_h   = _spin(0.01, 10, 1.6,  3, "mm"); form.addRow("Grubość dielektryka h:", self._imp_h)
        self._imp_t   = _spin(0.0,  1,  0.035,4, "mm"); form.addRow("Grubość miedzi t:", self._imp_t)
        self._imp_er  = _spin(1.0,  20, 4.5,  2, "");   form.addRow("Stała dielektryczna εr:", self._imp_er)
        lay.addLayout(form)

        target_row = QFormLayout()
        self._imp_z0_target = _spin(1, 300, 50, 1, "Ω")
        target_row.addRow("Docelowa impedancja Z₀:", self._imp_z0_target)
        lay.addLayout(target_row)

        btn_row = QHBoxLayout()
        btn_calc = QPushButton("Oblicz impedancję")
        btn_calc.clicked.connect(self._calc_impedance)
        btn_width = QPushButton("Oblicz szerokość ścieżki dla Z₀")
        btn_width.clicked.connect(self._calc_width_for_z0)
        btn_row.addWidget(btn_calc); btn_row.addWidget(btn_width)
        lay.addLayout(btn_row)

        self._imp_result = _result_box(); lay.addWidget(self._imp_result)
        return w

    def _calc_impedance(self) -> None:
        w = self._imp_w.value(); h = self._imp_h.value()
        t = self._imp_t.value(); er = self._imp_er.value()
        if self._imp_mode.currentIndex() == 0:
            res = calc_microstrip(w, h, t, er)
            if "error" in res:
                self._imp_result.setPlainText(f"Błąd: {res['error']}")
                return
            self._imp_result.setPlainText(
                f"=== Microstrip ===\n"
                f"Impedancja Z₀       = {res['Z0']:.2f} Ω\n"
                f"εr_eff              = {res['er_eff']:.3f}\n"
                f"Opóźnienie          = {res['delay_ps_mm']:.3f} ps/mm\n\n"
                f"Parametry:\n"
                f"  ścieżka w={w:.3f}mm  h={h:.3f}mm  t={t:.4f}mm  εr={er:.2f}"
            )
        else:
            b = h  # use h as total dielectric thickness for stripline
            res = calc_stripline(w, b, t, er)
            if "error" in res:
                self._imp_result.setPlainText(f"Błąd: {res['error']}")
                return
            self._imp_result.setPlainText(
                f"=== Stripline ===\n"
                f"Impedancja Z₀       = {res['Z0']:.2f} Ω\n"
                f"εr                  = {er:.2f}\n\n"
                f"Parametry:\n"
                f"  ścieżka w={w:.3f}mm  b={b:.3f}mm  t={t:.4f}mm"
            )

    def _calc_width_for_z0(self) -> None:
        z0 = self._imp_z0_target.value()
        h = self._imp_h.value(); t = self._imp_t.value(); er = self._imp_er.value()
        w = calc_microstrip_width(z0, h, t, er)
        check = calc_microstrip(w, h, t, er)
        z_check = check.get("Z0", 0)
        self._imp_result.setPlainText(
            f"=== Szerokość dla Z₀ = {z0:.1f} Ω ===\n"
            f"Wymagana szerokość  = {w:.4f} mm\n"
            f"Weryfikacja Z₀      = {z_check:.2f} Ω\n\n"
            f"Ustaw szerokość ścieżki na {w:.3f} mm\n"
            f"  h={h:.3f}mm  t={t:.4f}mm  εr={er:.2f}"
        )

    # ── Trace current tab ─────────────────────────────────────────────────────

    def _tab_current(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        form = QFormLayout()
        self._cur_w   = _spin(0.05, 50, 0.25, 3, "mm"); form.addRow("Szerokość ścieżki:", self._cur_w)
        self._cur_t   = _spin(0.01,  1, 0.035,4, "mm"); form.addRow("Grubość miedzi:", self._cur_t)
        self._cur_dt  = _spin(1, 100, 10, 1, "°C");     form.addRow("Dopuszczalny ΔT:", self._cur_dt)
        self._cur_lay = QComboBox()
        self._cur_lay.addItems(["external (zewnętrzna)", "internal (wewnętrzna)"])
        form.addRow("Warstwa:", self._cur_lay)
        lay.addLayout(form)

        btn = QPushButton("Oblicz prąd maksymalny")
        btn.clicked.connect(self._calc_current)
        lay.addWidget(btn)
        self._cur_result = _result_box(); lay.addWidget(self._cur_result)
        return w

    def _calc_current(self) -> None:
        ltype = "external" if self._cur_lay.currentIndex() == 0 else "internal"
        res = calc_trace_current(self._cur_w.value(), self._cur_t.value(),
                                 self._cur_dt.value(), ltype)
        self._cur_result.setPlainText(
            f"=== Prąd ścieżki (IPC-2221) ===\n"
            f"Maksymalny prąd     = {res['I_max_A']:.3f} A\n"
            f"Rezystancja         = {res['R_mohm_per_mm']:.3f} mΩ/mm\n"
            f"Spadek napięcia     = {res['V_drop_per_100mm']:.3f} V / 100mm\n\n"
            f"ścieżka {self._cur_w.value():.3f}mm × {self._cur_t.value():.4f}mm  "
            f"ΔT={self._cur_dt.value():.0f}°C  {ltype}"
        )

    # ── RC filter tab ─────────────────────────────────────────────────────────

    def _tab_rc(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        form = QFormLayout()
        self._rc_r = _spin(0.1, 10e6, 10000, 1, "Ω");  form.addRow("Rezystancja R:", self._rc_r)
        self._rc_c = _spin(0.001, 10000, 100, 3, "µF"); form.addRow("Pojemność C:", self._rc_c)
        lay.addLayout(form)

        btn = QPushButton("Oblicz filtr RC")
        btn.clicked.connect(self._calc_rc)
        lay.addWidget(btn)
        self._rc_result = _result_box(); lay.addWidget(self._rc_result)
        return w

    def _calc_rc(self) -> None:
        res = calc_rc_filter(self._rc_r.value(), self._rc_c.value())
        if "error" in res:
            self._rc_result.setPlainText(f"Błąd: {res['error']}"); return
        self._rc_result.setPlainText(
            f"=== Filtr RC dolnoprzepustowy ===\n"
            f"Stała czasowa τ     = {res['tau_ms']:.4f} ms\n"
            f"Częstotliwość fc    = {res['fc_Hz']:.2f} Hz\n"
            f"                    = {res['fc_kHz']:.4f} kHz\n\n"
            f"R={self._rc_r.value():.1f}Ω  C={self._rc_c.value():.3f}µF"
        )

    # ── Voltage divider tab ───────────────────────────────────────────────────

    def _tab_divider(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        form = QFormLayout()
        self._div_vin = _spin(0.1, 1000, 5.0, 2, "V");  form.addRow("Napięcie Vin:", self._div_vin)
        self._div_r1  = _spin(1, 10e6, 10000, 1, "Ω");  form.addRow("R1 (górny):", self._div_r1)
        self._div_r2  = _spin(1, 10e6, 10000, 1, "Ω");  form.addRow("R2 (dolny):", self._div_r2)
        lay.addLayout(form)

        btn = QPushButton("Oblicz dzielnik napięcia")
        btn.clicked.connect(self._calc_divider)
        lay.addWidget(btn)
        self._div_result = _result_box(); lay.addWidget(self._div_result)
        return w

    def _calc_divider(self) -> None:
        res = calc_voltage_divider(self._div_vin.value(), self._div_r1.value(), self._div_r2.value())
        if "error" in res:
            self._div_result.setPlainText(f"Błąd: {res['error']}"); return
        self._div_result.setPlainText(
            f"=== Dzielnik napięcia ===\n"
            f"Vout                = {res['Vout']:.4f} V\n"
            f"Prąd podziału       = {res['I_mA']:.4f} mA\n"
            f"Moc P_R1            = {res['P_R1_mW']:.3f} mW\n"
            f"Moc P_R2            = {res['P_R2_mW']:.3f} mW\n\n"
            f"Vin={self._div_vin.value():.2f}V  R1={self._div_r1.value():.0f}Ω  R2={self._div_r2.value():.0f}Ω"
        )

    # ── LED resistor tab ──────────────────────────────────────────────────────

    def _tab_led(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w)
        form = QFormLayout()
        self._led_vs = _spin(1.5, 48, 5.0, 2, "V");  form.addRow("Napięcie zasilania:", self._led_vs)
        self._led_vf = _spin(0.5,  5, 2.0, 2, "V");  form.addRow("Spadek na LED (Vf):", self._led_vf)
        self._led_if = _spin(0.1, 1000, 20, 1, "mA"); form.addRow("Prąd LED (If):", self._led_if)
        lay.addLayout(form)

        btn = QPushButton("Oblicz rezystor LED")
        btn.clicked.connect(self._calc_led)
        lay.addWidget(btn)
        self._led_result = _result_box(); lay.addWidget(self._led_result)
        return w

    def _calc_led(self) -> None:
        res = calc_led_resistor(self._led_vs.value(), self._led_vf.value(), self._led_if.value())
        if "error" in res:
            self._led_result.setPlainText(f"Błąd: {res['error']}"); return
        self._led_result.setPlainText(
            f"=== Rezystor LED ===\n"
            f"Wymagany R          = {res['R_ohm']:.2f} Ω\n"
            f"Najbliższy E24      = {res['R_std_ohm']:.0f} Ω\n"
            f"Rzeczywisty prąd    = {res['I_actual_mA']:.2f} mA\n"
            f"Moc rezystora       = {res['P_mW']:.1f} mW\n\n"
            f"Vs={self._led_vs.value():.2f}V  Vf={self._led_vf.value():.2f}V  If={self._led_if.value():.1f}mA"
        )
