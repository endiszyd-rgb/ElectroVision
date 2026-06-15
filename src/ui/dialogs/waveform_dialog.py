"""Waveform / RC-RL Simulator Dialog — visualize simple circuit responses."""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QDoubleSpinBox, QComboBox, QFormLayout,
    QSplitter, QWidget, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QLinearGradient, QPolygonF
)

from src.core.project import Project


# ── Waveform generators ────────────────────────────────────────────────────────

def gen_square(t: list[float], freq: float, vhi: float, vlo: float) -> list[float]:
    period = 1 / freq if freq > 0 else 1
    return [vhi if (t_ % period) < period / 2 else vlo for t_ in t]


def gen_sine(t: list[float], freq: float, amp: float, offset: float) -> list[float]:
    return [amp * math.sin(2 * math.pi * freq * t_) + offset for t_ in t]


def gen_rc_step_response(t: list[float], r: float, c: float,
                         v_in: float) -> list[float]:
    """V_out(t) = V_in * (1 - e^(-t/RC)) for step input."""
    tau = r * c
    if tau <= 0:
        return [v_in] * len(t)
    return [v_in * (1 - math.exp(-t_ / tau)) for t_ in t]


def gen_rl_step_response(t: list[float], r: float, l: float,
                         v_in: float) -> list[float]:
    """I(t) = V_in/R * (1 - e^(-R/L * t)) — current through RL."""
    tau = l / r if r > 0 else float('inf')
    if tau <= 0 or r <= 0:
        return [v_in / r if r > 0 else 0] * len(t)
    i_max = v_in / r
    return [i_max * (1 - math.exp(-t_ / tau)) for t_ in t]


def gen_rc_discharge(t: list[float], r: float, c: float,
                     v0: float) -> list[float]:
    """V(t) = V0 * e^(-t/RC) — capacitor discharge."""
    tau = r * c
    if tau <= 0:
        return [0.0] * len(t)
    return [v0 * math.exp(-t_ / tau) for t_ in t]


def gen_lc_resonance(t: list[float], l: float, c: float,
                     v0: float, damping: float = 0.1) -> list[float]:
    """Damped LC oscillation: V(t) = V0 * e^(-d*t) * cos(w0*t)."""
    if l <= 0 or c <= 0:
        return [0.0] * len(t)
    w0 = 1 / math.sqrt(l * c)
    return [v0 * math.exp(-damping * w0 * t_) * math.cos(w0 * t_) for t_ in t]


def gen_pwm_filtered(t: list[float], freq: float, duty: float,
                     r: float, c: float, v_in: float) -> list[float]:
    """PWM signal filtered through RC low-pass — numerical integration."""
    dt = t[1] - t[0] if len(t) > 1 else 1e-6
    tau = r * c if r > 0 and c > 0 else 1e-6
    period = 1 / freq if freq > 0 else 1
    out = [0.0]
    for i in range(1, len(t)):
        v_pwm = v_in if (t[i] % period) < period * duty else 0.0
        v_prev = out[-1]
        dv = (v_pwm - v_prev) / tau * dt
        out.append(min(v_in, max(0, v_prev + dv)))
    return out


# ── Waveform painter widget ────────────────────────────────────────────────────

