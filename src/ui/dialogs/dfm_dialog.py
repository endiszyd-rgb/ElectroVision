"""DFM (Design for Manufacturability) Dialog — manufacturer-specific production checks."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QTextEdit, QWidget, QTabWidget, QFormLayout,
    QDoubleSpinBox, QProgressBar, QFileDialog, QMessageBox,
    QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project


# ── Manufacturer profiles ──────────────────────────────────────────────────────

@dataclass
class MfgProfile:
    name: str
    min_trace_width_mm: float       = 0.127   # 5 mil
    min_clearance_mm: float         = 0.127
    min_via_drill_mm: float         = 0.3
    min_via_annular_mm: float       = 0.13
    min_hole_mm: float              = 0.3
    max_hole_mm: float              = 6.3
    min_edge_clearance_mm: float    = 0.3
    min_silkscreen_width_mm: float  = 0.15
    max_board_size_mm: tuple        = (500.0, 500.0)
    min_board_size_mm: tuple        = (5.0, 5.0)
    max_aspect_ratio: float         = 8.0    # via aspect ratio h/d
    board_thickness_mm: float       = 1.6
    copper_weight_oz: float         = 1.0    # 1 oz = 35 µm
    solder_mask: bool               = True
    notes: str                      = ""


PROFILES: dict[str, MfgProfile] = {
    "JLCPCB — Standard (2-layer)": MfgProfile(
        name="JLCPCB Standard",
        min_trace_width_mm=0.127,
        min_clearance_mm=0.127,
        min_via_drill_mm=0.3,
        min_via_annular_mm=0.13,
        min_hole_mm=0.3,
        max_hole_mm=6.3,
        min_edge_clearance_mm=0.3,
        max_board_size_mm=(500.0, 470.0),
        min_board_size_mm=(5.0, 5.0),
        max_aspect_ratio=8.0,
        notes="JLCPCB Standard 2-layer. Min 5mil trace/space. Via ≥0.3mm drill."
    ),
    "JLCPCB — Advanced (4-layer)": MfgProfile(
        name="JLCPCB Advanced 4L",
        min_trace_width_mm=0.1,
        min_clearance_mm=0.1,
        min_via_drill_mm=0.2,
        min_via_annular_mm=0.1,
        min_hole_mm=0.2,
        max_hole_mm=6.3,
        min_edge_clearance_mm=0.2,
        max_board_size_mm=(490.0, 490.0),
        notes="JLCPCB Advanced 4-layer. Min 4mil trace/space."
    ),
    "PCBWay — Standard": MfgProfile(
        name="PCBWay Standard",
        min_trace_width_mm=0.127,
        min_clearance_mm=0.127,
        min_via_drill_mm=0.3,
        min_via_annular_mm=0.15,
        min_hole_mm=0.3,
        max_hole_mm=6.0,
        min_edge_clearance_mm=0.3,
        max_board_size_mm=(600.0, 600.0),
        notes="PCBWay Standard. Similar to JLCPCB."
    ),
    "Eurocircuits — Class 6C": MfgProfile(
        name="Eurocircuits 6C",
        min_trace_width_mm=0.1,
        min_clearance_mm=0.1,
        min_via_drill_mm=0.2,
        min_via_annular_mm=0.1,
        min_hole_mm=0.2,
        max_hole_mm=6.5,
        min_edge_clearance_mm=0.2,
        max_board_size_mm=(400.0, 400.0),
        notes="Eurocircuits Class 6C. European PCB fab, high quality."
    ),
    "Hobbyist (relaxed)": MfgProfile(
        name="Hobbyist",
        min_trace_width_mm=0.2,
        min_clearance_mm=0.2,
        min_via_drill_mm=0.4,
        min_via_annular_mm=0.2,
        min_hole_mm=0.4,
        max_hole_mm=8.0,
        min_edge_clearance_mm=0.5,
        max_board_size_mm=(300.0, 300.0),
        notes="Relaxed constraints for hobby-grade PCBs."
    ),
    "IPC Class B (professional)": MfgProfile(
        name="IPC Class B",
        min_trace_width_mm=0.075,
        min_clearance_mm=0.075,
        min_via_drill_mm=0.2,
        min_via_annular_mm=0.05,
        min_hole_mm=0.15,
        max_hole_mm=6.35,
        min_edge_clearance_mm=0.13,
        max_board_size_mm=(600.0, 600.0),
        max_aspect_ratio=10.0,
        notes="IPC-2221 Class B. Professional production standard."
    ),
}


# ── DFM checks ─────────────────────────────────────────────────────────────────

@dataclass
class DFMIssue:
    severity: str     # "error" | "warning" | "info"
    category: str
    message: str
    position: str = ""
    suggestion: str = ""


def run_dfm(board, profile: MfgProfile) -> list[DFMIssue]:
    issues: list[DFMIssue] = []

    if not board:
        return [DFMIssue("error", "Board", "Brak płytki PCB.")]

    # Board size
    w, h = board.width_mm, board.height_mm
    min_w, min_h = profile.min_board_size_mm
    max_w, max_h = profile.max_board_size_mm
    if w < min_w or h < min_h:
        issues.append(DFMIssue("error", "Wymiary",
            f"Płytka {w:.1f}×{h:.1f}mm zbyt mała (min {min_w}×{min_h}mm)",
            suggestion="Powiększ rozmiar płytki."))
    if w > max_w or h > max_h:
        issues.append(DFMIssue("error", "Wymiary",
            f"Płytka {w:.1f}×{h:.1f}mm zbyt duża (max {max_w}×{max_h}mm)",
            suggestion="Zmniejsz rozmiar płytki lub zamów niestandardowy."))

    # Edge.Cuts outline
    edge = [l for l in board.graphic_lines if l.layer == "Edge.Cuts"]
    edge += [a for a in board.graphic_arcs  if a.layer == "Edge.Cuts"]
    if not edge:
        issues.append(DFMIssue("error", "Kontur",
            "Brak konturu płytki (Edge.Cuts).",
            suggestion="Narysuj kontur na warstwie Edge.Cuts."))

    # Trace width
    narrow = [(t, t.width) for t in board.traces if t.width < profile.min_trace_width_mm]
    if narrow:
        issues.append(DFMIssue("error", "Ścieżki",
            f"{len(narrow)} ścieżek zbyt wąskich (min {profile.min_trace_width_mm:.3f}mm)",
            position=f"({narrow[0][0].x1:.1f},{narrow[0][0].y1:.1f})",
            suggestion=f"Poszerz ścieżki do min {profile.min_trace_width_mm:.3f}mm."))

    # Trace clearance (simplified: check traces on same layer)
    _check_trace_clearance(board, profile, issues)

    # Via drill size
    small_vias = [v for v in board.vias if v.drill < profile.min_via_drill_mm]
    if small_vias:
        issues.append(DFMIssue("error", "Przelotki",
            f"{len(small_vias)} przelotki z za małym wierceniem (min {profile.min_via_drill_mm:.2f}mm)",
            position=f"({small_vias[0].x:.1f},{small_vias[0].y:.1f})",
            suggestion=f"Użyj wierceń ≥ {profile.min_via_drill_mm:.2f}mm."))

    # Via annular ring
    small_ring = [v for v in board.vias if (v.size - v.drill) / 2 < profile.min_via_annular_mm]
    if small_ring:
        issues.append(DFMIssue("warning", "Przelotki",
            f"{len(small_ring)} przelotki z za małym pierścieniem (min {profile.min_via_annular_mm:.3f}mm)",
            suggestion=f"Zwiększ rozmiar przelotki lub zmniejsz wiercenie."))

    # Via aspect ratio
    board_thickness = profile.board_thickness_mm
    for v in board.vias:
        if v.drill > 0:
            ratio = board_thickness / v.drill
            if ratio > profile.max_aspect_ratio:
                issues.append(DFMIssue("warning", "Przelotki",
                    f"Via ({v.x:.1f},{v.y:.1f}) aspect ratio {ratio:.1f}:1 > max {profile.max_aspect_ratio}:1",
                    suggestion="Zwiększ średnicę wiercenia lub zmniejsz grubość płytki."))

    # Edge clearance
    bb = board.bounding_box if hasattr(board, 'bounding_box') else None
    if bb:
        x_min, y_min, x_max, y_max = bb
        ec = profile.min_edge_clearance_mm
        for tr in board.traces:
            for x, y in [(tr.x1, tr.y1), (tr.x2, tr.y2)]:
                dist_edge = min(x - x_min, y - y_min, x_max - x, y_max - y)
                if dist_edge < ec:
                    issues.append(DFMIssue("warning", "Krawędź",
                        f"Ścieżka blisko krawędzi: {dist_edge:.2f}mm (min {ec:.2f}mm)",
                        position=f"({x:.1f},{y:.1f})",
                        suggestion="Zachowaj odstęp ≥ {ec:.2f}mm od krawędzi Edge.Cuts."))
                    break

    # Duplicate refs
    refs = [c.reference for c in board.components]
    seen = set()
    for ref in refs:
        if ref in seen:
            issues.append(DFMIssue("error", "Komponenty",
                f"Zduplikowana referencja: {ref}",
                suggestion="Zmień referencję aby była unikalna."))
        seen.add(ref)

    # Unconnected pads (pads with no net)
    unconnected = sum(1 for c in board.components for p in c.pads if not p.net_name)
    if unconnected > 0:
        issues.append(DFMIssue("info", "Sieci",
            f"{unconnected} padów bez przypisanej sieci",
            suggestion="Sprawdź czy wszystkie pady są podłączone do sieci."))

    # SMT components on both sides
    front = sum(1 for c in board.components if c.layer == "F.Cu")
    back  = sum(1 for c in board.components if c.layer == "B.Cu")
    if front > 0 and back > 0:
        issues.append(DFMIssue("info", "Montaż",
            f"Komponenty na obu stronach: {front} na F.Cu, {back} na B.Cu",
            suggestion="Montaż dwustronny zwiększa koszt. Rozważ przeniesienie elementów na jedną stronę."))

    # ICs without decoupling caps
    ics = [c for c in board.components if c.component_type == "ic"]
    caps = [c for c in board.components if c.component_type == "capacitor"]
    if len(ics) > len(caps) * 0.8 and ics:
        issues.append(DFMIssue("warning", "Zasilanie",
            f"{len(ics)} IC, tylko {len(caps)} kondensatorów — możliwy brak filtrowania",
            suggestion="Dodaj 100nF kondensator blokujący przy każdym IC (zalecenie IPC)."))

    # Board component density
    area_cm2 = board.width_mm * board.height_mm / 100
    if area_cm2 > 0 and len(board.components) / area_cm2 > 20:
        issues.append(DFMIssue("info", "Gęstość",
            f"Wysoka gęstość komponentów: {len(board.components)/area_cm2:.1f} komp/cm²",
            suggestion="Sprawdź czy odstępy między komponentami są wystarczające (min 0.2mm)."))

    if not issues:
        issues.append(DFMIssue("info", "OK",
            f"Brak problemów DFM dla profilu: {profile.name}", "", ""))

    return issues


def _check_trace_clearance(board, profile: MfgProfile, issues: list) -> None:
    traces_by_layer: dict[str, list] = {}
    for tr in board.traces:
        traces_by_layer.setdefault(tr.layer, []).append(tr)

    violations = 0
    first_pos = ""
    for layer, traces in traces_by_layer.items():
        if len(traces) < 2:
            continue
        for i in range(min(len(traces), 100)):
            for j in range(i + 1, min(len(traces), 100)):
                a, b = traces[i], traces[j]
                # Simplified: distance between endpoints
                dist = min(
                    math.hypot(a.x1 - b.x1, a.y1 - b.y1),
                    math.hypot(a.x1 - b.x2, a.y1 - b.y2),
                    math.hypot(a.x2 - b.x1, a.y2 - b.y1),
                    math.hypot(a.x2 - b.x2, a.y2 - b.y2),
                )
                if 0 < dist < profile.min_clearance_mm:
                    violations += 1
                    if not first_pos:
                        first_pos = f"({a.x1:.1f},{a.y1:.1f})"
    if violations:
        issues.append(DFMIssue("error", "Prześwit",
            f"{violations} par ścieżek z prześwitem < {profile.min_clearance_mm:.3f}mm",
            position=first_pos,
            suggestion=f"Zwiększ odstęp między ścieżkami do min {profile.min_clearance_mm:.3f}mm."))


# ── Dialog ─────────────────────────────────────────────────────────────────────

class DFMDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("DFM — Kontrola produkcyjna")
        self.resize(900, 620)
        self._issues: list[DFMIssue] = []
        self._build_ui()
        self._run()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Profile selector ──────────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Producent / profil:"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems(list(PROFILES.keys()))
        self._profile_combo.currentIndexChanged.connect(self._run)
        top.addWidget(self._profile_combo, 1)

        btn_run = QPushButton("🔄 Sprawdź")
        btn_run.clicked.connect(self._run)
        top.addWidget(btn_run)

        btn_export = QPushButton("📄 Eksportuj raport")
        btn_export.clicked.connect(self._export)
        top.addWidget(btn_export)
        layout.addLayout(top)

        # ── Profile notes ─────────────────────────────────────────────────────
        self._profile_notes = QLabel()
        self._profile_notes.setStyleSheet("color:#888; font-size:10px; padding:2px 4px;")
        layout.addWidget(self._profile_notes)

        splitter = QSplitter(Qt.Vertical)

        # ── Issue table ───────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Waga", "Kategoria", "Opis", "Pozycja", "Zalecenie"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        splitter.addWidget(self._table)

        # ── Summary ───────────────────────────────────────────────────────────
        self._summary = QTextEdit()
        self._summary.setReadOnly(True)
        self._summary.setFont(QFont("Consolas", 9))
        self._summary.setMaximumHeight(120)
        splitter.addWidget(self._summary)

        splitter.setSizes([400, 120])
        layout.addWidget(splitter, 1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _run(self) -> None:
        profile_name = self._profile_combo.currentText()
        profile = PROFILES.get(profile_name, list(PROFILES.values())[0])
        self._profile_notes.setText(f"ℹ {profile.notes}")

        board = self._project.board if self._project else None
        self._issues = run_dfm(board, profile)
        self._populate_table()
        self._update_summary(profile)

    def _populate_table(self) -> None:
        self._table.setRowCount(0)
        sev_colors = {
            "error":   (QColor("#8b0000"), "🔴 ERROR"),
            "warning": (QColor("#7a4d00"), "🟡 WARN"),
            "info":    (QColor("#1a3a1a"), "🔵 INFO"),
        }
        for issue in self._issues:
            row = self._table.rowCount()
            self._table.insertRow(row)
            color, label = sev_colors.get(issue.severity, (QColor("#222"), issue.severity))
            items = [
                QTableWidgetItem(label),
                QTableWidgetItem(issue.category),
                QTableWidgetItem(issue.message),
                QTableWidgetItem(issue.position),
                QTableWidgetItem(issue.suggestion),
            ]
            for col, item in enumerate(items):
                item.setBackground(QBrush(color))
                self._table.setItem(row, col, item)

    def _update_summary(self, profile: MfgProfile) -> None:
        errors   = sum(1 for i in self._issues if i.severity == "error")
        warnings = sum(1 for i in self._issues if i.severity == "warning")
        infos    = sum(1 for i in self._issues if i.severity == "info")

        board = self._project.board if self._project else None
        lines = [
            f"Profil: {profile.name}",
            f"Płytka: {board.width_mm:.1f}×{board.height_mm:.1f}mm | "
            f"{len(board.components)} komp. | {len(board.traces)} ścieżek | "
            f"{len(board.vias)} przelotki" if board else "Brak płytki",
            "",
            f"Błędy:        {errors}",
            f"Ostrzeżenia:  {warnings}",
            f"Informacje:   {infos}",
            "",
        ]
        if errors == 0 and warnings == 0:
            lines.append("✅ Projekt spełnia wymagania DFM dla wybranego producenta.")
        elif errors == 0:
            lines.append("⚠️  Projekt ma ostrzeżenia — warto sprawdzić przed zamówieniem.")
        else:
            lines.append("❌ Projekt ma błędy DFM — wymaga poprawek przed produkcją.")

        self._summary.setPlainText("\n".join(lines))

    def _export(self) -> None:
        if not self._issues:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj raport DFM",
            f"{self._project.name}_dfm_report.txt", "Tekst (*.txt)"
        )
        if not path:
            return
        lines = [
            f"RAPORT DFM — ElectroVision",
            f"Profil: {self._profile_combo.currentText()}",
            "=" * 60, ""
        ]
        for i in self._issues:
            lines.append(f"[{i.severity.upper():7s}] [{i.category}] {i.message}")
            if i.position:
                lines.append(f"         Pozycja: {i.position}")
            if i.suggestion:
                lines.append(f"         Zalec.:  {i.suggestion}")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Eksport", f"Raport zapisany:\n{path}")
