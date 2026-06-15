"""Trace Length Matcher — measure and equalise trace lengths per net."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QFormLayout,
    QSplitter, QTextEdit, QWidget, QTabWidget, QLineEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QBrush

from src.core.project import Project
from src.core.models.pcb_board import Trace


# ── Measurement ────────────────────────────────────────────────────────────────

@dataclass
class NetTraces:
    net: str
    traces: list[Trace] = field(default_factory=list)

    @property
    def total_length_mm(self) -> float:
        return sum(math.hypot(t.x2 - t.x1, t.y2 - t.y1) for t in self.traces)

    @property
    def trace_count(self) -> int:
        return len(self.traces)

    @property
    def avg_width_mm(self) -> float:
        if not self.traces:
            return 0.0
        return sum(t.width for t in self.traces) / len(self.traces)

    @property
    def layers(self) -> set[str]:
        return {t.layer for t in self.traces}


def measure_nets(board) -> list[NetTraces]:
    """Group traces by net and compute per-net statistics."""
    net_map: dict[str, NetTraces] = {}
    for trace in board.traces:
        net = trace.net_name or "(bez sieci)"
        if net not in net_map:
            net_map[net] = NetTraces(net=net)
        net_map[net].traces.append(trace)
    return sorted(net_map.values(), key=lambda n: n.net)


_DIFF_PAIR_SUFFIXES = [
    (r"(.+)_P$", r"(.+)_N$"),
    (r"(.+)\+$",  r"(.+)-$"),
    (r"(.+)_DP$", r"(.+)_DN$"),
    (r"(.+)PLUS$",r"(.+)MINUS$"),
    (r"(.+)_T$",  r"(.+)_C$"),
]


def find_diff_pairs(net_traces: list[NetTraces]) -> list[tuple[NetTraces, NetTraces]]:
    """Detect differential pairs by common naming conventions."""
    names = {nt.net: nt for nt in net_traces}
    pairs: list[tuple[NetTraces, NetTraces]] = []
    used: set[str] = set()

    for pos_re, neg_re in _DIFF_PAIR_SUFFIXES:
        for nt in net_traces:
            if nt.net in used:
                continue
            m = re.match(pos_re, nt.net, re.IGNORECASE)
            if not m:
                continue
            base = m.group(1)
            # find partner
            neg_re_full = neg_re.replace(r"(.+)", re.escape(base))
            for candidate in names:
                if candidate in used:
                    continue
                if re.match(neg_re_full, candidate, re.IGNORECASE):
                    pairs.append((nt, names[candidate]))
                    used.add(nt.net)
                    used.add(candidate)
                    break

    return pairs


def length_mismatch_mm(a: NetTraces, b: NetTraces) -> float:
    return abs(a.total_length_mm - b.total_length_mm)


# ── Propagation delay helpers ─────────────────────────────────────────────────

def _tpd_ps_per_mm(er: float = 4.5) -> float:
    """Propagation delay in ps/mm (FR4 microstrip approximation)."""
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12))
    return math.sqrt(er_eff) / 3e8 * 1e12 * 1e-3  # ps/mm


# ── Dialog ─────────────────────────────────────────────────────────────────────

class TraceLengthDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Analiza długości ścieżek — dopasowanie par różnicowych")
        self.resize(950, 640)
        self._build_ui()
        self._analyze()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Settings bar ──────────────────────────────────────────────────────
        tb = QHBoxLayout()

        tb.addWidget(QLabel("Er (FR4):"))
        self._er_spin = QDoubleSpinBox()
        self._er_spin.setRange(1.0, 20.0)
        self._er_spin.setValue(4.5)
        self._er_spin.setSingleStep(0.1)
        self._er_spin.valueChanged.connect(self._analyze)
        tb.addWidget(self._er_spin)

        tb.addWidget(QLabel("Max mismatch (mm):"))
        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.01, 50.0)
        self._tol_spin.setValue(0.5)
        self._tol_spin.setSuffix(" mm")
        self._tol_spin.valueChanged.connect(self._analyze)
        tb.addWidget(self._tol_spin)

        tb.addWidget(QLabel("Filtr sieci:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("np. USB, DDR, MIPI…")
        self._filter_edit.setMaximumWidth(160)
        self._filter_edit.textChanged.connect(self._apply_filter)
        tb.addWidget(self._filter_edit)

        self._cb_only_named = QCheckBox("Ukryj '(bez sieci)'")
        self._cb_only_named.setChecked(True)
        self._cb_only_named.toggled.connect(self._apply_filter)
        tb.addWidget(self._cb_only_named)

        tb.addStretch()

        btn_refresh = QPushButton("🔄 Odśwież")
        btn_refresh.clicked.connect(self._analyze)
        tb.addWidget(btn_refresh)

        layout.addLayout(tb)

        tabs = QTabWidget()

        # ── Tab 1: All nets ───────────────────────────────────────────────────
        tab_all = QWidget()
        tl = QVBoxLayout(tab_all)

        self._net_table = QTableWidget()
        self._net_table.setColumnCount(6)
        self._net_table.setHorizontalHeaderLabels([
            "Sieć", "Długość (mm)", "Ścieżki", "Śr. szer. (mm)",
            "Warstwy", "Opóźnienie (ps)"
        ])
        self._net_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._net_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._net_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._net_table.setSortingEnabled(True)
        self._net_table.itemSelectionChanged.connect(self._on_net_selected)
        tl.addWidget(self._net_table)

        tabs.addTab(tab_all, "📏 Długości ścieżek")

        # ── Tab 2: Differential pairs ──────────────────────────────────────────
        tab_diff = QWidget()
        dl = QVBoxLayout(tab_diff)

        self._diff_table = QTableWidget()
        self._diff_table.setColumnCount(7)
        self._diff_table.setHorizontalHeaderLabels([
            "Para (+)", "Para (−)", "Dł. + (mm)", "Dł. − (mm)",
            "Δ (mm)", "Δ (ps)", "Status"
        ])
        self._diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._diff_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._diff_table.setSortingEnabled(True)
        dl.addWidget(self._diff_table)

        self._diff_info = QLabel()
        self._diff_info.setStyleSheet("color: #aaa; font-size: 10px; padding: 2px;")
        dl.addWidget(self._diff_info)

        tabs.addTab(tab_diff, "🔀 Pary różnicowe")

        # ── Tab 3: Critical nets ──────────────────────────────────────────────
        tab_crit = QWidget()
        cl = QVBoxLayout(tab_crit)

        self._crit_text = QTextEdit()
        self._crit_text.setReadOnly(True)
        self._crit_text.setStyleSheet("font-family: Consolas; font-size: 10px;")
        cl.addWidget(self._crit_text)

        tabs.addTab(tab_crit, "⚠ Analizy krytyczne")

        layout.addWidget(tabs, 1)

        # ── Bottom ────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: #888; font-size: 10px;")
        bottom.addWidget(self._stats_lbl)
        bottom.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        self._all_nets: list[NetTraces] = []

    def _analyze(self) -> None:
        board = self._project.board if self._project else None
        if not board:
            return

        self._all_nets = measure_nets(board)
        tpd = _tpd_ps_per_mm(self._er_spin.value())

        # Fill net table
        self._net_table.setSortingEnabled(False)
        self._net_table.setRowCount(0)
        for nt in self._all_nets:
            row = self._net_table.rowCount()
            self._net_table.insertRow(row)
            self._net_table.setItem(row, 0, QTableWidgetItem(nt.net))

            length_item = QTableWidgetItem(f"{nt.total_length_mm:.3f}")
            length_item.setData(Qt.UserRole, nt.total_length_mm)
            self._net_table.setItem(row, 1, length_item)

            self._net_table.setItem(row, 2, QTableWidgetItem(str(nt.trace_count)))
            self._net_table.setItem(row, 3, QTableWidgetItem(f"{nt.avg_width_mm:.3f}"))
            self._net_table.setItem(row, 4, QTableWidgetItem(", ".join(sorted(nt.layers))))

            delay_ps = nt.total_length_mm * tpd
            self._net_table.setItem(row, 5, QTableWidgetItem(f"{delay_ps:.1f}"))

        self._net_table.setSortingEnabled(True)

        # Fill diff pairs table
        pairs = find_diff_pairs(self._all_nets)
        tol = self._tol_spin.value()
        self._diff_table.setSortingEnabled(False)
        self._diff_table.setRowCount(0)
        for pos, neg in pairs:
            row = self._diff_table.rowCount()
            self._diff_table.insertRow(row)
            self._diff_table.setItem(row, 0, QTableWidgetItem(pos.net))
            self._diff_table.setItem(row, 1, QTableWidgetItem(neg.net))
            self._diff_table.setItem(row, 2, QTableWidgetItem(f"{pos.total_length_mm:.3f}"))
            self._diff_table.setItem(row, 3, QTableWidgetItem(f"{neg.total_length_mm:.3f}"))

            delta_mm = length_mismatch_mm(pos, neg)
            delta_ps = delta_mm * tpd
            delta_item = QTableWidgetItem(f"{delta_mm:.3f}")
            delta_item.setData(Qt.UserRole, delta_mm)
            self._diff_table.setItem(row, 4, delta_item)
            self._diff_table.setItem(row, 5, QTableWidgetItem(f"{delta_ps:.1f}"))

            ok = delta_mm <= tol
            status_item = QTableWidgetItem("✓ OK" if ok else f"✗ +{delta_mm:.3f}mm")
            status_item.setForeground(QColor("#60e060") if ok else QColor("#e06060"))
            self._diff_table.setItem(row, 6, status_item)

        self._diff_table.setSortingEnabled(True)
        n_ok  = sum(1 for pos, neg in pairs if length_mismatch_mm(pos, neg) <= tol)
        n_bad = len(pairs) - n_ok
        self._diff_info.setText(
            f"Wykryte pary: {len(pairs)}  |  OK: {n_ok}  |  Poza tolerancją: {n_bad}  |  "
            f"Tolerancja: {tol:.2f} mm = {tol * tpd:.1f} ps"
        )

        # Critical nets report
        total_traces  = len(board.traces)
        total_length  = sum(nt.total_length_mm for nt in self._all_nets)
        longest       = max(self._all_nets, key=lambda n: n.total_length_mm, default=None)
        shortest      = min(
            (n for n in self._all_nets if n.total_length_mm > 0),
            key=lambda n: n.total_length_mm, default=None
        )
        lines = [
            "═══ Raport analizy długości ścieżek ═══",
            "",
            f"Łącznie ścieżek:      {total_traces}",
            f"Łącznie sieci:        {len(self._all_nets)}",
            f"Sumaryczna długość:   {total_length:.2f} mm ({total_length/10:.2f} cm)",
            f"Er (substrat):        {self._er_spin.value():.1f}",
            f"Opóźnienie prop.:     {_tpd_ps_per_mm(self._er_spin.value()):.3f} ps/mm",
            "",
        ]
        if longest:
            lines += [
                f"Najdłuższa sieć:  {longest.net}",
                f"  Długość:        {longest.total_length_mm:.3f} mm",
                f"  Opóźnienie:     {longest.total_length_mm * _tpd_ps_per_mm(self._er_spin.value()):.1f} ps",
                "",
            ]
        if shortest:
            lines += [
                f"Najkrótsza sieć:  {shortest.net}",
                f"  Długość:        {shortest.total_length_mm:.3f} mm",
                "",
            ]

        # Nets above 100mm
        long_nets = [n for n in self._all_nets if n.total_length_mm > 100]
        if long_nets:
            lines += [f"⚠ Ścieżki > 100mm ({len(long_nets)}):"]
            for nt in sorted(long_nets, key=lambda n: -n.total_length_mm)[:10]:
                lines.append(
                    f"  {nt.net:<20} {nt.total_length_mm:7.2f} mm  "
                    f"{nt.total_length_mm * _tpd_ps_per_mm(self._er_spin.value()):6.1f} ps"
                )
            lines.append("")

        # Diff pair mismatches
        bad_pairs = [(p, n) for p, n in pairs if length_mismatch_mm(p, n) > tol]
        if bad_pairs:
            tpd = _tpd_ps_per_mm(self._er_spin.value())
            lines += [f"⚠ Pary różnicowe poza tolerancją ({len(bad_pairs)}):"]
            for pos, neg in bad_pairs:
                dm = length_mismatch_mm(pos, neg)
                lines.append(
                    f"  {pos.net} / {neg.net}  Δ={dm:.3f}mm  Δt={dm*tpd:.1f}ps"
                )
            lines.append("")

        if not long_nets and not bad_pairs:
            lines.append("✓ Brak krytycznych problemów z długościami ścieżek.")

        self._crit_text.setPlainText("\n".join(lines))

        total_nets = len(self._all_nets)
        self._stats_lbl.setText(
            f"Sieci: {total_nets}  |  Ścieżki: {total_traces}  |  "
            f"Sumaryczna długość: {total_length:.1f} mm  |  "
            f"Pary różnicowe: {len(pairs)}"
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().lower()
        hide_unnamed = self._cb_only_named.isChecked()
        for row in range(self._net_table.rowCount()):
            item = self._net_table.item(row, 0)
            if not item:
                continue
            net = item.text()
            hidden = (hide_unnamed and net == "(bez sieci)") or \
                     (query and query not in net.lower())
            self._net_table.setRowHidden(row, hidden)

    def _on_net_selected(self) -> None:
        row = self._net_table.currentRow()
        if row < 0:
            return
        item = self._net_table.item(row, 0)
        if item:
            net = item.text()
            nt = next((n for n in self._all_nets if n.net == net), None)
            if nt:
                tpd = _tpd_ps_per_mm(self._er_spin.value())
                # Highlight row color
                self._net_table.item(row, 0).setToolTip(
                    f"Ścieżki: {nt.trace_count}\n"
                    f"Długość: {nt.total_length_mm:.3f} mm\n"
                    f"Opóźnienie: {nt.total_length_mm * tpd:.1f} ps\n"
                    f"Warstwy: {', '.join(sorted(nt.layers))}"
                )
