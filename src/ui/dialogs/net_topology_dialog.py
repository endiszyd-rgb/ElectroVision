"""Net Topology Dialog — force-directed graph of component connectivity."""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QGroupBox, QFormLayout, QSlider, QCheckBox,
    QWidget, QSizePolicy, QSplitter, QTextEdit, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QMouseEvent, QTransform
)

from src.core.project import Project
from src.core.models.component import Component


# ── Layout engine ─────────────────────────────────────────────────────────────

@dataclass
class _Node:
    ref: str
    comp_type: str
    value: str
    nets: set = field(default_factory=set)
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0

    def color(self) -> QColor:
        return _TYPE_COLORS.get(self.comp_type, QColor("#607090"))

    def width(self) -> float:
        return max(40, len(self.ref) * 8 + 12)

    def height(self) -> float:
        return 28.0


_TYPE_COLORS = {
    "ic":        QColor("#2a6090"),
    "resistor":  QColor("#6a4020"),
    "capacitor": QColor("#205040"),
    "inductor":  QColor("#504020"),
    "led":       QColor("#405000"),
    "diode":     QColor("#602040"),
    "transistor":QColor("#204060"),
    "crystal":   QColor("#304050"),
    "connector": QColor("#503020"),
    "switch":    QColor("#203050"),
}


def _run_layout(nodes: list[_Node], iterations: int = 120) -> None:
    """Fruchterman–Reingold spring layout."""
    n = len(nodes)
    if n == 0:
        return
    area = max(n * 2500.0, 40000.0)
    k = math.sqrt(area / n)

    def repel(d: float) -> float:
        return k * k / (d + 0.01)

    def attract(d: float) -> float:
        return d * d / k

    for step in range(iterations):
        t = max(10.0, 200.0 * (1 - step / iterations))

        # Repulsion between all pairs
        for i, a in enumerate(nodes):
            fx, fy = 0.0, 0.0
            for j, b in enumerate(nodes):
                if i == j:
                    continue
                dx, dy = a.x - b.x, a.y - b.y
                dist = math.hypot(dx, dy) or 0.01
                f = repel(dist)
                fx += dx / dist * f
                fy += dy / dist * f
            a.vx = (a.vx + fx) * 0.85
            a.vy = (a.vy + fy) * 0.85

        # Attraction along shared-net edges
        # Build net→nodes mapping
        net_map: dict[str, list[int]] = {}
        for i, nd in enumerate(nodes):
            for net in nd.nets:
                net_map.setdefault(net, []).append(i)

        for members in net_map.values():
            for p in range(len(members)):
                for q in range(p + 1, len(members)):
                    a, b = nodes[members[p]], nodes[members[q]]
                    dx, dy = b.x - a.x, b.y - a.y
                    dist = math.hypot(dx, dy) or 0.01
                    f = attract(dist)
                    a.vx += dx / dist * f
                    a.vy += dy / dist * f
                    b.vx -= dx / dist * f
                    b.vy -= dy / dist * f

        # Apply velocity with temperature cap
        for nd in nodes:
            speed = math.hypot(nd.vx, nd.vy)
            if speed > t:
                nd.vx = nd.vx / speed * t
                nd.vy = nd.vy / speed * t
            nd.x += nd.vx
            nd.y += nd.vy


def _build_graph(board, max_nodes: int = 60) -> tuple[list[_Node], dict[str, list[str]]]:
    """Build node list and net→refs mapping from board data."""
    nodes: list[_Node] = []
    net_refs: dict[str, list[str]] = {}

    for comp in board.components[:max_nodes]:
        nd = _Node(ref=comp.reference, comp_type=comp.component_type, value=comp.value)
        for pad in comp.pads:
            if pad.net_name:
                nd.nets.add(pad.net_name)
                net_refs.setdefault(pad.net_name, []).append(comp.reference)
        nodes.append(nd)

    # Random initial positions in a circle
    r = max(80.0, len(nodes) * 12.0)
    for i, nd in enumerate(nodes):
        angle = 2 * math.pi * i / max(len(nodes), 1)
        nd.x = r * math.cos(angle) + random.uniform(-20, 20)
        nd.y = r * math.sin(angle) + random.uniform(-20, 20)

    return nodes, net_refs


