"""Schematic panel — import .kicad_sch, 2D render + AI analysis."""
from __future__ import annotations
import math
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QSplitter, QTextEdit, QFileDialog, QMessageBox,
    QProgressBar, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt, Slot, QRectF, QPointF, QSizeF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QMouseEvent, QTransform
)

from src.core.parsers.kicad_sch_parser import parse_kicad_sch, Schematic, SchComponent
from src.core.project import Project
from src.ai.bridge import AIBridge


# ── Schematic 2D renderer ─────────────────────────────────────────────────────

class _SchView(QWidget):
    WIRE_COLOR   = QColor("#60a0d0")
    COMP_COLOR   = QColor("#e8c060")
    TEXT_COLOR   = QColor("#d0d0d0")
    LABEL_COLOR  = QColor("#80e080")
    JUNCTION_CLR = QColor("#60d0a0")
    NOCONN_CLR   = QColor("#d06060")
    GRID_COLOR   = QColor("#1e2030")
    BG_COLOR     = QColor("#12141e")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sch: Schematic | None = None
        self._scale = 1.5
        self._offset = QPointF(0, 0)
        self._drag_start: QPointF | None = None
        self._drag_offset = QPointF(0, 0)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_schematic(self, sch: Schematic) -> None:
        self._sch = sch
        self._fit_view()
        self.update()

    def _fit_view(self) -> None:
        if not self._sch:
            return
        bb = self._sch.bounding_box
        w = max(bb[2] - bb[0], 1.0)
        h = max(bb[3] - bb[1], 1.0)
        sx = (self.width() - 80) / w
        sy = (self.height() - 80) / h
        self._scale = max(0.1, min(sx, sy, 4.0))
        self._offset = QPointF(
            -bb[0] * self._scale + 40,
            -bb[1] * self._scale + 40,
        )

    def _to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(x * self._scale + self._offset.x(),
                       y * self._scale + self._offset.y())

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG_COLOR)

        if not self._sch:
            p.setPen(QColor("#555"))
            p.setFont(QFont("Arial", 13))
            p.drawText(self.rect(), Qt.AlignCenter, "Załaduj plik .kicad_sch")
            return

        # Wires
        p.setPen(QPen(self.WIRE_COLOR, max(1.0, self._scale * 0.15)))
        for w in self._sch.wires:
            a = self._to_screen(w.x1, w.y1)
            b = self._to_screen(w.x2, w.y2)
            p.drawLine(a, b)

        # Junctions
        p.setBrush(self.JUNCTION_CLR)
        p.setPen(Qt.NoPen)
        r = max(2.0, self._scale * 0.25)
        for j in self._sch.junctions:
            pt = self._to_screen(j.x, j.y)
            p.drawEllipse(pt, r, r)

        # No-connects (X)
        p.setPen(QPen(self.NOCONN_CLR, max(1.0, self._scale * 0.1)))
        d = max(2.0, self._scale * 0.3)
        for nc in self._sch.no_connects:
            pt = self._to_screen(nc.x, nc.y)
            p.drawLine(QPointF(pt.x()-d, pt.y()-d), QPointF(pt.x()+d, pt.y()+d))
            p.drawLine(QPointF(pt.x()+d, pt.y()-d), QPointF(pt.x()-d, pt.y()+d))

        # Components
        comp_size = max(3.0, self._scale * 0.8)
        for c in self._sch.components:
            pt = self._to_screen(c.x, c.y)
            # Body rect
            r_rect = QRectF(pt.x() - comp_size, pt.y() - comp_size,
                            comp_size * 2, comp_size * 2)
            p.setBrush(QBrush(QColor("#1c2a3a")))
            p.setPen(QPen(self.COMP_COLOR, max(0.5, self._scale * 0.1)))
            p.drawRect(r_rect)
            # Reference label
            if self._scale > 0.5:
                p.setPen(self.COMP_COLOR)
                p.setFont(QFont("Consolas", max(6, int(self._scale * 4.5))))
                p.drawText(QPointF(pt.x() + comp_size + 2, pt.y() - 1), c.reference)
                p.setPen(self.TEXT_COLOR)
                p.setFont(QFont("Consolas", max(5, int(self._scale * 3.5))))
                p.drawText(QPointF(pt.x() + comp_size + 2, pt.y() + max(6, int(self._scale * 4))), c.value)

        # Labels
        p.setPen(self.LABEL_COLOR)
        p.setFont(QFont("Consolas", max(5, int(self._scale * 3.5))))
        for lbl in self._sch.labels:
            pt = self._to_screen(lbl.x, lbl.y)
            if self._scale > 0.3:
                p.drawText(QPointF(pt.x() + 2, pt.y() - 2), lbl.text)

    def wheelEvent(self, e: QWheelEvent) -> None:
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        pos = e.position()
        self._offset = QPointF(
            pos.x() - (pos.x() - self._offset.x()) * factor,
            pos.y() - (pos.y() - self._offset.y()) * factor,
        )
        self._scale *= factor
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MiddleButton or e.button() == Qt.RightButton:
            self._drag_start = e.position()
            self._drag_offset = QPointF(self._offset)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start is not None:
            delta = e.position() - self._drag_start
            self._offset = self._drag_offset + delta
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._drag_start = None

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_F:
            self._fit_view()
            self.update()


