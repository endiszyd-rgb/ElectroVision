"""Interactive PCB Editor canvas widget.

Modes
-----
SELECT   — click to select, drag to move component
ROUTE    — click to start trace, click waypoints, double-click / Enter to finish
VIA      — click to place via
DELETE   — click on component / trace / via to delete
"""
from __future__ import annotations
import math
import copy
from enum import Enum
from typing import Optional

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QCursor,
    QWheelEvent, QMouseEvent, QKeyEvent, QPainterPath
)

from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine
from src.core.models.component import Component


# ── Colour palette ────────────────────────────────────────────────────────────
_LAYER_COLORS: dict[str, str] = {
    "F.Cu":    "#c83232",
    "B.Cu":    "#3264c8",
    "F.SilkS": "#dcdcdc",
    "B.SilkS": "#96dc96",
    "F.Mask":  "#c800a0",
    "B.Mask":  "#0096c8",
    "Edge.Cuts":"#ffdc00",
    "F.Fab":   "#b4b4b4",
    "B.Fab":   "#6464b4",
    "In1.Cu":  "#c2a020",
    "In2.Cu":  "#20a0c2",
}
_VIA_COLOR       = QColor("#50d050")
_SEL_COLOR       = QColor("#ffff00")
_ROUTE_PREVIEW   = QColor("#00e5ff")
_GRID_COLOR      = QColor("#1e2030")
_BG_COLOR        = QColor("#0d1117")
_BOARD_FILL      = QColor("#0e1820")
_COMP_FILL       = QColor("#1a2a1a")
_COMP_BORDER_F   = QColor("#c8a040")
_COMP_BORDER_B   = QColor("#4080c0")
_DEL_HOVER       = QColor("#ff4040")


class EditorMode(Enum):
    SELECT    = "select"
    ROUTE     = "route"
    VIA       = "via"
    DELETE    = "delete"
    ADD_COMP  = "add_comp"


# ── Undo commands ─────────────────────────────────────────────────────────────

class _MoveComp:
    def __init__(self, comp: Component, ox: float, oy: float, nx: float, ny: float):
        self.comp = comp
        self.ox, self.oy = ox, oy
        self.nx, self.ny = nx, ny

    def redo(self) -> None:
        self.comp.x, self.comp.y = self.nx, self.ny

    def undo(self) -> None:
        self.comp.x, self.comp.y = self.ox, self.oy

    def describe(self) -> str:
        return f"Przesuń {self.comp.reference}"


class _AddTrace:
    def __init__(self, board: PCBBoard, trace: Trace):
        self.board = board
        self.trace = trace

    def redo(self) -> None:
        if self.trace not in self.board.traces:
            self.board.traces.append(self.trace)

    def undo(self) -> None:
        if self.trace in self.board.traces:
            self.board.traces.remove(self.trace)

    def describe(self) -> str:
        return "Dodaj ścieżkę"


class _DelTrace:
    def __init__(self, board: PCBBoard, trace: Trace):
        self.board = board
        self.trace = trace

    def redo(self) -> None:
        if self.trace in self.board.traces:
            self.board.traces.remove(self.trace)

    def undo(self) -> None:
        if self.trace not in self.board.traces:
            self.board.traces.append(self.trace)

    def describe(self) -> str:
        return "Usuń ścieżkę"


class _AddVia:
    def __init__(self, board: PCBBoard, via: Via):
        self.board = board
        self.via = via

    def redo(self) -> None:
        if self.via not in self.board.vias:
            self.board.vias.append(self.via)

    def undo(self) -> None:
        if self.via in self.board.vias:
            self.board.vias.remove(self.via)

    def describe(self) -> str:
        return "Dodaj przelotke"


class _DelVia:
    def __init__(self, board: PCBBoard, via: Via):
        self.board = board
        self.via = via

    def redo(self) -> None:
        if self.via in self.board.vias:
            self.board.vias.remove(self.via)

    def undo(self) -> None:
        if self.via not in self.board.vias:
            self.board.vias.append(self.via)

    def describe(self) -> str:
        return "Usuń przelotke"


