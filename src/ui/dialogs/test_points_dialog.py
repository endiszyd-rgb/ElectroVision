"""Menedżer punktów testowych — ICT / flying probe coverage analyser."""
from __future__ import annotations
import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QLineEdit,
    QSplitter, QWidget, QTextEdit, QProgressBar,
    QMessageBox, QFileDialog, QCheckBox, QTabWidget
)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard
from src.core.models.component import Component, Pad


# ── Model ──────────────────────────────────────────────────────────────────────

@dataclass
class TPPoint:
    reference: str
    net_name: str
    x: float
    y: float
    side: str           # "F.Cu" lub "B.Cu"
    drill: float = 1.0  # mm — otwór lub średnica pady


def _is_test_point(comp: Component) -> bool:
    ref = comp.reference.upper()
    return ref.startswith("TP") or ref.startswith("TEST")


def scan_test_points(board: PCBBoard) -> list[TPPoint]:
    """Zbiera wszystkie TP* z boardu."""
    tps: list[TPPoint] = []
    for comp in board.components:
        if not _is_test_point(comp):
            continue
        # Zbierz sieci z padów
        nets = {pad.net_name for pad in comp.pads if pad.net_name}
        net = next(iter(nets), "")
        # Określ stronę na podstawie warstwy footprintu
        side = getattr(comp, "layer", "F.Cu") or "F.Cu"
        # Rozmiar z pierwszego pada (jeśli jest)
        drill = 1.0
        if comp.pads:
            pad = comp.pads[0]
            drill = max(pad.width, pad.height, 0.5)
        tps.append(TPPoint(
            reference=comp.reference,
            net_name=net,
            x=comp.x,
            y=comp.y,
            side=side,
            drill=drill,
        ))
    return tps


def coverage_report(board: PCBBoard, tps: list[TPPoint]) -> dict:
    """Oblicza pokrycie testowe."""
    all_nets = {pad.net_name for comp in board.components
                for pad in comp.pads if pad.net_name}
    covered_nets = {tp.net_name for tp in tps if tp.net_name}
    uncovered = all_nets - covered_nets - {""}
    return {
        "total_nets":    len(all_nets),
        "covered_nets":  len(covered_nets),
        "uncovered":     sorted(uncovered),
        "tp_count":      len(tps),
        "coverage_pct":  len(covered_nets) / len(all_nets) * 100 if all_nets else 0,
        "f_count":       sum(1 for t in tps if "F" in t.side),
        "b_count":       sum(1 for t in tps if "B" in t.side),
    }


def export_flying_probe_csv(tps: list[TPPoint]) -> str:
    """Eksport CSV dla testera latającego (format Spea/GenRad/Takaya)."""
    lines = ["Reference,Net,X_mm,Y_mm,Side,Drill_mm"]
    for tp in sorted(tps, key=lambda t: t.reference):
        lines.append(
            f'"{tp.reference}","{tp.net_name}",'
            f'{tp.x:.4f},{tp.y:.4f},"{tp.side}",{tp.drill:.2f}'
        )
    return "\n".join(lines)


# ── Canvas ─────────────────────────────────────────────────────────────────────

