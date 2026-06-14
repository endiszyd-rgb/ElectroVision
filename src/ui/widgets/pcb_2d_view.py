"""2D PCB rendering widget using QPainter."""
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QTransform, QWheelEvent, QMouseEvent

from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine, GraphicArc
from src.core.models.component import Component
from src.utils.colors import layer_color, VIA_COLOR, PAD_COLOR, BOARD_COLOR

RENDER_ORDER = [
    "B.Cu", "In2.Cu", "In1.Cu", "F.Cu",
    "B.Mask", "F.Mask",
    "B.SilkS", "F.SilkS",
    "B.Fab", "F.Fab",
    "Edge.Cuts",
]


class PCB2DView(QWidget):
    component_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._board: PCBBoard | None = None
        self._scale: float = 5.0
        self._offset_x: float = 40.0
        self._offset_y: float = 40.0
        self._pan_start: QPointF | None = None
        self._selected: Component | None = None
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_board(self, board: PCBBoard | None) -> None:
        self._board = board
        if board:
            self._fit_to_view()
        self.update()

    def _fit_to_view(self) -> None:
        if not self._board:
            return
        bb = self._board.bounding_box
        bw = bb[2] - bb[0]
        bh = bb[3] - bb[1]
        if bw <= 0 or bh <= 0:
            return
        margin = 0.9
        scale_x = (self.width()  * margin) / bw
        scale_y = (self.height() * margin) / bh
        self._scale = min(scale_x, scale_y)
        self._offset_x = (self.width()  - bw * self._scale) / 2 - bb[0] * self._scale
        self._offset_y = (self.height() - bh * self._scale) / 2 - bb[1] * self._scale

    def _world_to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(x * self._scale + self._offset_x,
                       y * self._scale + self._offset_y)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BOARD_COLOR)

        if not self._board:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak projektu PCB\nImportuj plik .kicad_pcb")
            return

        self._draw_board_fill(p)
        for layer in RENDER_ORDER:
            self._draw_traces(p, layer)
            self._draw_graphic_lines(p, layer)
            self._draw_graphic_arcs(p, layer)
        self._draw_vias(p)
        self._draw_pads(p)
        self._draw_selection(p)

    def _draw_board_fill(self, p: QPainter) -> None:
        if not self._board:
            return
        edge_lines = [l for l in self._board.graphic_lines if l.layer == "Edge.Cuts"]
        if not edge_lines:
            return
        bb = self._board.bounding_box
        tl = self._world_to_screen(bb[0], bb[1])
        br = self._world_to_screen(bb[2], bb[3])
        p.fillRect(QRectF(tl, br), QColor(20, 70, 20, 255))

    def _draw_traces(self, p: QPainter, layer: str) -> None:
        if not self._board:
            return
        color = layer_color(layer)
        for tr in self._board.traces:
            if tr.layer != layer:
                continue
            pen = QPen(color, max(1.0, tr.width * self._scale))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            a = self._world_to_screen(tr.x1, tr.y1)
            b = self._world_to_screen(tr.x2, tr.y2)
            p.drawLine(a, b)

    def _draw_graphic_lines(self, p: QPainter, layer: str) -> None:
        if not self._board:
            return
        color = layer_color(layer)
        for gl in self._board.graphic_lines:
            if gl.layer != layer:
                continue
            pen = QPen(color, max(1.0, gl.width * self._scale))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            a = self._world_to_screen(gl.x1, gl.y1)
            b = self._world_to_screen(gl.x2, gl.y2)
            p.drawLine(a, b)

    def _draw_graphic_arcs(self, p: QPainter, layer: str) -> None:
        if not self._board:
            return
        color = layer_color(layer)
        for ga in self._board.graphic_arcs:
            if ga.layer != layer:
                continue
            pen = QPen(color, max(1.0, ga.width * self._scale))
            p.setPen(pen)
            cx, cy = self._world_to_screen(ga.x, ga.y).x(), self._world_to_screen(ga.x, ga.y).y()
            r = ((ga.start_x - ga.x)**2 + (ga.start_y - ga.y)**2)**0.5 * self._scale
            rect = QRectF(cx - r, cy - r, 2*r, 2*r)
            start_angle = int(math.atan2(ga.start_y - ga.y, ga.start_x - ga.x) * 180 / math.pi * 16)
            span_angle = int(-ga.angle * 16)
            p.drawArc(rect, start_angle, span_angle)

    def _draw_vias(self, p: QPainter) -> None:
        if not self._board:
            return
        for via in self._board.vias:
            center = self._world_to_screen(via.x, via.y)
            r_outer = (via.size / 2) * self._scale
            r_inner = (via.drill / 2) * self._scale
            p.setBrush(QBrush(VIA_COLOR))
            p.setPen(Qt.NoPen)
            p.drawEllipse(center, r_outer, r_outer)
            p.setBrush(QBrush(BOARD_COLOR))
            p.drawEllipse(center, max(1.0, r_inner), max(1.0, r_inner))

    def _draw_pads(self, p: QPainter) -> None:
        if not self._board:
            return
        for comp in self._board.components:
            for pad in comp.pads:
                sx = comp.x + pad.x
                sy = comp.y + pad.y
                center = self._world_to_screen(sx, sy)
                rw = max(2.0, (pad.width  / 2) * self._scale)
                rh = max(2.0, (pad.height / 2) * self._scale)
                p.setBrush(QBrush(PAD_COLOR))
                p.setPen(Qt.NoPen)
                if pad.shape in ("circle", "oval") or pad.pad_type == "thru_hole":
                    p.drawEllipse(center, rw, rh)
                else:
                    rect = QRectF(center.x() - rw, center.y() - rh, 2*rw, 2*rh)
                    p.drawRect(rect)

    def _draw_selection(self, p: QPainter) -> None:
        if not self._selected:
            return
        center = self._world_to_screen(self._selected.x, self._selected.y)
        p.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        r = 5.0 * self._scale
        p.drawEllipse(center, r, r)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        cursor = event.position()
        self._offset_x = cursor.x() - factor * (cursor.x() - self._offset_x)
        self._offset_y = cursor.y() - factor * (cursor.y() - self._offset_y)
        self._scale *= factor
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self._pan_start = event.position()
        elif event.button() == Qt.LeftButton:
            self._pick_component(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_start and event.buttons() & Qt.RightButton:
            delta = event.position() - self._pan_start
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._pan_start = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self._pan_start = None

    def _pick_component(self, pos: QPointF) -> None:
        if not self._board:
            return
        best = None
        best_dist = float("inf")
        for comp in self._board.components:
            sp = self._world_to_screen(comp.x, comp.y)
            dx = sp.x() - pos.x()
            dy = sp.y() - pos.y()
            dist = (dx*dx + dy*dy)**0.5
            if dist < best_dist and dist < 20:
                best_dist = dist
                best = comp
        self._selected = best
        self.update()
        if best:
            self.component_selected.emit(best)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._board:
            self._fit_to_view()
