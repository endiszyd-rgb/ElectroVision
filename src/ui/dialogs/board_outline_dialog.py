"""Board Outline Wizard — generate standard PCB shapes on Edge.Cuts."""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QDoubleSpinBox, QComboBox, QFormLayout,
    QSplitter, QWidget, QCheckBox, QSpinBox, QMessageBox
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont
)

from src.core.project import Project
from src.core.models.pcb_board import GraphicLine, GraphicArc, PCBBoard


# ── Preview widget ─────────────────────────────────────────────────────────────

class _OutlinePreview(QWidget):
    BG    = QColor("#0d1117")
    EDGE  = QColor("#ffff40")
    GRID  = QColor("#1a2030")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines:  list[GraphicLine] = []
        self._arcs:   list[GraphicArc]  = []
        self._w_mm  = 80.0
        self._h_mm  = 60.0
        self.setMinimumSize(280, 200)

    def set_geometry(self, lines, arcs, w_mm, h_mm):
        self._lines = lines
        self._arcs  = arcs
        self._w_mm  = w_mm
        self._h_mm  = h_mm
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._lines and not self._arcs:
            p.setPen(QColor("#444"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak konturu")
            return

        margin = 20
        w_px = self.width()  - 2 * margin
        h_px = self.height() - 2 * margin
        scale = min(w_px / max(self._w_mm, 1), h_px / max(self._h_mm, 1))

        def tx(x): return margin + x * scale
        def ty(y): return margin + y * scale

        # Grid lines
        p.setPen(QPen(self.GRID, 1))
        grid_mm = 10.0
        x = 0.0
        while x <= self._w_mm:
            p.drawLine(int(tx(x)), margin, int(tx(x)), int(ty(self._h_mm)))
            x += grid_mm
        y = 0.0
        while y <= self._h_mm:
            p.drawLine(margin, int(ty(y)), int(tx(self._w_mm)), int(ty(y)))
            y += grid_mm

        # Outline
        p.setPen(QPen(self.EDGE, 2))
        for line in self._lines:
            p.drawLine(int(tx(line.x1)), int(ty(line.y1)),
                       int(tx(line.x2)), int(ty(line.y2)))
        for arc in self._arcs:
            cx, cy = tx(arc.x), ty(arc.y)
            sx, sy = tx(arc.start_x), ty(arc.start_y)
            r = math.hypot(sx - cx, sy - cy)
            start_angle_deg = math.degrees(math.atan2(cy - sy, sx - cx))
            span = arc.angle
            from PySide6.QtCore import QRectF
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            p.drawArc(rect, int(start_angle_deg * 16), int(span * 16))

        # Dimensions
        p.setPen(QColor("#888"))
        p.setFont(QFont("Consolas", 8))
        p.drawText(margin, self.height() - 4, f"{self._w_mm:.1f} × {self._h_mm:.1f} mm")


# ── Shape generators ───────────────────────────────────────────────────────────

def make_rectangle(w: float, h: float, corner_r: float = 0.0,
                   corner_count: int = 8) -> tuple[list, list]:
    """Generate rectangle outline lines and arcs. corner_r = 0 → sharp corners."""
    lines: list[GraphicLine] = []
    arcs:  list[GraphicArc]  = []
    lw = 0.05

    if corner_r <= 0 or corner_r * 2 >= min(w, h):
        # Sharp corners
        lines += [
            GraphicLine(0, 0, w, 0, lw, "Edge.Cuts"),
            GraphicLine(w, 0, w, h, lw, "Edge.Cuts"),
            GraphicLine(w, h, 0, h, lw, "Edge.Cuts"),
            GraphicLine(0, h, 0, 0, lw, "Edge.Cuts"),
        ]
    else:
        r = corner_r
        # Top edge
        lines.append(GraphicLine(r, 0, w - r, 0, lw, "Edge.Cuts"))
        # Right edge
        lines.append(GraphicLine(w, r, w, h - r, lw, "Edge.Cuts"))
        # Bottom edge
        lines.append(GraphicLine(w - r, h, r, h, lw, "Edge.Cuts"))
        # Left edge
        lines.append(GraphicLine(0, h - r, 0, r, lw, "Edge.Cuts"))
        # Corners (quarter circle arcs, approximated as line segments)
        def arc_pts(cx, cy, r, a_start, a_end, n):
            pts = []
            for i in range(n + 1):
                a = math.radians(a_start + (a_end - a_start) * i / n)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            return pts

        corners = [
            (r,     r,     180, 270),   # TL
            (w - r, r,     270, 360),   # TR
            (w - r, h - r, 0,   90),    # BR
            (r,     h - r, 90,  180),   # BL
        ]
        for cx, cy, a0, a1 in corners:
            pts = arc_pts(cx, cy, r, a0, a1, corner_count)
            for i in range(len(pts) - 1):
                lines.append(GraphicLine(pts[i][0], pts[i][1],
                                         pts[i+1][0], pts[i+1][1], lw, "Edge.Cuts"))

    return lines, arcs


def make_circle(cx: float, cy: float, radius: float,
                segments: int = 64) -> tuple[list, list]:
    lines: list[GraphicLine] = []
    lw = 0.05
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        lines.append(GraphicLine(
            cx + radius * math.cos(a0), cy + radius * math.sin(a0),
            cx + radius * math.cos(a1), cy + radius * math.sin(a1),
            lw, "Edge.Cuts"
        ))
    return lines, []


def make_oval(w: float, h: float) -> tuple[list, list]:
    """Oblong board: rectangle with semicircular ends."""
    lines: list[GraphicLine] = []
    r = min(w, h) / 2
    if w >= h:
        # Horizontal oval: semicircles on left/right
        lines.append(GraphicLine(r, 0, w - r, 0, 0.05, "Edge.Cuts"))
        lines.append(GraphicLine(r, h, w - r, h, 0.05, "Edge.Cuts"))
        cx_r, cx_l = w - r, r
        for cx, a0, a1 in [(cx_r, -90, 90), (cx_l, 90, 270)]:
            segs = 32
            for i in range(segs):
                a_s = math.radians(a0 + (a1 - a0) * i / segs)
                a_e = math.radians(a0 + (a1 - a0) * (i+1) / segs)
                lines.append(GraphicLine(
                    cx + r * math.cos(a_s), r + r * math.sin(a_s),
                    cx + r * math.cos(a_e), r + r * math.sin(a_e),
                    0.05, "Edge.Cuts"
                ))
    else:
        lines, _ = make_oval(h, w)  # rotate
    return lines, []


def make_mounting_holes(corners: list[tuple[float, float]],
                        hole_dia: float = 3.2) -> list[GraphicLine]:
    """Return circle outlines for mounting holes at given positions."""
    all_lines: list[GraphicLine] = []
    for (cx, cy) in corners:
        segs = 32
        r = hole_dia / 2
        for i in range(segs):
            a0 = 2 * math.pi * i / segs
            a1 = 2 * math.pi * (i + 1) / segs
            all_lines.append(GraphicLine(
                cx + r * math.cos(a0), cy + r * math.sin(a0),
                cx + r * math.cos(a1), cy + r * math.sin(a1),
                0.05, "Edge.Cuts"
            ))
    return all_lines


# ── Dialog ─────────────────────────────────────────────────────────────────────

class BoardOutlineDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Kreator konturu płytki (Edge.Cuts)")
        self.resize(740, 500)
        self._lines: list[GraphicLine] = []
        self._arcs:  list[GraphicArc]  = []
        self._build_ui()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: params ──────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        shape_box = QGroupBox("Kształt płytki")
        sf = QFormLayout(shape_box)

        self._shape = QComboBox()
        self._shape.addItems(["Prostokąt", "Prostokąt z zaokrąglonymi narożnikami",
                               "Okrąg", "Owal (oblong)"])
        self._shape.currentIndexChanged.connect(self._on_shape_change)
        sf.addRow("Kształt:", self._shape)

        self._w_spin = QDoubleSpinBox()
        self._w_spin.setRange(5, 600)
        self._w_spin.setValue(80)
        self._w_spin.setSuffix(" mm")
        self._w_spin.valueChanged.connect(self._update_preview)
        sf.addRow("Szerokość:", self._w_spin)

        self._h_spin = QDoubleSpinBox()
        self._h_spin.setRange(5, 600)
        self._h_spin.setValue(60)
        self._h_spin.setSuffix(" mm")
        self._h_spin.valueChanged.connect(self._update_preview)
        sf.addRow("Wysokość:", self._h_spin)

        self._r_spin = QDoubleSpinBox()
        self._r_spin.setRange(0, 50)
        self._r_spin.setValue(3.0)
        self._r_spin.setSuffix(" mm")
        self._r_spin.valueChanged.connect(self._update_preview)
        sf.addRow("Promień narożnika:", self._r_spin)
        ll.addWidget(shape_box)

        # Mounting holes
        mount_box = QGroupBox("Otwory montażowe")
        mf = QFormLayout(mount_box)

        self._mount_cb = QCheckBox("Dodaj otwory montażowe")
        self._mount_cb.toggled.connect(self._update_preview)
        mf.addRow(self._mount_cb)

        self._hole_dia = QDoubleSpinBox()
        self._hole_dia.setRange(1, 10)
        self._hole_dia.setValue(3.2)
        self._hole_dia.setSuffix(" mm")
        self._hole_dia.valueChanged.connect(self._update_preview)
        mf.addRow("Średnica otworu:", self._hole_dia)

        self._hole_margin = QDoubleSpinBox()
        self._hole_margin.setRange(1, 20)
        self._hole_margin.setValue(4.0)
        self._hole_margin.setSuffix(" mm")
        self._hole_margin.valueChanged.connect(self._update_preview)
        mf.addRow("Odstęp od krawędzi:", self._hole_margin)

        ll.addWidget(mount_box)
        ll.addStretch()

        info_box = QGroupBox("Popularne wymiary")
        il = QVBoxLayout(info_box)
        presets = [
            ("Arduino Uno (68.6×53.3)", 68.6, 53.3),
            ("Raspberry Pi (85×56)", 85, 56),
            ("ESP32 moduł (54×28)", 54, 28),
            ("Karta kredytowa (85.6×54)", 85.6, 54),
            ("Standardowa (100×80)", 100, 80),
        ]
        for label, w, h in presets:
            btn = QPushButton(label)
            cw, ch = w, h
            btn.clicked.connect(lambda _, x=cw, y=ch: self._apply_preset(x, y))
            il.addWidget(btn)
        ll.addWidget(info_box)

        splitter.addWidget(left)

        # ── Right: preview ────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self._preview = _OutlinePreview()
        rl.addWidget(self._preview, 1)

        self._dim_label = QLabel()
        self._dim_label.setAlignment(Qt.AlignCenter)
        self._dim_label.setStyleSheet("color:#aaa; font-size:10px; padding:4px;")
        rl.addWidget(self._dim_label)

        splitter.addWidget(right)
        splitter.setSizes([280, 460])
        layout.addWidget(splitter, 1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("✔ Zastosuj kontur do projektu")
        btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)
        btn_close = QPushButton("Anuluj")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_shape_change(self) -> None:
        idx = self._shape.currentIndex()
        self._r_spin.setEnabled(idx == 1)  # corner radius only for rounded rect
        self._update_preview()

    def _apply_preset(self, w: float, h: float) -> None:
        self._w_spin.setValue(w)
        self._h_spin.setValue(h)

    def _update_preview(self) -> None:
        w = self._w_spin.value()
        h = self._h_spin.value()
        r = self._r_spin.value()
        shape = self._shape.currentIndex()

        if shape == 0:
            lines, arcs = make_rectangle(w, h, 0)
        elif shape == 1:
            lines, arcs = make_rectangle(w, h, r)
        elif shape == 2:
            lines, arcs = make_circle(w / 2, w / 2, w / 2)
            h = w
        else:
            lines, arcs = make_oval(w, h)

        if self._mount_cb.isChecked():
            m = self._hole_margin.value()
            d = self._hole_dia.value()
            if shape == 2:
                holes = [(w / 2, w / 2)]  # center
            else:
                holes = [(m, m), (w - m, m), (w - m, h - m), (m, h - m)]
            lines += make_mounting_holes(holes, d)

        self._lines = lines
        self._arcs  = arcs
        self._preview.set_geometry(lines, arcs, w, h)
        area = w * h
        self._dim_label.setText(
            f"{w:.1f} × {h:.1f} mm  |  {area/100:.1f} cm²  |  "
            f"{len(lines)} segmentów"
        )

    def _apply(self) -> None:
        board = self._project.board if self._project else None
        if not board:
            QMessageBox.warning(self, "Brak projektu",
                                "Załaduj lub utwórz projekt PCB.")
            return

        # Remove existing Edge.Cuts
        board.graphic_lines = [l for l in board.graphic_lines
                                if l.layer != "Edge.Cuts"]
        board.graphic_arcs  = [a for a in board.graphic_arcs
                                if a.layer != "Edge.Cuts"]

        board.graphic_lines.extend(self._lines)
        board.graphic_arcs.extend(self._arcs)

        # Update board dimensions
        w = self._w_spin.value()
        h = self._h_spin.value()
        board.width_mm  = w
        board.height_mm = h

        QMessageBox.information(
            self, "Gotowe",
            f"Kontur {w:.1f}×{h:.1f}mm dodany do projektu.\n"
            f"Użyj Ctrl+Z (jeśli chcesz cofnąć) lub zapisz projekt."
        )
        self.accept()