class _TPCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: PCBBoard | None = None
        self._tps: list[TPPoint] = []
        self._sel_net: str = ""
        self.setMinimumSize(380, 260)
        self.setStyleSheet("background: #141420;")

    def set_data(self, board: PCBBoard, tps: list[TPPoint], sel_net: str = "") -> None:
        self._board, self._tps, self._sel_net = board, tps, sel_net
        self.update()

    def paintEvent(self, event) -> None:
        if not self._board:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bb = self._board.bounding_box
        bw, bh = bb[2] - bb[0] or 100, bb[3] - bb[1] or 100
        W, H = self.width(), self.height()
        margin = 20
        scale = min((W - 2*margin) / bw, (H - 2*margin) / bh)
        ox = margin - bb[0] * scale
        oy = margin - bb[1] * scale

        def pt(x, y): return QPointF(ox + x*scale, oy + y*scale)

        # Kontur płytki
        p.setPen(QPen(QColor("#f0c040"), 1.2))
        for gl in self._board.graphic_lines:
            if gl.layer == "Edge.Cuts":
                p.drawLine(pt(gl.x1, gl.y1), pt(gl.x2, gl.y2))

        # Ścieżki (tle)
        p.setPen(QPen(QColor("#5a3a1a"), 0.5))
        for t in self._board.traces:
            p.drawLine(pt(t.x1, t.y1), pt(t.x2, t.y2))

        # Punkty testowe
        for tp in self._tps:
            r = max(tp.drill * scale / 2, 4)
            cx, cy = pt(tp.x, tp.y).x(), pt(tp.x, tp.y).y()
            highlight = self._sel_net and tp.net_name == self._sel_net
            if tp.side.startswith("F"):
                clr = QColor("#40e080") if highlight else QColor("#20b050")
            else:
                clr = QColor("#e04080") if highlight else QColor("#b03060")
            p.setPen(QPen(QColor("white"), 0.5))
            p.setBrush(QBrush(clr))
            p.drawEllipse(QPointF(cx, cy), r, r)
            # label
            if scale > 3:
                p.setPen(QColor("#eeeeee"))
                p.setFont(QFont("Consolas", 6))
                p.drawText(QRectF(cx - 20, cy + r + 1, 40, 10),
                           Qt.AlignCenter, tp.reference)
        p.end()


# ── Dialog ─────────────────────────────────────────────────────────────────────

COL_REF  = 0
COL_NET  = 1
COL_X    = 2
COL_Y    = 3
COL_SIDE = 4
COL_DRL  = 5


class TestPointsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._board   = project.board
        self._tps: list[TPPoint] = []
        self.setWindowTitle("Menedżer punktów testowych — ICT / Flying Probe")
        self.resize(1060, 650)
        self._build_ui()
        self._scan()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()

        # ── Tab 1: Lista TP ────────────────────────────────────────────────────
        t1 = QWidget()
        t1l = QHBoxLayout(t1)
        spl = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        tb = QHBoxLayout()
        btn_scan  = QPushButton("⟳ Skanuj projekt")
        btn_scan.clicked.connect(self._scan)
        btn_add   = QPushButton("+ Dodaj TP…")
        btn_add.clicked.connect(self._add_tp)
        btn_del   = QPushButton("− Usuń wybrany")
        btn_del.clicked.connect(self._del_tp)
        tb.addWidget(btn_scan); tb.addWidget(btn_add); tb.addWidget(btn_del)
        tb.addStretch()
        self._flt = QLineEdit()
        self._flt.setPlaceholderText("Filtruj sieć…")
        self._flt.textChanged.connect(self._apply_filter)
        tb.addWidget(self._flt)
        ll.addLayout(tb)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Ref", "Sieć", "X [mm]", "Y [mm]", "Strona", "Śr. [mm]"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in range(2, 6):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_sel)
        ll.addWidget(self._table, 1)

        # Stats bar
        self._cov_bar = QProgressBar()
        self._cov_bar.setRange(0, 100)
        self._cov_bar.setStyleSheet(
            "QProgressBar{background:#222;border:1px solid #444;}"
            "QProgressBar::chunk{background:#209050;}"
        )
        self._cov_lbl = QLabel()
        self._cov_lbl.setStyleSheet("color:#aaa; font-size:10px;")
        ll.addWidget(self._cov_bar)
        ll.addWidget(self._cov_lbl)

        spl.addWidget(left)

        # Canvas
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.addWidget(QLabel("Mapa punktów testowych:"))
        self._canvas = _TPCanvas()
        rl.addWidget(self._canvas, 1)

        legend = QHBoxLayout()
        for clr, txt in [("#20b050", "F.Cu (front)"), ("#b03060", "B.Cu (back)")]:
            l = QLabel(f"■ {txt}")
            l.setStyleSheet(f"color:{clr}; font-size:10px;")
            legend.addWidget(l)
        legend.addStretch()
        rl.addLayout(legend)
        spl.addWidget(right)
        spl.setSizes([520, 440])
        t1l.addWidget(spl)
        tabs.addTab(t1, "📍 Punkty testowe")

        # ── Tab 2: Pokrycie sieci ──────────────────────────────────────────────
        t2 = QWidget()
        t2l = QVBoxLayout(t2)
        t2l.addWidget(QLabel("Sieci bez punktu testowego:"))
        self._uncov_table = QTableWidget()
        self._uncov_table.setColumnCount(1)
        self._uncov_table.setHorizontalHeaderLabels(["Sieć"])
        self._uncov_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._uncov_table.setEditTriggers(QTableWidget.NoEditTriggers)
        t2l.addWidget(self._uncov_table, 1)
        tabs.addTab(t2, "📊 Pokrycie sieci")

        # ── Tab 3: Dodaj TP ────────────────────────────────────────────────────
        t3 = QWidget()
        t3l = QVBoxLayout(t3)
        grp = QGroupBox("Nowy punkt testowy")
        gf = QFormLayout(grp)
        self._new_ref  = QLineEdit("TP1")
        gf.addRow("Referencja:", self._new_ref)
        self._new_net  = QLineEdit()
        self._new_net.setPlaceholderText("np. GND, SDA, CLK")
        gf.addRow("Sieć:", self._new_net)
        self._new_x    = QDoubleSpinBox()
        self._new_x.setRange(-500, 500); self._new_x.setSuffix(" mm")
        gf.addRow("X:", self._new_x)
        self._new_y    = QDoubleSpinBox()
        self._new_y.setRange(-500, 500); self._new_y.setSuffix(" mm")
        gf.addRow("Y:", self._new_y)
        self._new_side = QComboBox()
        self._new_side.addItems(["F.Cu", "B.Cu"])
        gf.addRow("Strona:", self._new_side)
        self._new_drl  = QDoubleSpinBox()
        self._new_drl.setRange(0.3, 5.0)
        self._new_drl.setValue(1.0)
        self._new_drl.setSuffix(" mm")
        gf.addRow("Średnica pada/otworu:", self._new_drl)
        t3l.addWidget(grp)
        btn_create = QPushButton("✔ Utwórz punkt testowy")
        btn_create.setStyleSheet("background:#1a4a8f;color:white;padding:4px;")
        btn_create.clicked.connect(self._create_tp)
        t3l.addWidget(btn_create)
        t3l.addStretch()
        tabs.addTab(t3, "➕ Dodaj TP")

        root.addWidget(tabs, 1)

        # Bottom
        bot = QHBoxLayout()
        btn_exp = QPushButton("💾 Eksportuj CSV (flying probe)")
        btn_exp.clicked.connect(self._export_csv)
        bot.addWidget(btn_exp)
        bot.addStretch()
        self._stat_lbl = QLabel()
        self._stat_lbl.setStyleSheet("color:#888;font-size:10px;")
        bot.addWidget(self._stat_lbl)
        bot.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        bot.addWidget(btn_close)
        root.addLayout(bot)

    # ── Logic ──────────────────────────────────────────────────────────────────

    def _scan(self) -> None:
        if not self._board:
            return
        self._tps = scan_test_points(self._board)
        self._populate_table()
        self._update_coverage()
        self._canvas.set_data(self._board, self._tps)

    def _populate_table(self) -> None:
        self._table.setRowCount(0)
        for tp in self._tps:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, COL_REF,  QTableWidgetItem(tp.reference))
            self._table.setItem(row, COL_NET,  QTableWidgetItem(tp.net_name))
            self._table.setItem(row, COL_X,    QTableWidgetItem(f"{tp.x:.3f}"))
            self._table.setItem(row, COL_Y,    QTableWidgetItem(f"{tp.y:.3f}"))
            self._table.setItem(row, COL_SIDE, QTableWidgetItem(tp.side))
            self._table.setItem(row, COL_DRL,  QTableWidgetItem(f"{tp.drill:.2f}"))
            clr = QColor("#143020") if "F" in tp.side else QColor("#201030")
            for c in range(6):
                it = self._table.item(row, c)
                if it:
                    it.setBackground(QBrush(clr))

    def _update_coverage(self) -> None:
        if not self._board:
            return
        rep = coverage_report(self._board, self._tps)
        pct = rep["coverage_pct"]
        self._cov_bar.setValue(int(pct))
        self._cov_lbl.setText(
            f"Pokrycie: {pct:.1f}%  |  "
            f"TP: {rep['tp_count']}  |  "
            f"Sieci pokryte: {rep['covered_nets']}/{rep['total_nets']}  |  "
            f"Front: {rep['f_count']}  Back: {rep['b_count']}"
        )
        self._stat_lbl.setText(
            f"Punktów testowych: {rep['tp_count']}  |  Pokrycie: {pct:.1f}%"
        )

        # Niepokryte sieci
        self._uncov_table.setRowCount(0)
        for net in rep["uncovered"]:
            row = self._uncov_table.rowCount()
            self._uncov_table.insertRow(row)
            item = QTableWidgetItem(net)
            item.setForeground(QColor("#e06040"))
            self._uncov_table.setItem(row, 0, item)

    def _on_sel(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._tps):
            tp = self._tps[row]
            self._canvas.set_data(self._board, self._tps, tp.net_name)

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for row in range(self._table.rowCount()):
            net_item = self._table.item(row, COL_NET)
            ref_item = self._table.item(row, COL_REF)
            net = net_item.text().lower() if net_item else ""
            ref = ref_item.text().lower() if ref_item else ""
            hide = bool(text) and text not in net and text not in ref
            self._table.setRowHidden(row, hide)

    def _add_tp(self) -> None:
        """Otwiera zakładkę Dodaj TP."""
        pass  # user navigates to tab 3

    def _create_tp(self) -> None:
        if not self._board:
            return
        ref = self._new_ref.text().strip()
        if not ref:
            QMessageBox.warning(self, "Błąd", "Podaj referencję TP.")
            return
        net  = self._new_net.text().strip()
        x    = self._new_x.value()
        y    = self._new_y.value()
        side = self._new_side.currentText()
        drl  = self._new_drl.value()

        # Utwórz komponent TP na płytce
        comp = Component(ref, "TestPoint", "TestPoint_Pad_D1.0mm", x, y)
        comp.layer = side
        pad = Pad("1", "thru_hole", "circle", 0, 0, drl, drl, net_name=net)
        comp.pads = [pad]
        self._board.components.append(comp)

        # Następna wolna referencja
        nums = [int(t.reference[2:]) for t in self._tps
                if t.reference.upper().startswith("TP") and t.reference[2:].isdigit()]
        next_n = max(nums, default=0) + 1
        self._new_ref.setText(f"TP{next_n + 1}")

        self._scan()
        QMessageBox.information(self, "Dodano", f"Punkt testowy {ref} ({net}) dodany do projektu.")

    def _del_tp(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._tps):
            return
        tp = self._tps[row]
        if not self._board:
            return
        self._board.components = [
            c for c in self._board.components if c.reference != tp.reference
        ]
        self._scan()

    def _export_csv(self) -> None:
        if not self._tps:
            QMessageBox.information(self, "Brak danych", "Brak punktów testowych do eksportu.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj CSV punktów testowych",
            "test_points.csv", "CSV (*.csv)"
        )
        if not path:
            return
        content = export_flying_probe_csv(self._tps)
        Path(path).write_text(content, encoding="utf-8-sig")
        QMessageBox.information(self, "Eksport", f"Zapisano {len(self._tps)} punktów:\n{path}")
