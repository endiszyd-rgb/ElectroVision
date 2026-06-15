"""ERC — Electrical Rules Check (distinct from DFM manufacturing checks)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTextEdit, QSplitter, QWidget, QCheckBox, QTabWidget,
    QProgressBar, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QBrush, QFont

from src.core.project import Project
from src.core.models.component import Component


# ── ERC rule result ────────────────────────────────────────────────────────────

@dataclass
class ERCIssue:
    severity: str           # "error" | "warning" | "info"
    rule: str               # rule name / category
    message: str
    reference: str = ""     # component ref, if applicable
    net: str = ""           # net name, if applicable
    suggestion: str = ""

    @property
    def icon(self) -> str:
        return {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(self.severity, "?")

    @property
    def color(self) -> QColor:
        return {
            "error":   QColor("#e06060"),
            "warning": QColor("#e0c060"),
            "info":    QColor("#6080e0"),
        }.get(self.severity, QColor("#aaaaaa"))


# ── ERC engine ─────────────────────────────────────────────────────────────────

_RESERVED_NET_NAMES = {"NET", "WIRE", "BUS", "POWER", "GND", "VCC", "VDD"}
_POWER_NET_RE = re.compile(
    r"(VCC|VDD|VIN|V\+|VBUS|VBAT|3\.?3V?|5V?|12V?|1\.?8V?|2\.?5V?|24V?|48V?)",
    re.IGNORECASE
)
_GND_NET_RE = re.compile(r"(GND|AGND|DGND|PGND|0V|VSS)", re.IGNORECASE)

# Components that are typically signal drivers (outputs)
_DRIVER_TYPES = {"ic", "transistor"}
# Passive / high-Z by default
_PASSIVE_TYPES = {"resistor", "capacitor", "inductor", "crystal"}


def run_erc(board) -> list[ERCIssue]:
    issues: list[ERCIssue] = []
    if not board:
        return [ERCIssue("error", "Board", "Brak projektu PCB.")]

    comps   = board.components
    traces  = board.traces
    nets    = board.nets

    # ── 1. Unconnected pads ───────────────────────────────────────────────────
    unconn: list[tuple[Component, str]] = []
    for comp in comps:
        for pad in comp.pads:
            if not pad.net_name:
                unconn.append((comp, pad.number))
    if unconn:
        issues.append(ERCIssue(
            "warning", "Niepolączone pady",
            f"{len(unconn)} padów bez przypisanej sieci",
            suggestion="Sprawdź czy pady są połączone z siecią lub celowo pozostawione bez sieci (test point)."
        ))
        for comp, pad_num in unconn[:8]:  # show up to 8 examples
            issues.append(ERCIssue(
                "warning", "Niepolączone pady",
                f"Pad {pad_num} komponentu {comp.reference} ({comp.value}) nie ma sieci",
                reference=comp.reference,
                suggestion="Podłącz pad do sieci lub dodaj test point."
            ))

    # ── 2. Duplicate references ───────────────────────────────────────────────
    refs_seen: dict[str, list[Component]] = {}
    for comp in comps:
        refs_seen.setdefault(comp.reference, []).append(comp)
    for ref, lst in refs_seen.items():
        if len(lst) > 1:
            issues.append(ERCIssue(
                "error", "Duplikaty referencji",
                f"Referencja '{ref}' użyta {len(lst)} razy",
                reference=ref,
                suggestion="Zmień referencje tak, aby były unikalne (użyj Auto-Annotation)."
            ))

    # ── 3. Net with only one connection (dangling net) ────────────────────────
    net_comp_count: dict[str, int] = {}
    for comp in comps:
        for pad in comp.pads:
            if pad.net_name:
                net_comp_count[pad.net_name] = net_comp_count.get(pad.net_name, 0) + 1
    for net_name, count in net_comp_count.items():
        if count == 1:
            issues.append(ERCIssue(
                "warning", "Sieć z jednym połączeniem",
                f"Sieć '{net_name}' ma tylko jedno podłączone urządzenie",
                net=net_name,
                suggestion="Sieć z jednym połączeniem prawdopodobnie jest odwieszona (dangling net). Sprawdź czy jest to celowe."
            ))

    # ── 4. Missing GND ────────────────────────────────────────────────────────
    has_gnd = any(_GND_NET_RE.search(n) for n in net_comp_count)
    has_pwr = any(_POWER_NET_RE.search(n) for n in net_comp_count)
    if not has_gnd and comps:
        issues.append(ERCIssue(
            "error", "Brak masy",
            "Brak sieci GND/AGND/0V — każdy projekt wymaga odniesienia do masy",
            suggestion="Dodaj połączenie z masą (GND) do komponentów zasilania."
        ))
    if has_pwr and not has_gnd:
        issues.append(ERCIssue(
            "error", "Zasilanie bez masy",
            "Znaleziono sieć zasilania ale brak sieci masy (GND)",
            suggestion="Dodaj sieć GND jako odniesienie dla zasilania."
        ))

    # ── 5. Power net with no source component ─────────────────────────────────
    power_nets = {n for n in net_comp_count if _POWER_NET_RE.search(n)}
    for pnet in sorted(power_nets):
        # Check if any component on this net is a regulator/source
        pads_on_net = [
            (comp, pad) for comp in comps for pad in comp.pads
            if pad.net_name == pnet
        ]
        sources = [
            comp for comp, pad in pads_on_net
            if any(kw in f"{comp.value} {comp.reference}".upper()
                   for kw in ["LDO", "REG", "LM317", "LM78", "LM33", "AMS", "AP2112",
                               "MIC52", "VREG", "BATTERY", "USB", "JACK", "CONN"])
        ]
        if not sources and len(pads_on_net) > 0:
            issues.append(ERCIssue(
                "info", "Brak źródła zasilania",
                f"Sieć '{pnet}' nie ma oczywistego źródła (regulatora/złącza)",
                net=pnet,
                suggestion="Sprawdź czy sieć zasilania ma podłączony regulator, złącze lub baterię."
            ))

    # ── 6. IC without bypass caps ─────────────────────────────────────────────
    ics = [c for c in comps if c.component_type == "ic"]
    caps_per_net: dict[str, int] = {}
    for comp in comps:
        if comp.component_type == "capacitor":
            for pad in comp.pads:
                if pad.net_name and _POWER_NET_RE.search(pad.net_name):
                    caps_per_net[pad.net_name] = caps_per_net.get(pad.net_name, 0) + 1

    if ics and not caps_per_net:
        issues.append(ERCIssue(
            "warning", "Brak kondensatorów blokujących",
            f"{len(ics)} układów IC bez kondensatorów blokujących na szynach zasilania",
            suggestion="Dodaj kondensatory 100nF przy każdym układzie IC (IPC-7711 / dobra praktyka)."
        ))

    # ── 7. Components with no pads ────────────────────────────────────────────
    no_pads = [c for c in comps if not c.pads]
    if no_pads:
        issues.append(ERCIssue(
            "warning", "Komponenty bez padów",
            f"{len(no_pads)} komponentów nie ma padów",
            suggestion="Sprawdź czy footprint jest poprawnie przypisany."
        ))
        for comp in no_pads[:5]:
            issues.append(ERCIssue(
                "info", "Brak padów",
                f"{comp.reference} ({comp.value}, footprint={comp.footprint}) — brak padów",
                reference=comp.reference
            ))

    # ── 8. High-impedance supply nets ─────────────────────────────────────────
    for net_name, count in net_comp_count.items():
        if _POWER_NET_RE.search(net_name) and count > 10:
            issues.append(ERCIssue(
                "info", "Duże obciążenie szyny",
                f"Sieć '{net_name}' ma {count} podłączonych komponentów",
                net=net_name,
                suggestion="Przy dużej liczbie odbiorców rozważ użycie kondensatorów bulk i odpowiedniej szerokości ścieżek."
            ))

    # ── 9. Traces without nets ───────────────────────────────────────────────
    unnamed_traces = [t for t in traces if not t.net_name]
    if unnamed_traces:
        issues.append(ERCIssue(
            "info", "Ścieżki bez sieci",
            f"{len(unnamed_traces)} ścieżek nie ma przypisanej sieci",
            suggestion="Przypisz sieci do ścieżek lub usuń ścieżki testowe."
        ))

    # ── 10. Net name quality ──────────────────────────────────────────────────
    for net_name in net_comp_count:
        if re.match(r"^\d+$", net_name):
            issues.append(ERCIssue(
                "info", "Jakość nazwy sieci",
                f"Sieć o nazwie czysto numerycznej: '{net_name}'",
                net=net_name,
                suggestion="Nadaj opisowe nazwy sieciom (np. SDA, MOSI, PWM_LED)."
            ))
        if len(net_name) > 30:
            issues.append(ERCIssue(
                "info", "Jakość nazwy sieci",
                f"Bardzo długa nazwa sieci: '{net_name}' ({len(net_name)} znaków)",
                net=net_name,
                suggestion="Skróć nazwę sieci dla lepszej czytelności."
            ))

    # ── 11. Floating components (not connected to any net) ────────────────────
    for comp in comps:
        if all(not pad.net_name for pad in comp.pads) and comp.pads:
            issues.append(ERCIssue(
                "error", "Komponent odłączony",
                f"{comp.reference} ({comp.value}) — żaden pad nie jest podłączony do sieci",
                reference=comp.reference,
                suggestion="Podłącz wszystkie pady komponentu do odpowiednich sieci."
            ))

    # ── 12. Multiple VCC nets (potential conflict) ─────────────────────────────
    vcc_nets = [n for n in net_comp_count if _POWER_NET_RE.search(n)]
    distinct_voltages = set()
    for n in vcc_nets:
        m = re.search(r"(\d+\.?\d*)V", n, re.IGNORECASE)
        if m:
            distinct_voltages.add(float(m.group(1)))
    if len(distinct_voltages) > 3:
        issues.append(ERCIssue(
            "info", "Wiele napięć zasilania",
            f"Projekt używa {len(distinct_voltages)} różnych napięć zasilania: "
            f"{', '.join(f'{v}V' for v in sorted(distinct_voltages))}",
            suggestion="Upewnij się, że poziomy napięć są zgodne z interfejsami komponentów (poziomy logiczne)."
        ))

    if not issues:
        issues.append(ERCIssue("info", "OK", "Brak naruszeń ERC — projekt wygląda poprawnie elektrycznie."))

    return issues


# ── Background worker ──────────────────────────────────────────────────────────

class _ERCWorker(QObject):
    done = Signal(list)

    def __init__(self, board):
        super().__init__()
        self._board = board

    def run(self):
        issues = run_erc(self._board)
        self.done.emit(issues)


# ── Dialog ─────────────────────────────────────────────────────────────────────

class ERCDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._issues:  list[ERCIssue] = []
        self.setWindowTitle("ERC — Sprawdzenie reguł elektrycznych")
        self.resize(940, 620)
        self._build_ui()
        self._run()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Filter bar ────────────────────────────────────────────────────────
        tb = QHBoxLayout()
        tb.addWidget(QLabel("Pokaż:"))
        self._cb_err  = QCheckBox("Błędy")
        self._cb_err.setChecked(True)
        self._cb_err.toggled.connect(self._apply_filter)
        self._cb_warn = QCheckBox("Ostrzeżenia")
        self._cb_warn.setChecked(True)
        self._cb_warn.toggled.connect(self._apply_filter)
        self._cb_info = QCheckBox("Info")
        self._cb_info.setChecked(True)
        self._cb_info.toggled.connect(self._apply_filter)
        tb.addWidget(self._cb_err)
        tb.addWidget(self._cb_warn)
        tb.addWidget(self._cb_info)

        tb.addSpacing(12)
        tb.addWidget(QLabel("Kategoria:"))
        self._cat_combo = QComboBox()
        self._cat_combo.addItem("— Wszystkie —")
        self._cat_combo.setMinimumWidth(180)
        self._cat_combo.currentTextChanged.connect(self._apply_filter)
        tb.addWidget(self._cat_combo)

        tb.addStretch()

        self._progress = QProgressBar()
        self._progress.setMaximumWidth(120)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        tb.addWidget(self._progress)

        btn_run = QPushButton("▶ Uruchom ERC")
        btn_run.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_run.clicked.connect(self._run)
        tb.addWidget(btn_run)

        layout.addLayout(tb)

        # ── Issue table ───────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Typ", "Kategoria", "Opis", "Komponent", "Sieć"]
        )
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSortingEnabled(True)
        self._table.itemSelectionChanged.connect(self._on_selected)
        splitter.addWidget(self._table)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(120)
        self._detail.setStyleSheet("font-family: Consolas; font-size: 10px;")
        splitter.addWidget(self._detail)

        splitter.setSizes([440, 120])
        layout.addWidget(splitter, 1)

        # ── Summary ───────────────────────────────────────────────────────────
        self._summary = QLabel()
        self._summary.setStyleSheet("color: #aaa; font-size: 10px; padding: 2px;")
        layout.addWidget(self._summary)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _run(self) -> None:
        board = self._project.board if self._project else None
        self._progress.setVisible(True)
        self._thread = QThread()
        self._worker = _ERCWorker(board)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    def _on_done(self, issues: list[ERCIssue]) -> None:
        self._progress.setVisible(False)
        self._issues = issues

        # Collect unique categories
        cats = sorted({i.rule for i in issues})
        self._cat_combo.blockSignals(True)
        current_cat = self._cat_combo.currentText()
        self._cat_combo.clear()
        self._cat_combo.addItem("— Wszystkie —")
        for cat in cats:
            self._cat_combo.addItem(cat)
        idx = self._cat_combo.findText(current_cat)
        self._cat_combo.setCurrentIndex(max(0, idx))
        self._cat_combo.blockSignals(False)

        self._populate_table(issues)

    def _populate_table(self, issues: list[ERCIssue]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for issue in issues:
            row = self._table.rowCount()
            self._table.insertRow(row)

            icon_item = QTableWidgetItem(f"{issue.icon} {issue.severity.upper()}")
            icon_item.setForeground(issue.color)
            icon_item.setFont(QFont("Consolas", 8, QFont.Bold))
            self._table.setItem(row, 0, icon_item)

            self._table.setItem(row, 1, QTableWidgetItem(issue.rule))
            self._table.setItem(row, 2, QTableWidgetItem(issue.message))

            ref_item = QTableWidgetItem(issue.reference)
            ref_item.setForeground(QColor("#80d0f0"))
            self._table.setItem(row, 3, ref_item)

            net_item = QTableWidgetItem(issue.net)
            net_item.setForeground(QColor("#80f0a0"))
            self._table.setItem(row, 4, net_item)

        self._table.setSortingEnabled(True)
        self._update_summary()
        self._apply_filter()

    def _apply_filter(self) -> None:
        show_err  = self._cb_err.isChecked()
        show_warn = self._cb_warn.isChecked()
        show_info = self._cb_info.isChecked()
        cat_flt   = self._cat_combo.currentText()
        show_all_cats = cat_flt.startswith("—")

        for row in range(self._table.rowCount()):
            sev_item = self._table.item(row, 0)
            cat_item = self._table.item(row, 1)
            if not sev_item or not cat_item:
                continue
            sev = sev_item.text().split()[-1].lower()
            cat = cat_item.text()
            ok_sev = (sev == "error" and show_err) or \
                     (sev == "warning" and show_warn) or \
                     (sev == "info" and show_info)
            ok_cat = show_all_cats or cat == cat_flt
            self._table.setRowHidden(row, not (ok_sev and ok_cat))

    def _update_summary(self) -> None:
        n_err  = sum(1 for i in self._issues if i.severity == "error")
        n_warn = sum(1 for i in self._issues if i.severity == "warning")
        n_info = sum(1 for i in self._issues if i.severity == "info")
        status = "✓ BRAK BŁĘDÓW" if n_err == 0 else f"✗ {n_err} BŁĘDÓW"
        self._summary.setText(
            f"{status}  |  Ostrzeżenia: {n_warn}  |  Info: {n_info}  |  "
            f"Łącznie naruszeń: {len(self._issues)}"
        )

    def _on_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._issues):
            return
        # Find matching issue by message text (table may be sorted)
        msg_item = self._table.item(row, 2)
        if not msg_item:
            return
        msg = msg_item.text()
        issue = next((i for i in self._issues if i.message == msg), None)
        if issue:
            self._detail.setPlainText(
                f"Kategoria:   {issue.rule}\n"
                f"Opis:        {issue.message}\n"
                f"Komponent:   {issue.reference or '—'}\n"
                f"Sieć:        {issue.net or '—'}\n"
                f"Sugestia:    {issue.suggestion}"
            )
