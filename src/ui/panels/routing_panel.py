"""Auto-routing AI panel — AI-assisted PCB routing suggestions + DRC overview."""
from __future__ import annotations
import math
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QSplitter, QTextEdit, QProgressBar,
    QComboBox, QDoubleSpinBox, QCheckBox, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QFrame
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent, QMouseEvent
)

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard, Trace, Via
from src.ai.bridge import AIBridge


# ── Routing visualiser (simplified grid view) ─────────────────────────────────

class _RoutingView(QWidget):
    """Read-only display of existing traces + AI routing overlay."""

    BG    = QColor("#0e1018")
    TRACE_F = QColor("#c04040")
    TRACE_B = QColor("#4060c0")
    VIA   = QColor("#60c060")
    COMP  = QColor("#c8a040")
    GRID  = QColor("#151820")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Optional[PCBBoard] = None
        self._scale = 4.0
        self._offset_x = 40.0
        self._offset_y = 40.0
        self._drag_start = None
        self._drag_off0 = (0.0, 0.0)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)

    def set_board(self, board: Optional[PCBBoard]) -> None:
        self._board = board
        self._fit()
        self.update()

    def _fit(self) -> None:
        if not self._board:
            return
        bb = self._board.bounding_box
        w = max(bb[2] - bb[0], 1)
        h = max(bb[3] - bb[1], 1)
        sx = (self.width() - 80) / w
        sy = (self.height() - 80) / h
        self._scale = max(0.1, min(sx, sy, 20.0))
        self._offset_x = -bb[0] * self._scale + 40
        self._offset_y = -bb[1] * self._scale + 40

    def _s(self, x: float, y: float) -> tuple[float, float]:
        return x * self._scale + self._offset_x, y * self._scale + self._offset_y

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        if not self._board:
            p.setPen(QColor("#444"))
            p.setFont(QFont("Arial", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "Załaduj projekt PCB")
            return

        # Board outline
        bb = self._board.bounding_box
        x1, y1 = self._s(bb[0], bb[1])
        x2, y2 = self._s(bb[2], bb[3])
        p.setPen(QPen(QColor("#ffcc00"), 1.5))
        p.setBrush(QBrush(QColor("#101820")))
        p.drawRect(int(x1), int(y1), int(x2-x1), int(y2-y1))

        # Graphic lines (Edge.Cuts etc.)
        for gl in self._board.graphic_lines:
            if gl.layer == "Edge.Cuts":
                continue
            ax, ay = self._s(gl.x1, gl.y1)
            bx, by = self._s(gl.x2, gl.y2)
            p.setPen(QPen(QColor("#505060"), max(0.5, gl.width * self._scale * 0.05)))
            p.drawLine(int(ax), int(ay), int(bx), int(by))

        # Traces
        for tr in self._board.traces:
            color = self.TRACE_F if tr.layer == "F.Cu" else self.TRACE_B
            pen_w = max(1.0, tr.width * self._scale)
            p.setPen(QPen(color, pen_w, Qt.SolidLine, Qt.RoundCap))
            ax, ay = self._s(tr.x1, tr.y1)
            bx, by = self._s(tr.x2, tr.y2)
            p.drawLine(int(ax), int(ay), int(bx), int(by))

        # Vias
        p.setBrush(self.VIA)
        p.setPen(Qt.NoPen)
        for via in self._board.vias:
            vx, vy = self._s(via.x, via.y)
            r = max(2.0, via.size * self._scale * 0.5)
            p.drawEllipse(int(vx - r), int(vy - r), int(r*2), int(r*2))

        # Components
        cs = max(2.0, self._scale * 0.5)
        p.setBrush(QBrush(QColor("#1c2a1c")))
        p.setPen(QPen(self.COMP, max(0.5, self._scale * 0.05)))
        for comp in self._board.components:
            cx, cy = self._s(comp.x, comp.y)
            p.drawRect(int(cx - cs), int(cy - cs), int(cs*2), int(cs*2))
            if self._scale > 3.0:
                p.setPen(self.COMP)
                p.setFont(QFont("Consolas", max(5, int(self._scale * 1.2))))
                p.drawText(int(cx + cs + 1), int(cy + 3), comp.reference)
                p.setPen(QPen(self.COMP, max(0.5, self._scale * 0.05)))

        # Legend
        p.setPen(QColor("#888"))
        p.setFont(QFont("Arial", 8))
        p.drawText(8, self.height() - 24, f"Skala: {self._scale:.1f}×  |  "
                   f"Komponenty: {len(self._board.components)}  |  "
                   f"Ścieżki: {len(self._board.traces)}  |  "
                   f"Przelotki: {len(self._board.vias)}")

    def wheelEvent(self, e: QWheelEvent) -> None:
        f = 1.2 if e.angleDelta().y() > 0 else 1/1.2
        px, py = e.position().x(), e.position().y()
        self._offset_x = px - (px - self._offset_x) * f
        self._offset_y = py - (py - self._offset_y) * f
        self._scale *= f
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._drag_start = (e.position().x(), e.position().y())
            self._drag_off0 = (self._offset_x, self._offset_y)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start:
            dx = e.position().x() - self._drag_start[0]
            dy = e.position().y() - self._drag_start[1]
            self._offset_x = self._drag_off0[0] + dx
            self._offset_y = self._drag_off0[1] + dy
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._drag_start = None

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_F:
            self._fit()
            self.update()


# ── Routing panel ─────────────────────────────────────────────────────────────

class RoutingPanel(QWidget):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: visualiser ─────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        btn_fit = QPushButton("⊡ Dopasuj")
        btn_fit.clicked.connect(self._fit_view)
        top_bar.addWidget(btn_fit)

        self._layer_combo = QComboBox()
        self._layer_combo.addItems(["Wszystkie warstwy", "F.Cu", "B.Cu"])
        self._layer_combo.currentIndexChanged.connect(lambda _: self._view.update())
        top_bar.addWidget(self._layer_combo)
        top_bar.addStretch()
        ll.addLayout(top_bar)

        self._view = _RoutingView()
        ll.addWidget(self._view, 1)

        hint = QLabel("Scroll = zoom  |  Śr/Prawy klawisz = pan  |  F = dopasuj")
        hint.setStyleSheet("color: #555; font-size: 9px;")
        ll.addWidget(hint)
        splitter.addWidget(left)

        # ── Right: AI routing ─────────────────────────────────────────────────
        right = QWidget()
        right.setMinimumWidth(300)
        right.setMaximumWidth(420)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 1: AI routing
        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)

        params_box = QGroupBox("Parametry trasowania")
        params_form = QVBoxLayout(params_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Szerokość ścieżki:"))
        self._trace_w = QDoubleSpinBox()
        self._trace_w.setRange(0.1, 5.0)
        self._trace_w.setValue(0.25)
        self._trace_w.setSuffix(" mm")
        row1.addWidget(self._trace_w)
        params_form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Clearance:"))
        self._clearance = QDoubleSpinBox()
        self._clearance.setRange(0.05, 2.0)
        self._clearance.setValue(0.2)
        self._clearance.setSuffix(" mm")
        row2.addWidget(self._clearance)
        params_form.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Via drill:"))
        self._via_d = QDoubleSpinBox()
        self._via_d.setRange(0.2, 2.0)
        self._via_d.setValue(0.4)
        self._via_d.setSuffix(" mm")
        row3.addWidget(self._via_d)
        params_form.addLayout(row3)

        self._chk_pour = QCheckBox("Płaszczyzna GND (pour)")
        self._chk_pour.setChecked(True)
        params_form.addWidget(self._chk_pour)

        self._chk_diff = QCheckBox("Pary różnicowe (USB/LVDS)")
        params_form.addWidget(self._chk_diff)

        self._chk_emi = QCheckBox("Optymalizacja EMI")
        params_form.addWidget(self._chk_emi)

        ai_layout.addWidget(params_box)

        btn_col = QVBoxLayout()
        btn_strategy  = QPushButton("🗺 Strategia trasowania")
        btn_strategy.clicked.connect(self._ai_strategy)
        btn_col.addWidget(btn_strategy)

        btn_power = QPushButton("⚡ Ścieżki zasilania")
        btn_power.clicked.connect(self._ai_power_routing)
        btn_col.addWidget(btn_power)

        btn_signal = QPushButton("📡 Sygnały wysokiej częstotliwości")
        btn_signal.clicked.connect(self._ai_hf)
        btn_col.addWidget(btn_signal)

        btn_emi = QPushButton("🛡 Analiza EMI / EMC")
        btn_emi.clicked.connect(self._ai_emi)
        btn_col.addWidget(btn_emi)

        btn_drc = QPushButton("✅ Sprawdź reguły projektowe")
        btn_drc.setStyleSheet("QPushButton { background: #1a4a1f; }")
        btn_drc.clicked.connect(self._run_drc)
        btn_col.addWidget(btn_drc)

        ai_layout.addLayout(btn_col)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(5)
        ai_layout.addWidget(self._ai_progress)

        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 9))
        self._ai_out.setPlaceholderText("Wyniki analizy AI i sugestie trasowania…")
        ai_layout.addWidget(self._ai_out, 1)

        btn_clear = QPushButton("Wyczyść")
        btn_clear.clicked.connect(self._ai_out.clear)
        ai_layout.addWidget(btn_clear)

        tabs.addTab(ai_tab, "🤖 AI Routing")

        # Tab 2: DRC results
        drc_tab = QWidget()
        drc_layout = QVBoxLayout(drc_tab)
        self._drc_tree = QTreeWidget()
        self._drc_tree.setHeaderLabels(["Typ", "Opis", "Lokalizacja"])
        self._drc_tree.setColumnWidth(0, 100)
        self._drc_tree.setColumnWidth(1, 220)
        drc_layout.addWidget(self._drc_tree)
        tabs.addTab(drc_tab, "✅ DRC")

        # Tab 3: Statistics
        stat_tab = QWidget()
        stat_layout = QVBoxLayout(stat_tab)
        self._stat_label = QLabel("Załaduj projekt PCB")
        self._stat_label.setWordWrap(True)
        self._stat_label.setTextFormat(Qt.RichText)
        self._stat_label.setAlignment(Qt.AlignTop)
        stat_layout.addWidget(self._stat_label)
        stat_layout.addStretch()
        tabs.addTab(stat_tab, "📊 Statystyki")

        rl.addWidget(tabs)
        splitter.addWidget(right)
        splitter.setSizes([700, 380])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._view.set_board(project.board)
        self._update_stats()

    def _fit_view(self) -> None:
        self._view._fit()
        self._view.update()

    def _update_stats(self) -> None:
        board = self._project.board
        if not board:
            self._stat_label.setText("<i>Brak projektu</i>")
            return

        # Trace length statistics
        total_len = sum(
            math.hypot(t.x2 - t.x1, t.y2 - t.y1)
            for t in board.traces
        )
        f_traces = [t for t in board.traces if t.layer == "F.Cu"]
        b_traces = [t for t in board.traces if t.layer == "B.Cu"]

        widths = sorted({round(t.width, 3) for t in board.traces})
        power_nets = [n.name for n in board.nets if any(
            p in n.name.upper() for p in ("VCC", "VDD", "GND", "3V3", "5V", "12V")
        )]

        self._stat_label.setText(
            "<b>Statystyki trasowania:</b><br><br>"
            f"Łączna długość ścieżek: <b>{total_len:.1f} mm</b><br>"
            f"F.Cu: {len(f_traces)} ścieżek<br>"
            f"B.Cu: {len(b_traces)} ścieżek<br>"
            f"Przelotki: <b>{len(board.vias)}</b><br><br>"
            f"Używane szerokości: {', '.join(f'{w}mm' for w in widths)}<br><br>"
            f"<b>Sieci zasilania ({len(power_nets)}):</b><br>"
            + "<br>".join(power_nets[:15])
            + ("<br><i>...</i>" if len(power_nets) > 15 else "")
        )

    def _board_context(self) -> str:
        board = self._project.board
        if not board:
            return "Brak projektu."
        comps_str = ", ".join(
            f"{c.reference}({c.value})" for c in board.components[:20]
        )
        power_nets = [n.name for n in board.nets if any(
            p in n.name.upper() for p in ("VCC", "VDD", "GND", "3V3", "5V", "12V")
        )]
        return (
            f"Płytka PCB: {board.width_mm:.1f}×{board.height_mm:.1f} mm, "
            f"{len(board.components)} komponentów, {len(board.nets)} sieci, "
            f"{len(board.traces)} ścieżek, {len(board.vias)} przelotok\n"
            f"Komponenty (pierwsze 20): {comps_str}\n"
            f"Sieci zasilania: {', '.join(power_nets)}\n"
            f"Parametry: ścieżki {self._trace_w.value()}mm, "
            f"clearance {self._clearance.value()}mm, "
            f"via drill {self._via_d.value()}mm"
        )

    def _start_ai(self) -> bool:
        if not self._project.board:
            self._ai_out.setPlainText("Załaduj projekt PCB.")
            return False
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        return True

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_out.append(f"\n⚠ {msg}")

    def _ai_strategy(self) -> None:
        if not self._start_ai():
            return
        opts = []
        if self._chk_pour.isChecked():
            opts.append("płaszczyzna GND (copper pour)")
        if self._chk_diff.isChecked():
            opts.append("pary różnicowe")
        if self._chk_emi.isChecked():
            opts.append("optymalizacja EMI")

        self._ai.ask_async(
            f"Kontekst płytki:\n{self._board_context()}\n\n"
            f"Opcje: {', '.join(opts) or 'standardowe'}\n\n"
            "Zaproponuj kompletną strategię trasowania PCB:\n"
            "1. Kolejność tras (zasilanie → sygnały → GND)\n"
            "2. Które sygnały wymagają kontrolowanej impedancji\n"
            "3. Separation planes (analog/digital)\n"
            "4. Rozmieszczenie vias\n"
            "5. Copper pour — gdzie i jak\n"
            "6. Stitching vias\n"
            "7. Specificzne reguły dla komponentów (RF, SMPS, USB)",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_power_routing(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Kontekst płytki:\n{self._board_context()}\n\n"
            "Przeanalizuj i zaproponuj strategię trasowania ścieżek zasilania:\n"
            "1. Minimalna szerokość ścieżek zasilania dla każdego prądu\n"
            "2. Gdzie umieścić kondensatory blokujące (przy każdym IC)\n"
            "3. Star topology vs bus topology\n"
            "4. Vias termiczne przy regulatorach\n"
            "5. Czy potrzebny plane layer\n"
            "6. Ochrona przed odwrotną polaryzacją",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_hf(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Kontekst płytki:\n{self._board_context()}\n\n"
            "Zaproponuj zasady trasowania dla sygnałów szybkich/RF:\n"
            "1. USB D+/D- (90Ω differential, length matching)\n"
            "2. SPI/I2C clock — terminator, blizkie GND return\n"
            "3. Sygnały kryształu/oscylatora\n"
            "4. Impedancja mikrostrip (50Ω dla RF)\n"
            "5. Unikanie cross-talk\n"
            "6. Minimalizacja pętli GND",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_emi(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Kontekst płytki:\n{self._board_context()}\n\n"
            "Przeprowadź pre-compliance EMI/EMC:\n"
            "1. Identyfikacja głównych źródeł emisji (SMPS, clock, USB)\n"
            "2. Jak zminimalizować pętle prądu (current loop area)\n"
            "3. Ekranowanie — czy potrzebne?\n"
            "4. Filtrowanie wejść/wyjść (ferrite bead, LC)\n"
            "5. Slot antenowy — jak unikać\n"
            "6. Zalecenia dla certyfikacji CE/FCC",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _run_drc(self) -> None:
        """Run basic geometric DRC and populate the tree."""
        board = self._project.board
        if not board:
            return
        self._drc_tree.clear()

        issues: list[tuple[str, str, str]] = []

        # Check 1: components without footprint
        for c in board.components:
            if not c.footprint:
                issues.append(("WARNING", f"{c.reference}: brak footprintu", f"({c.x:.1f},{c.y:.1f})"))

        # Check 2: traces with zero length
        for i, t in enumerate(board.traces):
            length = math.hypot(t.x2 - t.x1, t.y2 - t.y1)
            if length < 0.001:
                issues.append(("WARNING", f"Ścieżka #{i}: zerowa długość", t.layer))

        # Check 3: very thin traces
        min_w = self._clearance.value()
        for i, t in enumerate(board.traces):
            if t.width < min_w * 0.5:
                issues.append(("ERROR", f"Ścieżka #{i}: szerokość {t.width:.3f}mm < min", t.layer))

        # Check 4: missing GND net
        net_names = {n.name.upper() for n in board.nets}
        if "GND" not in net_names and "/GND" not in net_names:
            issues.append(("WARNING", "Brak sieci GND na płytce", "Global"))

        # Check 5: board size sanity
        if board.width_mm < 1 or board.height_mm < 1:
            issues.append(("ERROR", f"Wymiary płytki zbyt małe: {board.width_mm:.1f}×{board.height_mm:.1f}mm", "Board"))
        if board.width_mm > 500 or board.height_mm > 500:
            issues.append(("WARNING", f"Bardzo duże wymiary: {board.width_mm:.0f}×{board.height_mm:.0f}mm", "Board"))

        # Check 6: overlapping components (simplified bounding box)
        positions: list[tuple[str, float, float]] = [(c.reference, c.x, c.y) for c in board.components]
        for i in range(len(positions)):
            for j in range(i+1, len(positions)):
                d = math.hypot(positions[j][1]-positions[i][1], positions[j][2]-positions[i][2])
                if d < 0.5:
                    issues.append(("WARNING",
                                   f"Nakładanie: {positions[i][0]} ↔ {positions[j][0]} ({d:.2f}mm)",
                                   f"({positions[i][1]:.1f},{positions[i][2]:.1f})"))

        if not issues:
            ok = QTreeWidgetItem(self._drc_tree, ["OK", "Brak błędów DRC", ""])
            ok.setForeground(0, QColor("#80e080"))
        else:
            for kind, desc, loc in issues:
                item = QTreeWidgetItem(self._drc_tree, [kind, desc, loc])
                color = "#e08080" if kind == "ERROR" else "#e0c060"
                item.setForeground(0, QColor(color))
                item.setForeground(1, QColor(color))

        self._drc_tree.expandAll()
        self._drc_tree.resizeColumnToContents(0)
        self._drc_tree.resizeColumnToContents(1)
