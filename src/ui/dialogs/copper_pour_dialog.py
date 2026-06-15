"""Copper Pour Analyser & Zone Manager — statystyki i edytor miedzianych wylewy."""
from __future__ import annotations
import math
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QLineEdit,
    QSplitter, QWidget, QTextEdit, QSpinBox, QProgressBar,
    QMessageBox, QTabWidget
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF, QFont

from src.core.project import Project
from src.core.models.pcb_board import CopperZone, PCBBoard


# ── Analiza geometrii strefy ────────────────────────────────────────────────────

@dataclass
class ZoneStats:
    zone: CopperZone
    area_mm2: float
    perimeter_mm: float
    pad_count: int          # pady wewnątrz strefy
    island_count: int = 1   # uproszczone — 1 per strefa

    @property
    def fill_label(self) -> str:
        return f"{self.area_mm2:.1f} mm²"


def _polygon_area(pts: list) -> float:
    """Shoelace formula."""
    n = len(pts)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _polygon_perimeter(pts: list) -> float:
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def _point_in_polygon(px: float, py: float, pts: list) -> bool:
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def analyse_zones(board: PCBBoard) -> list[ZoneStats]:
    stats = []
    for zone in board.zones:
        pts = zone.points
        area = _polygon_area(pts)
        peri = _polygon_perimeter(pts)
        # count pads inside zone
        pad_count = 0
        for comp in board.components:
            for pad in comp.pads:
                px = comp.x + pad.x
                py = comp.y + pad.y
                if _point_in_polygon(px, py, pts):
                    pad_count += 1
        stats.append(ZoneStats(zone=zone, area_mm2=area, perimeter_mm=peri, pad_count=pad_count))
    return stats


def board_copper_summary(board: PCBBoard, stats: list[ZoneStats]) -> dict:
    """Podsumowanie miedzi per warstwa."""
    layers: dict[str, float] = {}
    for s in stats:
        layers[s.zone.layer] = layers.get(s.zone.layer, 0.0) + s.area_mm2
    bb = board.bounding_box
    board_area = (bb[2] - bb[0]) * (bb[3] - bb[1])
    return {
        "layers":     layers,
        "board_area": board_area,
        "total_zone_area": sum(s.area_mm2 for s in stats),
        "zone_count":  len(stats),
    }


# ── Podgląd canvas ──────────────────────────────────────────────────────────────

class _ZoneCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: PCBBoard | None = None
        self._stats: list[ZoneStats] = []
        self._sel: int = -1
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background: #1a1a2e;")

    def set_data(self, board: PCBBoard, stats: list[ZoneStats], sel: int = -1) -> None:
        self._board = board
        self._stats = stats
        self._sel = sel
        self.update()

    def paintEvent(self, event) -> None:
        if not self._board:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bb = self._board.bounding_box
        bw = bb[2] - bb[0] or 100
        bh = bb[3] - bb[1] or 100
        W, H = self.width(), self.height()
        margin = 20
        sx = (W - 2 * margin) / bw
        sy = (H - 2 * margin) / bh
        scale = min(sx, sy)
        ox = margin - bb[0] * scale
        oy = margin - bb[1] * scale

        def mm(x, y):
            return QPointF(ox + x * scale, oy + y * scale)

        # Board outline
        p.setPen(QPen(QColor("#f0c040"), 1.5))
        p.setBrush(Qt.NoBrush)
        for gl in self._board.graphic_lines:
            if gl.layer == "Edge.Cuts":
                a = mm(gl.x1, gl.y1)
                b = mm(gl.x2, gl.y2)
                p.drawLine(a, b)

        # Zones
        _LAYER_CLR = {
            "F.Cu": QColor(180, 40, 40, 110),
            "B.Cu": QColor(40, 100, 180, 110),
            "In1.Cu": QColor(40, 160, 80, 100),
            "In2.Cu": QColor(160, 80, 160, 100),
        }
        for i, s in enumerate(self._stats):
            pts = s.zone.points
            if len(pts) < 3:
                continue
            poly = QPolygonF([mm(x, y) for x, y in pts])
            clr = _LAYER_CLR.get(s.zone.layer, QColor(100, 100, 100, 100))
            p.setBrush(QBrush(clr))
            if i == self._sel:
                p.setPen(QPen(QColor("#ffffff"), 2))
            else:
                p.setPen(QPen(QColor(200, 200, 200, 60), 0.5))
            p.drawPolygon(poly)

        # Traces
        p.setPen(QPen(QColor("#c87840"), 0.8))
        for t in self._board.traces:
            p.drawLine(mm(t.x1, t.y1), mm(t.x2, t.y2))

        p.end()


