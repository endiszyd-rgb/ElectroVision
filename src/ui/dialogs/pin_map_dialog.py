"""Pin Map Dialog — show all pads/pins of a component with net assignments."""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QTextEdit, QSplitter, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont
)

from src.core.project import Project
from src.core.models.component import Component, Pad


# ── Footprint preview ──────────────────────────────────────────────────────────

class _FootprintView(QWidget):
    pad_hovered = Signal(str)   # pad number

    BG       = QColor("#0e1018")
    PAD_SMD  = QColor("#c87941")
    PAD_THT  = QColor("#60a0d0")
    PAD_SEL  = QColor("#60ff60")
    BODY     = QColor("#2a3020")
    BODY_BDR = QColor("#4a6040")
    TEXT     = QColor("#d0d0d0")
    GRID     = QColor("#151820")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._comp: Component | None = None
        self._hovered: str = ""
        self._selected: str = ""
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_component(self, comp: Component | None) -> None:
        self._comp = comp
        self._hovered = ""
        self._selected = ""
        self.update()

    def select_pad(self, number: str) -> None:
        self._selected = number
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._comp or not self._comp.pads:
            p.setPen(QColor("#555"))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak padów")
            return

        # Compute bounding box of pads
        xs = [pad.x for pad in self._comp.pads]
        ys = [pad.y for pad in self._comp.pads]
        ws = [max(pad.width, pad.height, 0.1) for pad in self._comp.pads]
        x_min = min(xs) - max(ws)
        x_max = max(xs) + max(ws)
        y_min = min(ys) - max(ws)
        y_max = max(ys) + max(ws)
        w_mm = max(x_max - x_min, 0.1)
        h_mm = max(y_max - y_min, 0.1)

        margin = 24
        W = self.width()  - 2 * margin
        H = self.height() - 2 * margin
        scale = min(W / w_mm, H / h_mm)

        def tx(x): return margin + (x - x_min) * scale
        def ty(y): return margin + (y - y_min) * scale

        # Component body (bounding box)
        p.setPen(QPen(self.BODY_BDR, 1))
        p.setBrush(QBrush(self.BODY))
        p.drawRect(int(tx(x_min + max(ws))), int(ty(y_min + max(ws))),
                   int(w_mm * scale - 2 * max(ws) * scale),
                   int(h_mm * scale - 2 * max(ws) * scale))

        # Reference label
        p.setPen(self.TEXT)
        p.setFont(QFont("Consolas", 8))
        p.drawText(QRectF(tx(x_min), ty(y_min), w_mm * scale, h_mm * scale),
                   Qt.AlignCenter, self._comp.reference)

        # Pads
        for pad in self._comp.pads:
            pw = max(2, pad.width * scale)
            ph = max(2, pad.height * scale)
            cx, cy = tx(pad.x), ty(pad.y)

            is_sel     = (pad.number == self._selected)
            is_hover   = (pad.number == self._hovered)
            fill_color = (self.PAD_SEL if is_sel else
                          (QColor("#ffffff") if is_hover else
                           (self.PAD_THT if pad.drill > 0 else self.PAD_SMD)))

            p.setPen(QPen(QColor("#ffffff") if is_sel else QColor("#000000"), 0.5))
            p.setBrush(QBrush(fill_color))

            if pad.shape == "circle" or pad.drill > 0:
                r = min(pw, ph) / 2
                p.drawEllipse(QPointF(cx, cy), r, r)
            else:
                p.drawRect(int(cx - pw/2), int(cy - ph/2), int(pw), int(ph))

            # Pad number
            p.setPen(QColor("#000") if not is_sel else QColor("#fff"))
            p.setFont(QFont("Arial", max(5, int(min(pw, ph) * 0.35))))
            p.drawText(QRectF(cx - pw/2, cy - ph/2, pw, ph),
                       Qt.AlignCenter, pad.number)

        # Net label next to first pin
        if self._comp.pads:
            for pad in self._comp.pads:
                if pad.net_name:
                    lx, ly = tx(pad.x) + max(2, pad.width * scale) / 2 + 2, ty(pad.y)
                    p.setPen(QColor("#80e080"))
                    p.setFont(QFont("Consolas", 6))
                    p.drawText(int(lx), int(ly), pad.net_name[:12])

    def mouseMoveEvent(self, e):
        if not self._comp or not self._comp.pads:
            return
        xs = [p.x for p in self._comp.pads]
        ys = [p.y for p in self._comp.pads]
        ws = [max(p.width, p.height, 0.1) for p in self._comp.pads]
        x_min = min(xs) - max(ws); x_max = max(xs) + max(ws)
        y_min = min(ys) - max(ws); y_max = max(ys) + max(ws)
        w_mm = max(x_max - x_min, 0.1); h_mm = max(y_max - y_min, 0.1)
        margin = 24
        W = self.width() - 2 * margin; H = self.height() - 2 * margin
        scale = min(W / w_mm, H / h_mm)

        mx, my = e.position().x(), e.position().y()
        hit = ""
        for pad in self._comp.pads:
            cx = margin + (pad.x - x_min) * scale
            cy = margin + (pad.y - y_min) * scale
            r = max(4, min(pad.width, pad.height) * scale / 2 + 2)
            if math.hypot(mx - cx, my - cy) < r:
                hit = pad.number
                break
        if hit != self._hovered:
            self._hovered = hit
            if hit:
                self.pad_hovered.emit(hit)
            self.update()