# ── Canvas widget ─────────────────────────────────────────────────────────────

class _TopoCanvas(QWidget):
    node_clicked = Signal(str)    # ref
    edge_clicked = Signal(str)    # net name

    BG        = QColor("#0d1117")
    EDGE_DEF  = QColor("#2a3a50")
    EDGE_PWR  = QColor("#804020")
    EDGE_GND  = QColor("#205040")
    EDGE_HL   = QColor("#e0c060")
    NODE_BDR  = QColor("#60a0d0")
    NODE_SEL  = QColor("#60ff80")
    TEXT_CLR  = QColor("#d0d0d0")
    GRID      = QColor("#12161e")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes:    list[_Node] = []
        self._net_refs: dict[str, list[str]] = {}
        self._scale   = 1.0
        self._offset  = QPointF(0, 0)
        self._drag_start: QPointF | None = None
        self._drag_off   = QPointF(0, 0)
        self._sel_ref    = ""
        self._sel_net    = ""
        self._filter_net = ""
        self._show_power = True
        self._show_gnd   = True
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_data(self, nodes, net_refs) -> None:
        self._nodes    = nodes
        self._net_refs = net_refs
        self._fit_all()
        self.update()

    def set_filter_net(self, net: str) -> None:
        self._filter_net = net
        self.update()

    def set_show_power(self, v: bool) -> None:
        self._show_power = v
        self.update()

    def set_show_gnd(self, v: bool) -> None:
        self._show_gnd = v
        self.update()

    def select_ref(self, ref: str) -> None:
        self._sel_ref = ref
        self.update()

    def _fit_all(self) -> None:
        if not self._nodes:
            return
        xs = [nd.x for nd in self._nodes]
        ys = [nd.y for nd in self._nodes]
        margin = 60
        w_data = max(max(xs) - min(xs), 1)
        h_data = max(max(ys) - min(ys), 1)
        self._scale = min(
            (self.width()  - margin * 2) / w_data,
            (self.height() - margin * 2) / h_data,
            2.5
        )
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        self._offset = QPointF(
            self.width()  / 2 - cx * self._scale,
            self.height() / 2 - cy * self._scale,
        )

    def _tx(self, x: float) -> float:
        return x * self._scale + self._offset.x()

    def _ty(self, y: float) -> float:
        return y * self._scale + self._offset.y()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._nodes:
            p.setPen(QColor("#555"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Brak danych — zaimportuj projekt i kliknij Generuj Graf")
            return

        node_map = {nd.ref: nd for nd in self._nodes}

        # ── Draw edges ────────────────────────────────────────────────────────
        p.setPen(QPen(self.EDGE_DEF, 1))
        for net, refs in self._net_refs.items():
            if len(refs) < 2:
                continue

            # Visibility filters
            is_pwr = "VCC" in net.upper() or "VDD" in net.upper() or "VIN" in net.upper() or "VBUS" in net.upper()
            is_gnd = "GND" in net.upper() or "AGND" in net.upper() or "0V" == net
            if is_pwr and not self._show_power:
                continue
            if is_gnd and not self._show_gnd:
                continue
            if self._filter_net and net != self._filter_net:
                continue

            highlighted = (net == self._sel_net or net == self._filter_net)
            if highlighted:
                color = self.EDGE_HL
                width = 2
            elif is_gnd:
                color = self.EDGE_GND
                width = 1
            elif is_pwr:
                color = self.EDGE_PWR
                width = 1
            else:
                color = self.EDGE_DEF
                width = 1

            p.setPen(QPen(color, width))

            # Draw hub-and-spoke: each ref connects to next in chain
            valid = [r for r in refs if r in node_map]
            for i in range(len(valid) - 1):
                a = node_map[valid[i]]
                b = node_map[valid[i + 1]]
                ax, ay = self._tx(a.x), self._ty(a.y)
                bx, by = self._tx(b.x), self._ty(b.y)
                p.drawLine(int(ax), int(ay), int(bx), int(by))

            # Net label at midpoint of first edge
            if valid and len(valid) >= 2 and (highlighted or self._filter_net == net):
                a, b = node_map[valid[0]], node_map[valid[1]]
                mx = (self._tx(a.x) + self._tx(b.x)) / 2
                my = (self._ty(a.y) + self._ty(b.y)) / 2
                p.setPen(self.EDGE_HL)
                p.setFont(QFont("Consolas", 7))
                p.drawText(int(mx + 3), int(my - 3), net)

        # ── Draw nodes ────────────────────────────────────────────────────────
        font_node = QFont("Consolas", 8)
        font_node.setBold(True)
        p.setFont(font_node)

        for nd in self._nodes:
            nx = self._tx(nd.x)
            ny = self._ty(nd.y)
            nw = nd.width() * self._scale
            nh = nd.height() * self._scale
            rect = QRectF(nx - nw / 2, ny - nh / 2, nw, nh)

            is_sel = (nd.ref == self._sel_ref)
            fill   = nd.color().lighter(130) if is_sel else nd.color()
            border = self.NODE_SEL if is_sel else self.NODE_BDR

            p.setPen(QPen(border, 2 if is_sel else 1))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(rect, 4 * self._scale, 4 * self._scale)

            # Label: reference
            p.setPen(QColor("#ffffff") if is_sel else self.TEXT_CLR)
            p.setFont(font_node)
            p.drawText(rect, Qt.AlignCenter, nd.ref)

            # Small type indicator below ref
            if self._scale > 0.7:
                p.setPen(QColor("#808080"))
                p.setFont(QFont("Arial", 6))
                val_str = nd.value[:10] if nd.value else ""
                p.drawText(
                    QRectF(nx - nw / 2, ny + nh / 2 + 1, nw, 14),
                    Qt.AlignCenter, val_str
                )

    def wheelEvent(self, e: QWheelEvent) -> None:
        factor = 1.12 if e.angleDelta().y() > 0 else 1 / 1.12
        pos = e.position()
        self._offset = QPointF(
            pos.x() - (pos.x() - self._offset.x()) * factor,
            pos.y() - (pos.y() - self._offset.y()) * factor,
        )
        self._scale *= factor
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            hit = self._node_at(e.position())
            if hit:
                self._sel_ref = hit.ref
                self._sel_net = ""
                self.node_clicked.emit(hit.ref)
                self.update()
                return
            net = self._net_at(e.position())
            if net:
                self._sel_net = net
                self._sel_ref = ""
                self.edge_clicked.emit(net)
                self.update()
                return
        if e.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._drag_start = e.position()
            self._drag_off   = QPointF(self._offset)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start is not None:
            delta = e.position() - self._drag_start
            self._offset = QPointF(
                self._drag_off.x() + delta.x(),
                self._drag_off.y() + delta.y(),
            )
            self.update()

    def mouseReleaseEvent(self, _) -> None:
        self._drag_start = None

    def _node_at(self, pos: QPointF) -> _Node | None:
        for nd in self._nodes:
            nx, ny = self._tx(nd.x), self._ty(nd.y)
            nw = nd.width() * self._scale
            nh = nd.height() * self._scale
            if abs(pos.x() - nx) < nw / 2 and abs(pos.y() - ny) < nh / 2:
                return nd
        return None

    def _net_at(self, pos: QPointF) -> str:
        node_map = {nd.ref: nd for nd in self._nodes}
        best_dist, best_net = 12.0, ""
        for net, refs in self._net_refs.items():
            valid = [r for r in refs if r in node_map]
            for i in range(len(valid) - 1):
                a, b = node_map[valid[i]], node_map[valid[i + 1]]
                ax, ay = self._tx(a.x), self._ty(a.y)
                bx, by = self._tx(b.x), self._ty(b.y)
                dist = _pt_to_seg_dist(pos.x(), pos.y(), ax, ay, bx, by)
                if dist < best_dist:
                    best_dist, best_net = dist, net
        return best_net


def _pt_to_seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ── Dialog ─────────────────────────────────────────────────────────────────────

class NetTopologyDialog(QDialog):
    component_selected = Signal(str)   # reference

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._nodes: list[_Node] = []
        self._net_refs: dict[str, list[str]] = {}
        self.setWindowTitle("Topologia sieci — Graf połączeń")
        self.resize(1100, 700)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = QHBoxLayout()

        lbl_iter = QLabel("Iteracje layoutu:")
        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(20, 500)
        self._iter_spin.setValue(120)
        self._iter_spin.setSingleStep(20)
        tb.addWidget(lbl_iter)
        tb.addWidget(self._iter_spin)

        lbl_max = QLabel("Max komponentów:")
        self._max_spin = QSpinBox()
        self._max_spin.setRange(5, 200)
        self._max_spin.setValue(60)
        self._max_spin.setSingleStep(5)
        tb.addWidget(lbl_max)
        tb.addWidget(self._max_spin)

        self._cb_power = QCheckBox("Pokaż szyny zasilania")
        self._cb_power.setChecked(True)
        self._cb_power.toggled.connect(lambda v: self._canvas.set_show_power(v))
        tb.addWidget(self._cb_power)

        self._cb_gnd = QCheckBox("Pokaż GND")
        self._cb_gnd.setChecked(True)
        self._cb_gnd.toggled.connect(lambda v: self._canvas.set_show_gnd(v))
        tb.addWidget(self._cb_gnd)

        tb.addSpacing(8)

        self._net_filter_combo = QComboBox()
        self._net_filter_combo.setMinimumWidth(140)
        self._net_filter_combo.addItem("— Wszystkie sieci —")
        self._net_filter_combo.currentTextChanged.connect(self._on_filter_net)
        tb.addWidget(QLabel("Filtr sieci:"))
        tb.addWidget(self._net_filter_combo)

        tb.addStretch()

        btn_gen = QPushButton("⚡ Generuj graf")
        btn_gen.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_gen.clicked.connect(self._generate)
        tb.addWidget(btn_gen)

        btn_fit = QPushButton("🔍 Dopasuj widok")
        btn_fit.clicked.connect(self._fit)
        tb.addWidget(btn_fit)

        btn_shuffle = QPushButton("🔀 Przetasuj")
        btn_shuffle.clicked.connect(self._shuffle)
        tb.addWidget(btn_shuffle)

        layout.addLayout(tb)

        # ── Splitter: canvas | info panel ─────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        self._canvas = _TopoCanvas()
        self._canvas.node_clicked.connect(self._on_node_clicked)
        self._canvas.edge_clicked.connect(self._on_edge_clicked)
        splitter.addWidget(self._canvas)

        # Info panel
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(4, 0, 0, 0)

        self._info_title = QLabel("Kliknij komponent lub sieć")
        self._info_title.setStyleSheet("font-weight: bold; color: #c0d8f0; font-size: 12px;")
        self._info_title.setWordWrap(True)
        info_layout.addWidget(self._info_title)

        self._info_text = QTextEdit()
        self._info_text.setReadOnly(True)
        self._info_text.setMinimumWidth(200)
        self._info_text.setMaximumWidth(260)
        self._info_text.setStyleSheet("font-family: Consolas; font-size: 10px;")
        info_layout.addWidget(self._info_text)

        # Legend
        legend = QGroupBox("Legenda")
        leg_layout = QVBoxLayout(legend)
        for ctype, color in _TYPE_COLORS.items():
            row = QHBoxLayout()
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {color.name()}; font-size: 14px;")
            row.addWidget(dot)
            row.addWidget(QLabel(ctype))
            row.addStretch()
            leg_layout.addLayout(row)
        info_layout.addWidget(legend)

        splitter.addWidget(info_widget)
        splitter.setSizes([820, 260])
        layout.addWidget(splitter, 1)

        # ── Bottom ────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        self._stats_label = QLabel()
        self._stats_label.setStyleSheet("color: #888; font-size: 10px;")
        bottom.addWidget(self._stats_label)
        bottom.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _generate(self) -> None:
        board = self._project.board if self._project else None
        if not board or not board.components:
            self._info_text.setPlainText("Brak komponentów w projekcie.\nZaimportuj plik .kicad_pcb lub dodaj komponenty.")
            return

        self._nodes, self._net_refs = _build_graph(board, self._max_spin.value())

        # Populate net filter combo
        self._net_filter_combo.blockSignals(True)
        self._net_filter_combo.clear()
        self._net_filter_combo.addItem("— Wszystkie sieci —")
        for net in sorted(self._net_refs.keys()):
            self._net_filter_combo.addItem(net)
        self._net_filter_combo.blockSignals(False)

        _run_layout(self._nodes, self._iter_spin.value())
        self._canvas.set_data(self._nodes, self._net_refs)

        n_nets = len(self._net_refs)
        n_comp = len(self._nodes)
        n_edges = sum(max(0, len(v) - 1) for v in self._net_refs.values())
        self._stats_label.setText(
            f"Komponentów: {n_comp}  |  Sieci: {n_nets}  |  "
            f"Krawędzi grafu: {n_edges}  |  "
            f"Przybliżona złożoność: {n_edges * n_comp}"
        )

    def _fit(self) -> None:
        self._canvas._fit_all()
        self._canvas.update()

    def _shuffle(self) -> None:
        r = max(80.0, len(self._nodes) * 12.0)
        for i, nd in enumerate(self._nodes):
            angle = 2 * math.pi * i / max(len(self._nodes), 1)
            nd.x = r * math.cos(angle) + random.uniform(-30, 30)
            nd.y = r * math.sin(angle) + random.uniform(-30, 30)
            nd.vx = nd.vy = 0
        _run_layout(self._nodes, self._iter_spin.value())
        self._canvas.set_data(self._nodes, self._net_refs)

    def _on_node_clicked(self, ref: str) -> None:
        node_map = {nd.ref: nd for nd in self._nodes}
        nd = node_map.get(ref)
        if not nd:
            return
        self._info_title.setText(f"Komponent: {ref}")

        nets_sorted = sorted(nd.nets)
        lines = [
            f"Referencja:  {nd.ref}",
            f"Typ:         {nd.comp_type}",
            f"Wartość:     {nd.value}",
            f"Sieci ({len(nd.nets)}):",
        ]
        for net in nets_sorted:
            members = self._net_refs.get(net, [])
            lines.append(f"  {net} → {', '.join(m for m in members if m != ref)[:60]}")
        self._info_text.setPlainText("\n".join(lines))
        self.component_selected.emit(ref)

    def _on_edge_clicked(self, net: str) -> None:
        members = self._net_refs.get(net, [])
        self._info_title.setText(f"Sieć: {net}")
        lines = [
            f"Sieć:        {net}",
            f"Połączenia:  {len(members)} komponentów",
            "",
            "Komponenty w sieci:",
        ] + [f"  {r}" for r in sorted(members)]
        self._info_text.setPlainText("\n".join(lines))

    def _on_filter_net(self, text: str) -> None:
        if text.startswith("—"):
            self._canvas.set_filter_net("")
        else:
            self._canvas.set_filter_net(text)