# ── Dialog ──────────────────────────────────────────────────────────────────────

_LAYERS = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"]
_NETS_PLACEHOLDER = "(wszystkie sieci zasilające)"


class CopperPourDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._board = project.board
        self._stats: list[ZoneStats] = []
        self.setWindowTitle("Analizator miedzianych wylewy (Copper Pour)")
        self.resize(1050, 640)
        self._build_ui()
        self._analyse()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        tabs = QTabWidget()

        # ── Tab 1: Statystyki ─────────────────────────────────────────────────
        stat_w = QWidget()
        sl = QHBoxLayout(stat_w)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Strefy miedziowe:"))

        self._zone_table = QTableWidget()
        self._zone_table.setColumnCount(6)
        self._zone_table.setHorizontalHeaderLabels(
            ["Warstwa", "Sieć", "Pole [mm²]", "Obwód [mm]", "Pady", "Prześwit"]
        )
        hdr = self._zone_table.horizontalHeader()
        for i in range(6):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._zone_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._zone_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._zone_table.itemSelectionChanged.connect(self._on_zone_sel)
        ll.addWidget(self._zone_table, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Dodaj strefę")
        btn_add.clicked.connect(self._add_zone)
        btn_del = QPushButton("− Usuń")
        btn_del.clicked.connect(self._del_zone)
        btn_refresh = QPushButton("⟳ Przelicz")
        btn_refresh.clicked.connect(self._analyse)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_refresh)
        ll.addLayout(btn_row)

        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        self._canvas = _ZoneCanvas()
        rl.addWidget(self._canvas, 1)

        # Summary box
        summary = QGroupBox("Podsumowanie miedzi")
        sfm = QFormLayout(summary)
        self._lbl_total_area = QLabel("—")
        self._lbl_board_area = QLabel("—")
        self._lbl_fill_pct = QLabel("—")
        self._lbl_zone_count = QLabel("—")
        sfm.addRow("Łączne pole stref:", self._lbl_total_area)
        sfm.addRow("Pole płytki:", self._lbl_board_area)
        sfm.addRow("Wypełnienie miedzi:", self._lbl_fill_pct)
        sfm.addRow("Liczba stref:", self._lbl_zone_count)

        self._fill_bar = QProgressBar()
        self._fill_bar.setRange(0, 100)
        self._fill_bar.setStyleSheet(
            "QProgressBar { background: #222; border: 1px solid #444; }"
            "QProgressBar::chunk { background: #b04020; }"
        )
        sfm.addRow("", self._fill_bar)

        self._layer_lbl = QLabel()
        self._layer_lbl.setStyleSheet("color: #aaa; font-size: 10px;")
        self._layer_lbl.setWordWrap(True)
        sfm.addRow("Per warstwa:", self._layer_lbl)
        rl.addWidget(summary)

        splitter.addWidget(right)
        splitter.setSizes([380, 570])
        sl.addWidget(splitter)
        tabs.addTab(stat_w, "📊 Statystyki stref")

        # ── Tab 2: Edytor strefy ──────────────────────────────────────────────
        edit_w = QWidget()
        el = QVBoxLayout(edit_w)

        el.addWidget(QLabel("Wybierz strefę w tabeli lub dodaj nową, a następnie edytuj parametry:"))

        form = QGroupBox("Parametry strefy")
        ff = QFormLayout(form)

        self._e_layer = QComboBox()
        self._e_layer.addItems(_LAYERS)
        ff.addRow("Warstwa:", self._e_layer)

        self._e_net = QLineEdit()
        self._e_net.setPlaceholderText("np. GND, VCC, AGND")
        ff.addRow("Sieć:", self._e_net)

        self._e_clearance = QDoubleSpinBox()
        self._e_clearance.setRange(0.05, 2.0)
        self._e_clearance.setSuffix(" mm")
        self._e_clearance.setSingleStep(0.05)
        self._e_clearance.setValue(0.2)
        ff.addRow("Prześwit do miedzi:", self._e_clearance)

        self._e_priority = QSpinBox()
        self._e_priority.setRange(0, 10)
        ff.addRow("Priorytet wypełnienia:", self._e_priority)

        self._e_points = QTextEdit()
        self._e_points.setPlaceholderText(
            "Wierzchołki poligonu — jeden na linię: X,Y\n"
            "Przykład:\n0,0\n100,0\n100,80\n0,80"
        )
        self._e_points.setMaximumHeight(140)
        ff.addRow("Wierzchołki [mm]:", self._e_points)

        el.addWidget(form)

        e_btns = QHBoxLayout()
        btn_apply_edit = QPushButton("✔ Zastosuj zmiany")
        btn_apply_edit.setStyleSheet("background: #1a4a8f; color: white;")
        btn_apply_edit.clicked.connect(self._apply_edit)
        btn_rect = QPushButton("⬜ Wstaw prostokąt z płytki")
        btn_rect.clicked.connect(self._insert_board_rect)
        e_btns.addWidget(btn_rect)
        e_btns.addWidget(btn_apply_edit)
        e_btns.addStretch()
        el.addLayout(e_btns)
        el.addStretch()

        tabs.addTab(edit_w, "✏ Edytor strefy")

        # ── Tab 3: Wskazówki DFM ──────────────────────────────────────────────
        dfm_w = QWidget()
        dl = QVBoxLayout(dfm_w)
        self._dfm_text = QTextEdit()
        self._dfm_text.setReadOnly(True)
        self._dfm_text.setStyleSheet(
            "background: #111; color: #ddd; font-family: monospace; font-size: 11px;"
        )
        dl.addWidget(self._dfm_text)
        tabs.addTab(dfm_w, "🏭 Wskazówki DFM")

        root.addWidget(tabs, 1)

        # ── Bottom ────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _analyse(self) -> None:
        if not self._board:
            return
        self._stats = analyse_zones(self._board)
        self._populate_table()
        self._update_summary()
        self._canvas.set_data(self._board, self._stats, -1)
        self._build_dfm_report()

    def _populate_table(self) -> None:
        self._zone_table.setRowCount(0)
        for s in self._stats:
            row = self._zone_table.rowCount()
            self._zone_table.insertRow(row)
            self._zone_table.setItem(row, 0, QTableWidgetItem(s.zone.layer))
            self._zone_table.setItem(row, 1, QTableWidgetItem(s.zone.net_name or "—"))
            self._zone_table.setItem(row, 2, QTableWidgetItem(f"{s.area_mm2:.2f}"))
            self._zone_table.setItem(row, 3, QTableWidgetItem(f"{s.perimeter_mm:.1f}"))
            self._zone_table.setItem(row, 4, QTableWidgetItem(str(s.pad_count)))
            self._zone_table.setItem(row, 5, QTableWidgetItem(f"{s.zone.clearance:.2f} mm"))

    def _update_summary(self) -> None:
        summary = board_copper_summary(self._board, self._stats)
        total = summary["total_zone_area"]
        board = summary["board_area"]
        pct = (total / board * 100) if board > 0 else 0

        self._lbl_total_area.setText(f"{total:.1f} mm²")
        self._lbl_board_area.setText(f"{board:.1f} mm²")
        self._lbl_fill_pct.setText(f"{pct:.1f} %")
        self._lbl_zone_count.setText(str(summary["zone_count"]))
        self._fill_bar.setValue(int(min(pct, 100)))

        layer_parts = []
        for lyr, area in sorted(summary["layers"].items()):
            pct_l = area / board * 100 if board > 0 else 0
            layer_parts.append(f"{lyr}: {area:.1f} mm² ({pct_l:.1f}%)")
        self._layer_lbl.setText("  |  ".join(layer_parts) or "—")

    def _on_zone_sel(self) -> None:
        idx = self._zone_table.currentRow()
        if idx < 0 or idx >= len(self._stats):
            return
        self._canvas.set_data(self._board, self._stats, idx)
        # fill editor
        z = self._stats[idx].zone
        ci = self._e_layer.findText(z.layer)
        if ci >= 0:
            self._e_layer.setCurrentIndex(ci)
        self._e_net.setText(z.net_name)
        self._e_clearance.setValue(z.clearance)
        self._e_priority.setValue(z.priority)
        self._e_points.setPlainText(
            "\n".join(f"{x:.3f},{y:.3f}" for x, y in z.points)
        )

    def _add_zone(self) -> None:
        bb = self._board.bounding_box if self._board else (0, 0, 100, 80)
        zone = CopperZone(
            points=[(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3])],
            net_name="GND",
            layer="F.Cu",
            clearance=0.2,
        )
        if self._board:
            self._board.zones.append(zone)
        self._analyse()
        self._zone_table.selectRow(self._zone_table.rowCount() - 1)

    def _del_zone(self) -> None:
        idx = self._zone_table.currentRow()
        if idx < 0 or not self._board or idx >= len(self._board.zones):
            return
        self._board.zones.pop(idx)
        self._analyse()

    def _apply_edit(self) -> None:
        idx = self._zone_table.currentRow()
        if idx < 0 or not self._board or idx >= len(self._board.zones):
            QMessageBox.warning(self, "Brak wyboru", "Wybierz strefę w tabeli.")
            return
        z = self._board.zones[idx]
        z.layer = self._e_layer.currentText()
        z.net_name = self._e_net.text().strip()
        z.clearance = self._e_clearance.value()
        z.priority = self._e_priority.value()
        pts = []
        for line in self._e_points.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                x, y = line.split(",")
                pts.append((float(x), float(y)))
            except ValueError:
                QMessageBox.warning(self, "Błąd", f"Nieprawidłowa linia: '{line}'")
                return
        if len(pts) < 3:
            QMessageBox.warning(self, "Błąd", "Potrzeba co najmniej 3 wierzchołków.")
            return
        z.points = pts
        self._analyse()

    def _insert_board_rect(self) -> None:
        if not self._board:
            return
        bb = self._board.bounding_box
        self._e_points.setPlainText(
            f"{bb[0]:.3f},{bb[1]:.3f}\n"
            f"{bb[2]:.3f},{bb[1]:.3f}\n"
            f"{bb[2]:.3f},{bb[3]:.3f}\n"
            f"{bb[0]:.3f},{bb[3]:.3f}"
        )

    def _build_dfm_report(self) -> None:
        lines = ["=== Wskazówki DFM — Miedziowe wylewy ===\n"]
        if not self._stats:
            lines.append("Brak stref miedziowych w projekcie.\n")
            lines.append("Zalecenie: dodaj wylewy GND na F.Cu i B.Cu\n"
                         "  → zmniejszają impedancję powrotu, ekranują EMI\n"
                         "     i poprawiają odprowadzanie ciepła.\n")
        else:
            summary = board_copper_summary(self._board, self._stats)
            board_area = summary["board_area"]
            total = summary["total_zone_area"]
            pct = total / board_area * 100 if board_area > 0 else 0

            if pct < 30:
                lines.append(f"⚠  Niskie wypełnienie miedzi: {pct:.1f}%\n"
                             "   Zalecenie: dodaj strefy GND na B.Cu lub F.Cu.\n")
            elif pct > 80:
                lines.append(f"ℹ  Bardzo wysokie wypełnienie: {pct:.1f}%\n"
                             "   Sprawdź, czy nie powstaną mosty (solder bridges)\n"
                             "   przy zalewaniu płytki. Zwiększ prześwity termiczne.\n")
            else:
                lines.append(f"✔  Wypełnienie miedzi OK: {pct:.1f}%\n")

            layers = summary["layers"]
            if "F.Cu" in layers and "B.Cu" not in layers:
                lines.append("⚠  Brak wylewki GND na B.Cu.\n"
                             "   Dodaj strefę GND na B.Cu — paruje się z F.Cu\n"
                             "   tworząc płaszczyznę referencyjną.\n")

            for s in self._stats:
                if s.zone.clearance < 0.1:
                    lines.append(f"⚠  Strefa {s.zone.layer}/{s.zone.net_name}: prześwit {s.zone.clearance} mm < 0.1 mm\n"
                                 "   Ryzyko zwarcia przy produkcji.\n")
                if s.area_mm2 < 1.0:
                    lines.append(f"ℹ  Strefa {s.zone.layer}/{s.zone.net_name}: małe pole {s.area_mm2:.2f} mm²\n"
                                 "   Sprawdź, czy strefa jest intencjonalna.\n")
                if s.pad_count == 0 and s.zone.net_name in ("GND", "AGND", "PGND"):
                    lines.append(f"⚠  Strefa GND na {s.zone.layer} nie zawiera żadnych padów.\n"
                                 "   Upewnij się, że pady GND leżą w obszarze strefy.\n")

            lines.append("\n=== Reguły ogólne ===\n")
            lines.append("• Prześwit termiczny (thermal relief): 0.5 mm szczelina, 4 ramiona\n")
            lines.append("• Minimalna szerokość ramion thermal relief: 0.25 mm\n")
            lines.append("• Nie łącz dwóch stref o tej samej sieci przez cienkie mostki\n")
            lines.append("• Wyższy priorytet = strefa nadpisuje sąsiednie na tej samej warstwie\n")

        self._dfm_text.setPlainText("".join(lines))