# ── Dialog ─────────────────────────────────────────────────────────────────────

class PinMapDialog(QDialog):
    net_highlight_requested = Signal(str)

    def __init__(self, project: Project, comp: Component | None = None, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Mapa pinów / padów")
        self.resize(780, 520)
        self._build_ui()
        self._populate_comp_list()
        if comp:
            self._select_comp(comp.reference)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Component selector ────────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Komponent:"))
        self._comp_combo = QComboBox()
        self._comp_combo.currentIndexChanged.connect(self._on_comp_selected)
        top.addWidget(self._comp_combo, 1)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: footprint preview ───────────────────────────────────────────
        self._fp_view = _FootprintView()
        self._fp_view.pad_hovered.connect(self._on_pad_hovered)
        splitter.addWidget(self._fp_view)

        # ── Right: pad table ──────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color:#aaa; font-size:10px; padding:2px;")
        rl.addWidget(self._info_label)

        self._pad_table = QTableWidget()
        self._pad_table.setColumnCount(5)
        self._pad_table.setHorizontalHeaderLabels(
            ["Pin #", "Sieć", "Typ", "Kształt", "Rozmiar (mm)"]
        )
        self._pad_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._pad_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pad_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._pad_table.itemSelectionChanged.connect(self._on_pad_selected)
        rl.addWidget(self._pad_table)

        # Net info
        net_box = QGroupBox("Sieć wybranego pinu")
        nl = QVBoxLayout(net_box)
        self._net_label = QLabel("—")
        self._net_label.setFont(QFont("Consolas", 10))
        self._net_label.setStyleSheet("color:#60e060;")
        nl.addWidget(self._net_label)

        btn_hl = QPushButton("Podświetl sieć w edytorze PCB")
        btn_hl.clicked.connect(self._highlight_net)
        nl.addWidget(btn_hl)
        rl.addWidget(net_box)

        splitter.addWidget(right)
        splitter.setSizes([280, 500])
        layout.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _populate_comp_list(self) -> None:
        self._comp_combo.blockSignals(True)
        self._comp_combo.clear()
        board = self._project.board if self._project else None
        if board:
            for comp in sorted(board.components, key=lambda c: c.reference):
                self._comp_combo.addItem(f"{comp.reference} — {comp.value}", comp.reference)
        self._comp_combo.blockSignals(False)
        self._on_comp_selected()

    def _select_comp(self, ref: str) -> None:
        for i in range(self._comp_combo.count()):
            if self._comp_combo.itemData(i) == ref:
                self._comp_combo.setCurrentIndex(i)
                return

    def _current_comp(self) -> Component | None:
        ref = self._comp_combo.currentData()
        board = self._project.board if self._project else None
        if not board or not ref:
            return None
        return next((c for c in board.components if c.reference == ref), None)

    def _on_comp_selected(self) -> None:
        comp = self._current_comp()
        self._fp_view.set_component(comp)
        self._pad_table.setRowCount(0)
        if not comp:
            self._info_label.setText("Brak komponentu")
            return

        self._info_label.setText(
            f"<b>{comp.reference}</b> — {comp.value}  |  "
            f"Footprint: {comp.footprint.split(':')[-1]}  |  "
            f"{len(comp.pads)} padów  |  Warstwa: {comp.layer}"
        )
        self._info_label.setTextFormat(Qt.RichText)

        nets_used = set()
        for pad in sorted(comp.pads, key=lambda p: p.number):
            row = self._pad_table.rowCount()
            self._pad_table.insertRow(row)
            self._pad_table.setItem(row, 0, QTableWidgetItem(pad.number))
            net_item = QTableWidgetItem(pad.net_name or "—")
            if pad.net_name:
                net_item.setForeground(QColor("#60e060"))
                nets_used.add(pad.net_name)
            else:
                net_item.setForeground(QColor("#888"))
            self._pad_table.setItem(row, 1, net_item)
            self._pad_table.setItem(row, 2, QTableWidgetItem(pad.pad_type))
            self._pad_table.setItem(row, 3, QTableWidgetItem(pad.shape))
            size_str = f"{pad.width:.3f}×{pad.height:.3f}"
            if pad.drill > 0:
                size_str += f" drill={pad.drill:.3f}"
            self._pad_table.setItem(row, 4, QTableWidgetItem(size_str))

    def _on_pad_hovered(self, number: str) -> None:
        for row in range(self._pad_table.rowCount()):
            item = self._pad_table.item(row, 0)
            if item and item.text() == number:
                self._pad_table.selectRow(row)
                break

    def _on_pad_selected(self) -> None:
        row = self._pad_table.currentRow()
        if row < 0:
            return
        num = (self._pad_table.item(row, 0) or QTableWidgetItem("")).text()
        net = (self._pad_table.item(row, 1) or QTableWidgetItem("")).text()
        self._net_label.setText(net if net != "—" else "Brak sieci")
        self._fp_view.select_pad(num)

    def _highlight_net(self) -> None:
        net = self._net_label.text()
        if net and net not in ("Brak sieci", "—"):
            self.net_highlight_requested.emit(net)