class _DelComp:
    def __init__(self, board: PCBBoard, comp: Component):
        self.board = board
        self.comp = comp

    def redo(self) -> None:
        if self.comp in self.board.components:
            self.board.components.remove(self.comp)

    def undo(self) -> None:
        if self.comp not in self.board.components:
            self.board.components.append(self.comp)

    def describe(self) -> str:
        return f"Usuń {self.comp.reference}"


class _AddComp:
    def __init__(self, board: PCBBoard, comp: Component):
        self.board = board
        self.comp = comp

    def redo(self) -> None:
        if self.comp not in self.board.components:
            self.board.components.append(self.comp)

    def undo(self) -> None:
        if self.comp in self.board.components:
            self.board.components.remove(self.comp)

    def describe(self) -> str:
        return f"Dodaj {self.comp.reference}"


# ── Main editor widget ────────────────────────────────────────────────────────

class PCBEditor(QWidget):
    component_selected = Signal(object)   # Component | None
    board_modified     = Signal()
    status_message     = Signal(str)
    undo_state_changed = Signal(bool, bool)  # can_undo, can_redo

    # Hit-test radii (in world mm)
    _COMP_HALF = 1.8    # component bounding half-size
    _VIA_RADIUS = 0.6   # via click radius

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Optional[PCBBoard] = None

        # View
        self._scale   = 8.0      # px / mm
        self._off_x   = 60.0
        self._off_y   = 60.0

        # Editor state
        self._mode          = EditorMode.SELECT
        self._grid_mm       = 1.27
        self._active_layer  = "F.Cu"
        self._trace_width   = 0.25
        self._via_drill     = 0.4
        self._via_size      = 0.8
        self._via_net       = ""
        self._pending_comp: Optional[Component] = None  # component to place

        # Selection
        self._sel_comp:  Optional[Component] = None
        self._sel_trace: Optional[Trace]     = None
        self._sel_via:   Optional[Via]       = None
        self._hover_del: object | None       = None   # highlighted for delete

        # Drag (move component)
        self._dragging       = False
        self._drag_comp: Optional[Component] = None
        self._drag_start_w   = (0.0, 0.0)   # world coords at drag start
        self._drag_comp_orig = (0.0, 0.0)   # original comp pos

        # View pan
        self._panning       = False
        self._pan_start     = (0.0, 0.0)
        self._pan_off0      = (0.0, 0.0)

        # Routing
        self._routing       = False
        self._route_pts: list[tuple[float, float]] = []
        self._cursor_w      = (0.0, 0.0)

        # Undo / Redo
        self._undo_stack: list = []
        self._redo_stack: list = []

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(400, 300)
        self.setCursor(Qt.CrossCursor)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_board(self, board: Optional[PCBBoard]) -> None:
        self._board = board
        self._sel_comp = self._sel_trace = self._sel_via = None
        self._routing = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._fit_view()
        self.update()

    def set_mode(self, mode: EditorMode) -> None:
        self._mode = mode
        self._routing = False
        self._route_pts.clear()
        self._hover_del = None
        self._pending_comp = None
        cursors = {
            EditorMode.SELECT:   Qt.ArrowCursor,
            EditorMode.ROUTE:    Qt.CrossCursor,
            EditorMode.VIA:      Qt.CrossCursor,
            EditorMode.DELETE:   Qt.ForbiddenCursor,
            EditorMode.ADD_COMP: Qt.DragCopyCursor,
        }
        self.setCursor(cursors.get(mode, Qt.CrossCursor))
        self.update()

    def set_active_layer(self, layer: str) -> None:
        self._active_layer = layer

    def set_trace_width(self, w: float) -> None:
        self._trace_width = w

    def set_grid(self, g: float) -> None:
        self._grid_mm = g

    def set_via_params(self, drill: float, size: float) -> None:
        self._via_drill = drill
        self._via_size  = size

    def set_pending_component(self, comp: Component) -> None:
        """Place-mode: the component that follows the cursor."""
        self._pending_comp = copy.deepcopy(comp)
        self.set_mode(EditorMode.ADD_COMP)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> None:
        if not self._undo_stack:
            return
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._emit_undo_state()
        self.board_modified.emit()
        self.update()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        cmd = self._redo_stack.pop()
        cmd.redo()
        self._undo_stack.append(cmd)
        self._emit_undo_state()
        self.board_modified.emit()
        self.update()

    def delete_selected(self) -> None:
        if self._sel_comp:
            self._do(_DelComp(self._board, self._sel_comp))
            self._sel_comp = None
            self.component_selected.emit(None)
        elif self._sel_trace:
            self._do(_DelTrace(self._board, self._sel_trace))
            self._sel_trace = None
        elif self._sel_via:
            self._do(_DelVia(self._board, self._sel_via))
            self._sel_via = None
        self.update()

    def fit_view(self) -> None:
        self._fit_view()
        self.update()

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _w2s(self, wx: float, wy: float) -> tuple[float, float]:
        """World → screen."""
        return wx * self._scale + self._off_x, wy * self._scale + self._off_y

    def _s2w(self, sx: float, sy: float) -> tuple[float, float]:
        """Screen → world."""
        return (sx - self._off_x) / self._scale, (sy - self._off_y) / self._scale

    def _snap(self, wx: float, wy: float) -> tuple[float, float]:
        g = self._grid_mm
        return round(wx / g) * g, round(wy / g) * g

    def _fit_view(self) -> None:
        if not self._board:
            return
        bb = self._board.bounding_box
        w = max(bb[2] - bb[0], 10.0)
        h = max(bb[3] - bb[1], 10.0)
        sx = (self.width()  - 120) / w
        sy = (self.height() - 120) / h
        self._scale = max(0.5, min(sx, sy, 30.0))
        self._off_x = -bb[0] * self._scale + 60
        self._off_y = -bb[1] * self._scale + 60

    # ── Undo helpers ──────────────────────────────────────────────────────────

    def _do(self, cmd) -> None:
        cmd.redo()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        self._emit_undo_state()
        self.board_modified.emit()
        self.status_message.emit(cmd.describe())

    def _emit_undo_state(self) -> None:
        self.undo_state_changed.emit(self.can_undo(), self.can_redo())

    # ── Hit testing ───────────────────────────────────────────────────────────

    def _comp_at(self, wx: float, wy: float) -> Optional[Component]:
        if not self._board:
            return None
        thr = max(self._COMP_HALF, 4.0 / self._scale)
        for c in reversed(self._board.components):
            if abs(c.x - wx) < thr and abs(c.y - wy) < thr:
                return c
        return None

    def _via_at(self, wx: float, wy: float) -> Optional[Via]:
        if not self._board:
            return None
        thr = max(self._VIA_RADIUS, 3.0 / self._scale)
        for v in self._board.vias:
            if math.hypot(v.x - wx, v.y - wy) < thr:
                return v
        return None

    def _trace_at(self, wx: float, wy: float) -> Optional[Trace]:
        if not self._board:
            return None
        thr = max(0.3, 4.0 / self._scale)
        best: Optional[Trace] = None
        best_d = thr
        for t in self._board.traces:
            dx = t.x2 - t.x1; dy = t.y2 - t.y1
            length_sq = dx*dx + dy*dy
            if length_sq < 1e-12:
                d = math.hypot(wx - t.x1, wy - t.y1)
            else:
                param = max(0.0, min(1.0, ((wx-t.x1)*dx + (wy-t.y1)*dy) / length_sq))
                px = t.x1 + param*dx; py = t.y1 + param*dy
                d = math.hypot(wx - px, wy - py)
            if d < best_d:
                best_d = d; best = t
        return best

    # ── paintEvent ────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG_COLOR)

        if not self._board:
            p.setPen(QColor("#555"))
            p.setFont(QFont("Arial", 14))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Załaduj projekt PCB lub wybierz szablon")
            return

        self._draw_grid(p)
        self._draw_board_outline(p)
        self._draw_graphic_lines(p)
        self._draw_traces(p)
        self._draw_vias(p)
        self._draw_components(p)
        self._draw_route_preview(p)
        self._draw_pending_comp(p)
        self._draw_status_bar(p)

    def _draw_grid(self, p: QPainter) -> None:
        g = self._grid_mm * self._scale
        if g < 4:
            return
        p.setPen(QPen(_GRID_COLOR, 1))
        w, h = self.width(), self.height()
        x0 = ((-self._off_x) // g) * g + self._off_x
        y0 = ((-self._off_y) // g) * g + self._off_y
        x = x0
        while x < w:
            y = y0
            while y < h:
                p.drawPoint(int(x), int(y))
                y += g
            x += g

    def _draw_board_outline(self, p: QPainter) -> None:
        bb = self._board.bounding_box
        x1, y1 = self._w2s(bb[0], bb[1])
        x2, y2 = self._w2s(bb[2], bb[3])
        p.setBrush(QBrush(_BOARD_FILL))
        p.setPen(QPen(QColor("#ffcc00"), 1.5))
        p.drawRect(int(x1), int(y1), int(x2-x1), int(y2-y1))

    def _draw_graphic_lines(self, p: QPainter) -> None:
        for gl in self._board.graphic_lines:
            if gl.layer == "Edge.Cuts":
                continue
            c = QColor(_LAYER_COLORS.get(gl.layer, "#888"))
            w = max(0.5, gl.width * self._scale)
            p.setPen(QPen(c, w))
            ax, ay = self._w2s(gl.x1, gl.y1)
            bx, by = self._w2s(gl.x2, gl.y2)
            p.drawLine(int(ax), int(ay), int(bx), int(by))

    def _draw_traces(self, p: QPainter) -> None:
        for t in self._board.traces:
            is_del_hover = (self._mode == EditorMode.DELETE and self._hover_del is t)
            is_sel = (self._sel_trace is t)
            base_c = QColor(_LAYER_COLORS.get(t.layer, "#888"))
            if is_del_hover:
                color = _DEL_HOVER
            elif is_sel:
                color = _SEL_COLOR
            else:
                color = base_c
            pw = max(1.0, t.width * self._scale)
            p.setPen(QPen(color, pw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            ax, ay = self._w2s(t.x1, t.y1)
            bx, by = self._w2s(t.x2, t.y2)
            p.drawLine(int(ax), int(ay), int(bx), int(by))

    def _draw_vias(self, p: QPainter) -> None:
        for v in self._board.vias:
            is_del_hover = (self._mode == EditorMode.DELETE and self._hover_del is v)
            is_sel = (self._sel_via is v)
            color = _DEL_HOVER if is_del_hover else (_SEL_COLOR if is_sel else _VIA_COLOR)
            cx, cy = self._w2s(v.x, v.y)
            r_outer = max(2.0, v.size   * self._scale * 0.5)
            r_drill = max(1.0, v.drill  * self._scale * 0.5)
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), r_outer, r_outer)
            p.setBrush(QBrush(_BG_COLOR))
            p.drawEllipse(QPointF(cx, cy), r_drill, r_drill)

    def _draw_components(self, p: QPainter) -> None:
        cs = max(2.0, self._COMP_HALF * self._scale)
        for c in self._board.components:
            is_del_hover = (self._mode == EditorMode.DELETE and self._hover_del is c)
            is_sel = (self._sel_comp is c)
            border_c = _DEL_HOVER if is_del_hover else (
                _SEL_COLOR if is_sel else (
                    _COMP_BORDER_B if c.layer == "B.Cu" else _COMP_BORDER_F
                )
            )
            cx, cy = self._w2s(c.x, c.y)
            fill = QColor("#2a1a1a") if is_del_hover else (
                QColor("#2a2a00") if is_sel else _COMP_FILL
            )
            p.setBrush(QBrush(fill))
            p.setPen(QPen(border_c, max(1.0, self._scale * 0.08)))
            p.drawRect(QRectF(cx - cs, cy - cs, cs*2, cs*2))

            if self._scale > 3.0:
                p.setPen(border_c)
                p.setFont(QFont("Consolas", max(6, int(self._scale * 1.1))))
                p.drawText(QPointF(cx + cs + 2, cy + 4), c.reference)
            if self._scale > 6.0:
                p.setPen(QColor("#a0a0a0"))
                p.setFont(QFont("Consolas", max(5, int(self._scale * 0.8))))
                p.drawText(QPointF(cx + cs + 2, cy + cs), c.value)

    def _draw_route_preview(self, p: QPainter) -> None:
        if not self._routing or not self._route_pts:
            return
        cx, cy = self._cursor_w
        pen = QPen(_ROUTE_PREVIEW, max(1.0, self._trace_width * self._scale),
                   Qt.DashLine, Qt.RoundCap)
        p.setPen(pen)
        # Draw committed segments
        for i in range(len(self._route_pts) - 1):
            ax, ay = self._w2s(*self._route_pts[i])
            bx, by = self._w2s(*self._route_pts[i+1])
            p.drawLine(int(ax), int(ay), int(bx), int(by))
        # Preview to cursor
        lx, ly = self._w2s(*self._route_pts[-1])
        mx, my = self._w2s(cx, cy)
        p.drawLine(int(lx), int(ly), int(mx), int(my))
        # Dot at each waypoint
        p.setBrush(_ROUTE_PREVIEW)
        p.setPen(Qt.NoPen)
        for pt in self._route_pts:
            sx, sy = self._w2s(*pt)
            p.drawEllipse(QPointF(sx, sy), 3, 3)

    def _draw_pending_comp(self, p: QPainter) -> None:
        if self._mode != EditorMode.ADD_COMP or not self._pending_comp:
            return
        c = self._pending_comp
        cx, cy = self._w2s(*self._cursor_w)
        cs = max(2.0, self._COMP_HALF * self._scale)
        p.setBrush(QBrush(QColor("#1a2a1a")))
        p.setPen(QPen(QColor("#80ff80"), max(1.0, self._scale * 0.08), Qt.DashLine))
        p.drawRect(QRectF(cx - cs, cy - cs, cs*2, cs*2))
        if self._scale > 3.0:
            p.setPen(QColor("#80ff80"))
            p.setFont(QFont("Consolas", max(6, int(self._scale * 1.1))))
            p.drawText(QPointF(cx + cs + 2, cy + 4), c.reference)

    def _draw_status_bar(self, p: QPainter) -> None:
        wx, wy = self._cursor_w
        mode_names = {
            EditorMode.SELECT:   "WYBIERZ",
            EditorMode.ROUTE:    "TRASUJ",
            EditorMode.VIA:      "PRZELOTKA",
            EditorMode.DELETE:   "USUŃ",
            EditorMode.ADD_COMP: "UMIEŚĆ KOMPONENT",
        }
        mode_str = mode_names.get(self._mode, "")
        info = (f"[{mode_str}]  X={wx:.2f}  Y={wy:.2f} mm  "
                f"Warstwa: {self._active_layer}  "
                f"Siatka: {self._grid_mm:.2f}mm  "
                f"Zoom: {self._scale:.1f}×")
        p.setPen(QColor("#666"))
        p.setFont(QFont("Consolas", 8))
        p.drawText(8, self.height() - 6, info)

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent) -> None:
        sx, sy = e.position().x(), e.position().y()
        wx, wy = self._s2w(sx, sy)
        snx, sny = self._snap(wx, wy)

        # Middle / right button → pan
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._pan_start = (sx, sy)
            self._pan_off0  = (self._off_x, self._off_y)
            return

        if not self._board or e.button() != Qt.LeftButton:
            return

        if self._mode == EditorMode.SELECT:
            self._handle_select_click(wx, wy, sx, sy)

        elif self._mode == EditorMode.ROUTE:
            self._handle_route_click(snx, sny, e)

        elif self._mode == EditorMode.VIA:
            self._place_via(snx, sny)

        elif self._mode == EditorMode.DELETE:
            self._handle_delete_click(wx, wy)

        elif self._mode == EditorMode.ADD_COMP:
            self._place_pending_comp(snx, sny)

    def _handle_select_click(self, wx: float, wy: float,
                              sx: float, sy: float) -> None:
        comp = self._comp_at(wx, wy)
        if comp:
            self._sel_comp  = comp
            self._sel_trace = None
            self._sel_via   = None
            self.component_selected.emit(comp)
            # Prepare drag
            self._dragging       = True
            self._drag_comp      = comp
            self._drag_start_w   = (wx, wy)
            self._drag_comp_orig = (comp.x, comp.y)
            self.update()
            return
        via = self._via_at(wx, wy)
        if via:
            self._sel_via   = via
            self._sel_comp  = None
            self._sel_trace = None
            self.component_selected.emit(None)
            self.update()
            return
        tr = self._trace_at(wx, wy)
        if tr:
            self._sel_trace = tr
            self._sel_comp  = None
            self._sel_via   = None
            self.component_selected.emit(None)
            self.update()
            return
        # Click on empty space — deselect
        self._sel_comp = self._sel_trace = self._sel_via = None
        self.component_selected.emit(None)
        self.update()

    def _handle_route_click(self, snx: float, sny: float,
                             e: QMouseEvent) -> None:
        if not self._routing:
            # Start new route
            self._routing = True
            self._route_pts = [(snx, sny)]
            self.status_message.emit(
                "Trasowanie: klikaj punkty pośrednie, podwójny klik / Enter = zakończ, Esc = anuluj"
            )
        else:
            # Check double-click → finish
            if e.type().name == "MouseButtonDblClick":
                self._finish_route(snx, sny)
            else:
                self._route_pts.append((snx, sny))
        self.update()

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton and self._mode == EditorMode.ROUTE and self._routing:
            sx, sy = e.position().x(), e.position().y()
            wx, wy = self._s2w(sx, sy)
            snx, sny = self._snap(wx, wy)
            self._finish_route(snx, sny)

    def _finish_route(self, ex: float, ey: float) -> None:
        if not self._routing or len(self._route_pts) < 1:
            self._routing = False
            return
        pts = self._route_pts + [(ex, ey)]
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            if math.hypot(x2-x1, y2-y1) < 0.01:
                continue
            tr = Trace(x1=x1, y1=y1, x2=x2, y2=y2,
                       width=self._trace_width, layer=self._active_layer)
            self._do(_AddTrace(self._board, tr))
        self._routing = False
        self._route_pts.clear()
        self.update()

    def _place_via(self, wx: float, wy: float) -> None:
        via = Via(x=wx, y=wy,
                  drill=self._via_drill, size=self._via_size,
                  net_name=self._via_net)
        self._do(_AddVia(self._board, via))
        self.update()

    def _handle_delete_click(self, wx: float, wy: float) -> None:
        comp = self._comp_at(wx, wy)
        if comp:
            self._do(_DelComp(self._board, comp))
            if self._sel_comp is comp:
                self._sel_comp = None
                self.component_selected.emit(None)
            self.update(); return
        via = self._via_at(wx, wy)
        if via:
            self._do(_DelVia(self._board, via))
            if self._sel_via is via:
                self._sel_via = None
            self.update(); return
        tr = self._trace_at(wx, wy)
        if tr:
            self._do(_DelTrace(self._board, tr))
            if self._sel_trace is tr:
                self._sel_trace = None
            self.update()

    def _place_pending_comp(self, wx: float, wy: float) -> None:
        if not self._pending_comp or not self._board:
            return
        comp = copy.deepcopy(self._pending_comp)
        comp.x = wx
        comp.y = wy
        # Auto-increment reference number
        prefix = "".join(ch for ch in comp.reference if ch.isalpha())
        existing_nums = []
        for c in self._board.components:
            if c.reference.startswith(prefix):
                try:
                    existing_nums.append(int(c.reference[len(prefix):]))
                except ValueError:
                    pass
        next_num = max(existing_nums, default=0) + 1
        comp.reference = f"{prefix}{next_num}"
        self._do(_AddComp(self._board, comp))
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        sx, sy = e.position().x(), e.position().y()
        wx, wy = self._s2w(sx, sy)
        snx, sny = self._snap(wx, wy)
        self._cursor_w = (snx, sny)

        if self._panning:
            dx = sx - self._pan_start[0]
            dy = sy - self._pan_start[1]
            self._off_x = self._pan_off0[0] + dx
            self._off_y = self._pan_off0[1] + dy
            self.update()
            return

        if self._dragging and self._drag_comp:
            dx = wx - self._drag_start_w[0]
            dy = wy - self._drag_start_w[1]
            ox, oy = self._drag_comp_orig
            new_x, new_y = self._snap(ox + dx, oy + dy)
            self._drag_comp.x = new_x
            self._drag_comp.y = new_y
            self.update()
            return

        # Delete mode: update hover highlight
        if self._mode == EditorMode.DELETE and self._board:
            hit = (self._comp_at(wx, wy)
                   or self._via_at(wx, wy)
                   or self._trace_at(wx, wy))
            if hit is not self._hover_del:
                self._hover_del = hit
                self.update()

        if self._routing or self._mode == EditorMode.ADD_COMP:
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = False
            return

        if e.button() == Qt.LeftButton and self._dragging and self._drag_comp:
            self._dragging = False
            ox, oy = self._drag_comp_orig
            nx, ny = self._drag_comp.x, self._drag_comp.y
            if (ox, oy) != (nx, ny):
                # Record as undo command (the move already happened, just record it)
                cmd = _MoveComp(self._drag_comp, ox, oy, nx, ny)
                # Don't call cmd.redo() again — comp is already at new pos
                self._undo_stack.append(cmd)
                self._redo_stack.clear()
                self._emit_undo_state()
                self.board_modified.emit()
                self.status_message.emit(cmd.describe())
            self._drag_comp = None
            self.update()

    def wheelEvent(self, e: QWheelEvent) -> None:
        factor = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        px, py = e.position().x(), e.position().y()
        self._off_x = px - (px - self._off_x) * factor
        self._off_y = py - (py - self._off_y) * factor
        self._scale *= factor
        self.update()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key_Escape:
            if self._routing:
                self._routing = False
                self._route_pts.clear()
                self.status_message.emit("Trasowanie anulowane")
                self.update()
            elif self._mode == EditorMode.ADD_COMP:
                self.set_mode(EditorMode.SELECT)

        elif e.key() == Qt.Key_Return or e.key() == Qt.Key_Enter:
            if self._routing and len(self._route_pts) >= 2:
                self._finish_route(*self._route_pts[-1])

        elif e.key() == Qt.Key_Delete or e.key() == Qt.Key_Backspace:
            self.delete_selected()

        elif e.key() == Qt.Key_F:
            self.fit_view()

        elif e.modifiers() & Qt.ControlModifier:
            if e.key() == Qt.Key_Z:
                if e.modifiers() & Qt.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
            elif e.key() == Qt.Key_Y:
                self.redo()

        elif e.key() == Qt.Key_S:
            self.set_mode(EditorMode.SELECT)
        elif e.key() == Qt.Key_R:
            self.set_mode(EditorMode.ROUTE)
        elif e.key() == Qt.Key_V:
            self.set_mode(EditorMode.VIA)
        elif e.key() == Qt.Key_X:
            self.set_mode(EditorMode.DELETE)