class WaveformView(QWidget):
    BG  = QColor("#0d1117")
    GRID = QColor("#1a2030")
    AXIS = QColor("#3a4050")
    COLORS = [QColor("#60c0ff"), QColor("#60ff90"), QColor("#ff8040"),
              QColor("#ff60c0"), QColor("#ffd060")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._traces: list[tuple[str, list[float], list[float], QColor]] = []
        self._x_label = "Czas"
        self._y_label = "Napięcie / Prąd"
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_traces(self, traces, x_label="Czas", y_label="Wartość"):
        self._traces = traces
        self._x_label = x_label
        self._y_label = y_label
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._traces:
            p.setPen(QColor("#444"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak danych — kliknij Generuj")
            return

        margin = (50, 20, 20, 35)  # left, top, right, bottom
        W = self.width() - margin[0] - margin[2]
        H = self.height() - margin[1] - margin[3]

        # Gather all x/y values
        all_x = []
        all_y = []
        for _, xs, ys, _ in self._traces:
            all_x.extend(xs)
            all_y.extend(ys)

        if not all_x or not all_y:
            return

        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        if x_max == x_min:
            x_max = x_min + 1
        if y_max == y_min:
            y_max = y_min + 1
            y_min = y_min - 0.1

        def tx(x): return margin[0] + (x - x_min) / (x_max - x_min) * W
        def ty(y): return margin[1] + H - (y - y_min) / (y_max - y_min) * H

        # Grid
        p.setPen(QPen(self.GRID, 1))
        for i in range(5):
            xg = margin[0] + i * W // 4
            p.drawLine(xg, margin[1], xg, margin[1] + H)
        for i in range(5):
            yg = margin[1] + i * H // 4
            p.drawLine(margin[0], yg, margin[0] + W, yg)

        # Axes
        p.setPen(QPen(self.AXIS, 1))
        p.drawLine(margin[0], margin[1], margin[0], margin[1] + H)
        p.drawLine(margin[0], margin[1] + H, margin[0] + W, margin[1] + H)

        # Y axis labels
        p.setFont(QFont("Consolas", 7))
        p.setPen(QColor("#888"))
        for i in range(5):
            y_val = y_min + (y_max - y_min) * i / 4
            yp = ty(y_val)
            p.drawText(2, int(yp) + 4, f"{y_val:.3g}")

        # X axis labels
        for i in range(5):
            x_val = x_min + (x_max - x_min) * i / 4
            xp = tx(x_val)
            p.drawText(int(xp) - 14, margin[1] + H + 14, _fmt_si(x_val, "s"))

        # Axis labels
        p.setFont(QFont("Arial", 8))
        p.setPen(QColor("#aaa"))
        p.drawText(margin[0] + W // 2 - 20, self.height() - 2, self._x_label)

        # Traces
        for ci, (label, xs, ys, color) in enumerate(self._traces):
            p.setPen(QPen(color, 1.5))
            pts = QPolygonF([QPointF(tx(x), ty(y)) for x, y in zip(xs, ys)])
            p.drawPolyline(pts)

            # Legend
            lx = margin[0] + 8 + ci * 120
            ly = margin[1] + 10
            p.setPen(color)
            p.drawLine(lx, ly, lx + 16, ly)
            p.setPen(QColor("#ddd"))
            p.drawText(lx + 20, ly + 4, label)


def _fmt_si(val: float, unit: str) -> str:
    if val == 0:
        return f"0{unit}"
    abs_val = abs(val)
    if abs_val >= 1:
        return f"{val:.3g}{unit}"
    if abs_val >= 1e-3:
        return f"{val*1e3:.3g}m{unit}"
    if abs_val >= 1e-6:
        return f"{val*1e6:.3g}µ{unit}"
    return f"{val*1e9:.3g}n{unit}"


# ── Dialog ─────────────────────────────────────────────────────────────────────

class WaveformDialog(QDialog):
    def __init__(self, project: Project = None, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Symulator przebiegów RC/RL/LC")
        self.resize(860, 580)
        self._build_ui()
        self._generate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Params ────────────────────────────────────────────────────────────
        params = QWidget()
        pl = QVBoxLayout(params)
        pl.setContentsMargins(0, 0, 0, 0)

        circ_box = QGroupBox("Układ")
        cf = QFormLayout(circ_box)

        self._circuit = QComboBox()
        self._circuit.addItems([
            "RC — odpowiedź skokowa (ładowanie)",
            "RC — rozładowanie",
            "RL — odpowiedź skokowa",
            "LC — rezonans tłumiony",
            "PWM → RC filtr dolnoprzepustowy",
            "Filtr RC — odpowiedź na sinus",
        ])
        self._circuit.currentIndexChanged.connect(self._generate)
        cf.addRow("Układ:", self._circuit)

        self._r_spin = QDoubleSpinBox()
        self._r_spin.setRange(0.1, 1e7)
        self._r_spin.setValue(1000)
        self._r_spin.setSuffix(" Ω")
        self._r_spin.setDecimals(1)
        self._r_spin.valueChanged.connect(self._generate)
        cf.addRow("Rezystancja R:", self._r_spin)

        self._c_spin = QDoubleSpinBox()
        self._c_spin.setRange(1e-12, 1e-3)
        self._c_spin.setValue(100e-9)
        self._c_spin.setSuffix(" F")
        self._c_spin.setDecimals(12)
        self._c_spin.setSingleStep(1e-9)
        self._c_spin.valueChanged.connect(self._generate)
        cf.addRow("Pojemność C:", self._c_spin)

        self._l_spin = QDoubleSpinBox()
        self._l_spin.setRange(1e-9, 1.0)
        self._l_spin.setValue(10e-6)
        self._l_spin.setSuffix(" H")
        self._l_spin.setDecimals(9)
        self._l_spin.setSingleStep(1e-6)
        self._l_spin.valueChanged.connect(self._generate)
        cf.addRow("Indukcyjność L:", self._l_spin)

        self._vin_spin = QDoubleSpinBox()
        self._vin_spin.setRange(0.1, 100)
        self._vin_spin.setValue(3.3)
        self._vin_spin.setSuffix(" V")
        self._vin_spin.valueChanged.connect(self._generate)
        cf.addRow("Napięcie wej. Vin:", self._vin_spin)

        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(1, 1e6)
        self._freq_spin.setValue(1000)
        self._freq_spin.setSuffix(" Hz")
        self._freq_spin.valueChanged.connect(self._generate)
        cf.addRow("Częstotliwość sygnału:", self._freq_spin)

        self._duty_spin = QDoubleSpinBox()
        self._duty_spin.setRange(0.01, 0.99)
        self._duty_spin.setValue(0.5)
        self._duty_spin.setSingleStep(0.05)
        self._duty_spin.valueChanged.connect(self._generate)
        cf.addRow("Wypełnienie PWM:", self._duty_spin)

        pl.addWidget(circ_box)

        # Calculated values
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setFont(QFont("Consolas", 8))
        self._info_label.setStyleSheet("color:#aaa; padding:4px;")
        pl.addWidget(self._info_label)

        self._show_input = QCheckBox("Pokaż sygnał wejściowy")
        self._show_input.setChecked(True)
        self._show_input.toggled.connect(self._generate)
        pl.addWidget(self._show_input)

        pl.addStretch()

        btn_gen = QPushButton("▶ Generuj")
        btn_gen.clicked.connect(self._generate)
        pl.addWidget(btn_gen)

        splitter.addWidget(params)

        # ── Waveform ──────────────────────────────────────────────────────────
        self._view = WaveformView()
        splitter.addWidget(self._view)
        splitter.setSizes([240, 620])

        layout.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _generate(self) -> None:
        r = self._r_spin.value()
        c = self._c_spin.value()
        l = self._l_spin.value()
        v_in = self._vin_spin.value()
        freq = self._freq_spin.value()
        duty = self._duty_spin.value()
        circuit = self._circuit.currentIndex()

        tau_rc = r * c
        tau_rl = l / r if r > 0 else 0
        fc_rc = 1 / (2 * math.pi * tau_rc) if tau_rc > 0 else 0
        f0_lc = 1 / (2 * math.pi * math.sqrt(l * c)) if l > 0 and c > 0 else 0

        info_parts = [f"τ_RC = {_fmt_si(tau_rc, 's')}  fc = {fc_rc:.0f} Hz"]
        if l > 0:
            info_parts.append(f"τ_RL = {_fmt_si(tau_rl, 's')}  f₀_LC = {f0_lc:.0f} Hz")
        self._info_label.setText("  |  ".join(info_parts))

        # Time span: 5 time constants
        if circuit in (0, 1):
            t_end = max(5 * tau_rc, 1e-6)
        elif circuit == 2:
            t_end = max(5 * tau_rl, 1e-6)
        elif circuit == 3:
            t_end = max(5 / (f0_lc * 0.1 + 1), 3 / (f0_lc + 1))
        elif circuit == 4:
            t_end = max(5 / freq, 5 * tau_rc)
        else:
            t_end = max(5 / freq, 5 * tau_rc)

        N = 500
        t = [i * t_end / N for i in range(N + 1)]

        traces = []
        show_in = self._show_input.isChecked()

        if circuit == 0:  # RC step charge
            ys = gen_rc_step_response(t, r, c, v_in)
            traces.append(("V_out", t, ys, WaveformView.COLORS[0]))
            if show_in:
                ys_in = [v_in] * len(t)
                traces.append(("V_in", t, ys_in, WaveformView.COLORS[1]))
        elif circuit == 1:  # RC discharge
            ys = gen_rc_discharge(t, r, c, v_in)
            traces.append(("V(t)", t, ys, WaveformView.COLORS[0]))
        elif circuit == 2:  # RL step
            ys = gen_rl_step_response(t, r, l, v_in)
            traces.append(("I(t) [A]", t, ys, WaveformView.COLORS[0]))
            if show_in:
                ys_vl = [v_in - r * y for y in ys]
                traces.append(("V_L(t)", t, ys_vl, WaveformView.COLORS[2]))
        elif circuit == 3:  # LC resonance
            ys = gen_lc_resonance(t, l, c, v_in)
            traces.append(("V_LC(t)", t, ys, WaveformView.COLORS[0]))
        elif circuit == 4:  # PWM + RC filter
            ys_pwm = gen_square(t, freq, v_in, 0.0)
            ys_out = gen_pwm_filtered(t, freq, duty, r, c, v_in)
            if show_in:
                traces.append(("PWM in", t, ys_pwm, WaveformView.COLORS[1]))
            traces.append(("V_out (RC)", t, ys_out, WaveformView.COLORS[0]))
            dc_out = v_in * duty
            traces.append((f"DC avg ({dc_out:.2f}V)", t, [dc_out] * len(t),
                           WaveformView.COLORS[2]))
        elif circuit == 5:  # Sinus + RC filter
            ys_in = gen_sine(t, freq, v_in / 2, v_in / 2)
            gain = 1 / math.sqrt(1 + (freq / fc_rc) ** 2) if fc_rc > 0 else 1
            phase = -math.atan(freq / fc_rc) if fc_rc > 0 else 0
            ys_out = [v_in / 2 * gain * math.sin(2 * math.pi * freq * t_ + phase) + v_in / 2 * gain
                      for t_ in t]
            if show_in:
                traces.append(("V_in", t, ys_in, WaveformView.COLORS[1]))
            traces.append((f"V_out (G={gain:.2f})", t, ys_out, WaveformView.COLORS[0]))

        self._view.set_traces(traces, x_label=f"Czas [s]", y_label="Napięcie [V] / Prąd [A]")