# ── Schematic panel ───────────────────────────────────────────────────────────

class SchematicPanel(QWidget):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._sch: Schematic | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: schematic view ─────────────────────────────────────────────
        view_container = QWidget()
        vc_layout = QVBoxLayout(view_container)
        vc_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        btn_open = QPushButton("📂 Otwórz .kicad_sch")
        btn_open.clicked.connect(self._on_open)
        toolbar.addWidget(btn_open)

        btn_fit = QPushButton("⊡ Dopasuj")
        btn_fit.clicked.connect(self._fit)
        toolbar.addWidget(btn_fit)

        self._info_label = QLabel("Brak schematu — załaduj plik .kicad_sch")
        self._info_label.setStyleSheet("color: #888; font-size: 10px;")
        toolbar.addWidget(self._info_label)
        toolbar.addStretch()
        vc_layout.addLayout(toolbar)

        self._view = _SchView()
        vc_layout.addWidget(self._view, 1)

        hint = QLabel("Scroll = zoom  |  Prawy przycisk / Środkowy = pan  |  F = dopasuj")
        hint.setStyleSheet("color: #555; font-size: 9px; padding: 2px;")
        vc_layout.addWidget(hint)
        splitter.addWidget(view_container)

        # ── Right: info + AI ─────────────────────────────────────────────────
        right = QWidget()
        right.setMaximumWidth(320)
        right.setMinimumWidth(240)
        r_layout = QVBoxLayout(right)
        r_layout.setContentsMargins(0, 0, 0, 0)

        # Stats
        stats_box = QGroupBox("Statystyki schematu")
        stats_layout = QVBoxLayout(stats_box)
        self._stats_label = QLabel("—")
        self._stats_label.setWordWrap(True)
        self._stats_label.setTextFormat(Qt.RichText)
        stats_layout.addWidget(self._stats_label)
        r_layout.addWidget(stats_box)

        # AI
        ai_box = QGroupBox("🤖 AI Analiza schematu")
        ai_layout = QVBoxLayout(ai_box)

        btn_row = QHBoxLayout()
        btn_analyze = QPushButton("Analizuj schemat")
        btn_analyze.clicked.connect(self._ai_analyze)
        btn_row.addWidget(btn_analyze)

        btn_power = QPushButton("Zasilanie")
        btn_power.clicked.connect(self._ai_power)
        btn_row.addWidget(btn_power)
        ai_layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        btn_bom = QPushButton("Generuj BOM z AI")
        btn_bom.clicked.connect(self._ai_bom)
        btn_row2.addWidget(btn_bom)

        btn_errors = QPushButton("Szukaj błędów")
        btn_errors.clicked.connect(self._ai_errors)
        btn_row2.addWidget(btn_errors)
        ai_layout.addLayout(btn_row2)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(5)
        ai_layout.addWidget(self._ai_progress)

        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 9))
        self._ai_out.setPlaceholderText("Wyniki analizy AI…")
        ai_layout.addWidget(self._ai_out)

        btn_clear = QPushButton("Wyczyść")
        btn_clear.clicked.connect(self._ai_out.clear)
        ai_layout.addWidget(btn_clear)
        r_layout.addWidget(ai_box)
        r_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([700, 280])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        # Try to auto-load .kicad_sch alongside .kicad_pcb
        if project.path:
            sch_path = project.path.with_suffix(".kicad_sch")
            if sch_path.exists():
                self._load_sch(str(sch_path))

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Otwórz schemat KiCad", "",
            "KiCad Schematic (*.kicad_sch);;Wszystkie pliki (*)"
        )
        if path:
            self._load_sch(path)

    def _load_sch(self, path: str) -> None:
        try:
            self._sch = parse_kicad_sch(path)
            self._view.set_schematic(self._sch)
            self._update_stats()
            self._info_label.setText(f"{Path(path).name}  |  {len(self._sch.components)} komp., {len(self._sch.wires)} drutów")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można wczytać schematu:\n{e}")

    def _update_stats(self) -> None:
        if not self._sch:
            self._stats_label.setText("—")
            return
        comps = self._sch.components
        by_type: dict[str, int] = {}
        for c in comps:
            t = c.reference[:1] if c.reference else "?"
            by_type[t] = by_type.get(t, 0) + 1

        type_map = {"R": "Rezystory", "C": "Kondensatory", "U": "ICs", "J": "Złącza",
                    "D": "Diody", "Q": "Tranzystory", "L": "Cewki", "SW": "Przyciski"}
        rows = []
        for k, v in sorted(by_type.items()):
            name = type_map.get(k, k)
            rows.append(f"<b>{name}:</b> {v}")

        bb = self._sch.bounding_box
        w = bb[2] - bb[0]; h = bb[3] - bb[1]
        self._stats_label.setText(
            f"<b>Tytuł:</b> {self._sch.title}<br>"
            f"<b>Komponenty:</b> {len(comps)}<br>"
            f"<b>Druty:</b> {len(self._sch.wires)}<br>"
            f"<b>Etykiety:</b> {len(self._sch.labels)}<br>"
            f"<b>Rozm. obszaru:</b> {w:.0f}×{h:.0f}<br><br>"
            + "<br>".join(rows)
        )

    def _fit(self) -> None:
        self._view._fit_view()
        self._view.update()

    def _sch_summary(self) -> str:
        if not self._sch:
            return "Brak schematu."
        refs = [f"{c.reference}={c.value}" for c in self._sch.components[:30]]
        labels = [l.text for l in self._sch.labels[:20]]
        return (
            f"Schemat: {self._sch.title}\n"
            f"Komponenty ({len(self._sch.components)}): {', '.join(refs)}\n"
            f"Etykiety sieci: {', '.join(labels)}\n"
            f"Druty: {len(self._sch.wires)}, Junctions: {len(self._sch.junctions)}"
        )

    def _start_ai(self) -> bool:
        if not self._sch:
            self._ai_out.setPlainText("Załaduj schemat .kicad_sch.")
            return False
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        return True

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_out.append(f"\n⚠ {msg}")

    def _ai_analyze(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Przeanalizuj schemat elektroniczny:\n{self._sch_summary()}\n\n"
            "Opisz: architekturę układu, bloki funkcjonalne, "
            "co robi układ, jakie sygnały przepływają, "
            "potencjalne problemy projektowe.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_power(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Przeanalizuj zasilanie schematu:\n{self._sch_summary()}\n\n"
            "Wskaż: sieci zasilania, jak dystrybuowane jest zasilanie, "
            "kondensatory blokujące, regulator napięcia, "
            "brakujące elementy filtrujące, ryzyko zakłóceń.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_bom(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Na podstawie schematu wygeneruj BOM:\n{self._sch_summary()}\n\n"
            "Format: tabela Markdown z kolumnami: "
            "Ref | Wartość | Opis | Footprint sugerowany | LCSC Part# (jeśli znasz).\n"
            "Pogrupuj według typu komponentu.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_errors(self) -> None:
        if not self._start_ai():
            return
        self._ai.ask_async(
            f"Sprawdź schemat pod kątem błędów:\n{self._sch_summary()}\n\n"
            "Szukaj: brakujących pull-up/pull-down, niezasilonych pinów MCU, "
            "braku kondensatorów blokujących, błędnych napięć, "
            "brakujących rezystorów szeregowych USB D+/D-, "
            "braku ochrony ESD, konfliktu sieci. "
            "Wylistuj problemy numerycznie z wyjaśnieniem.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )
