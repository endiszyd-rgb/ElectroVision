"""PCB Viewer panel — 2D + 3D view with AI analysis sidebar."""
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QGroupBox, QSplitter,
    QTextEdit, QCheckBox, QProgressBar, QScrollArea,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QThread
from PySide6.QtGui import QFont, QColor, QPalette

from src.core.project import Project
from src.core.models.component import Component
from src.ui.widgets.pcb_2d_view import PCB2DView
from src.ui.widgets.pcb_3d_view import PCB3DView
from src.ai.bridge import AIBridge


class PCBViewerPanel(QWidget):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: 2D / 3D views ──────────────────────────────────────────────
        view_tabs = QTabWidget()
        view_tabs.setDocumentMode(True)

        self._view_2d = PCB2DView()
        self._view_3d = PCB3DView()
        view_tabs.addTab(self._view_2d, "2D — Warstwy")
        view_tabs.addTab(self._view_3d, "3D — Interaktywny")
        self._view_2d.component_selected.connect(self._on_component_selected)
        splitter.addWidget(view_tabs)

        # ── Right: info + AI ─────────────────────────────────────────────────
        right = QWidget()
        right.setMaximumWidth(340)
        right.setMinimumWidth(260)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Board info
        board_box = QGroupBox("Informacje o płytce")
        board_layout = QVBoxLayout(board_box)
        self._board_info = QLabel("Brak projektu")
        self._board_info.setWordWrap(True)
        self._board_info.setTextFormat(Qt.RichText)
        board_layout.addWidget(self._board_info)
        right_layout.addWidget(board_box)

        # Selected component
        comp_box = QGroupBox("Wybrany komponent")
        comp_layout = QVBoxLayout(comp_box)
        self._comp_info = QTextEdit()
        self._comp_info.setReadOnly(True)
        self._comp_info.setMaximumHeight(160)
        self._comp_info.setPlaceholderText("Kliknij komponent na płytce…")
        self._comp_info.setFont(QFont("Consolas", 9))
        comp_layout.addWidget(self._comp_info)
        right_layout.addWidget(comp_box)

        # Layer visibility
        layer_box = QGroupBox("Widoczność warstw")
        layer_layout = QVBoxLayout(layer_box)
        self._layer_checks: dict[str, QCheckBox] = {}
        for layer_name, color_hint in [
            ("F.Cu", "#c83232"), ("B.Cu", "#0064c8"), ("F.SilkS", "#dcdcdc"),
            ("B.SilkS", "#96dc96"), ("F.Mask", "#c80096"), ("B.Mask", "#0096c8"),
            ("Edge.Cuts", "#ffdc00"), ("F.Fab", "#b4b4b4"), ("B.Fab", "#6464b4"),
        ]:
            cb = QCheckBox(layer_name)
            cb.setChecked(True)
            cb.toggled.connect(lambda checked, ln=layer_name: self._on_layer_toggle(ln, checked))
            layer_layout.addWidget(cb)
            self._layer_checks[layer_name] = cb
        right_layout.addWidget(layer_box)

        # AI Analysis
        ai_box = QGroupBox("🤖 AI Analiza PCB")
        ai_layout = QVBoxLayout(ai_box)

        btn_row = QHBoxLayout()
        btn_analyze = QPushButton("Analizuj płytkę")
        btn_analyze.setToolTip("AI przeanalizuje projekt pod kątem architektury, zasilania, EMI")
        btn_analyze.clicked.connect(self._ai_analyze_board)
        btn_row.addWidget(btn_analyze)

        btn_comp_ai = QPushButton("Wyjaśnij komponent")
        btn_comp_ai.setToolTip("AI wyjaśni funkcję i podłączenie wybranego komponentu")
        btn_comp_ai.clicked.connect(self._ai_explain_component)
        btn_row.addWidget(btn_comp_ai)
        ai_layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        btn_routing = QPushButton("Strategia trasowania")
        btn_routing.clicked.connect(self._ai_routing)
        btn_row2.addWidget(btn_routing)

        btn_power = QPushButton("Analiza zasilania")
        btn_power.clicked.connect(self._ai_power)
        btn_row2.addWidget(btn_power)
        ai_layout.addLayout(btn_row2)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(6)
        ai_layout.addWidget(self._ai_progress)

        self._ai_output = QTextEdit()
        self._ai_output.setReadOnly(True)
        self._ai_output.setMaximumHeight(200)
        self._ai_output.setFont(QFont("Consolas", 9))
        self._ai_output.setPlaceholderText("Wyniki analizy AI pojawią się tutaj…")
        ai_layout.addWidget(self._ai_output)

        btn_clear_ai = QPushButton("Wyczyść")
        btn_clear_ai.clicked.connect(self._ai_output.clear)
        ai_layout.addWidget(btn_clear_ai)
        right_layout.addWidget(ai_box)

        # Open in KiCad
        btn_kicad = QPushButton("⚡ Otwórz w KiCad (pcbnew)")
        btn_kicad.clicked.connect(self._open_in_kicad)
        right_layout.addWidget(btn_kicad)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([900, 300])
        main_layout.addWidget(splitter)

    # ── Project update ────────────────────────────────────────────────────────

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        board = project.board
        self._view_2d.set_board(board)
        self._view_3d.set_board(board)
        self._ai.set_project_context(project_name=project.name, board=board)
        if board:
            bb = board.bounding_box
            net_names = {n.name for n in board.nets if n.name}
            power_nets = [n for n in net_names if any(p in n.upper() for p in ("VCC","VDD","GND","3V3","5V"))]
            self._board_info.setText(
                f"<b>{project.name}</b><br>"
                f"<span style='color:#aaa;'>{project.save_path_str() or 'Nowy projekt'}</span><br><br>"
                f"📐 Wymiary: <b>{board.width_mm:.2f} × {board.height_mm:.2f} mm</b><br>"
                f"🔩 Komponenty: <b>{len(board.components)}</b><br>"
                f"〰 Ścieżki: <b>{len(board.traces)}</b><br>"
                f"⬤ Przelotki: <b>{len(board.vias)}</b><br>"
                f"🌐 Sieci: <b>{len(board.nets)}</b> "
                f"(<span style='color:#fa4;'>{len(power_nets)} zasilających</span>)<br>"
                f"📚 Warstwy: <b>{len(board.layers)}</b>"
            )
        else:
            self._board_info.setText("<i>Brak projektu — importuj .kicad_pcb</i>")

    # ── Component selection ───────────────────────────────────────────────────

    def _on_component_selected(self, comp: Component) -> None:
        pad_nets = ", ".join(sorted({p.net_name for p in comp.pads if p.net_name}))
        self._comp_info.setHtml(
            f"<b style='color:#fa0;'>{comp.reference}</b> — {comp.value}<br>"
            f"<b>Typ:</b> {comp.component_type}<br>"
            f"<b>Footprint:</b> {comp.footprint}<br>"
            f"<b>Pozycja:</b> X={comp.x:.3f} Y={comp.y:.3f} mm<br>"
            f"<b>Obrót:</b> {comp.rotation}°  <b>Warstwa:</b> {comp.layer}<br>"
            f"<b>Pady:</b> {len(comp.pads)}  <b>Sieci:</b> {pad_nets or '—'}<br>"
            + (f"<b>Opis:</b> {comp.description}<br>" if comp.description else "")
            + (f"<b>Datasheet:</b> <a href='{comp.datasheet}'>{comp.datasheet[:40]}</a>" if comp.datasheet else "")
        )

    def _on_layer_toggle(self, layer_name: str, visible: bool) -> None:
        # Forward to 2D view (toggle layer rendering)
        if hasattr(self._view_2d, 'set_layer_visible'):
            self._view_2d.set_layer_visible(layer_name, visible)
        self._view_2d.update()

    # ── AI actions ────────────────────────────────────────────────────────────

    def _start_ai(self, prompt_fn) -> None:
        if not self._project.board:
            self._ai_output.setPlainText("Załaduj projekt PCB przed analizą AI.")
            return
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        prompt_fn()

    def _ai_done(self, _full: str = "") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_analyze_board(self) -> None:
        self._start_ai(lambda: self._ai.analyze_pcb(
            self._project.board,
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        ))

    def _ai_explain_component(self) -> None:
        selected = self._comp_info.toPlainText()
        if not selected.strip():
            self._ai_output.setPlainText("Najpierw kliknij komponent na płytce.")
            return
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"Wyjaśnij funkcję i podłączenie komponentu:\n{selected}\n\n"
            "Podaj: co robi, jak podłączyć (piny, napięcia, pull-up/pull-down), "
            "kod inicjalizacji, najczęstsze błędy.",
            system_key="code_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_routing(self) -> None:
        self._start_ai(lambda: self._ai.ask_async(
            "Zaproponuj optymalną strategię trasowania ścieżek dla tej płytki. "
            "Uwzględnij: grupy sygnałów, impedancję kontrolowaną, pętle GND, "
            "separację sygnałów analogowych/cyfrowych, RF, zasilanie.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        ))

    def _ai_power(self) -> None:
        self._start_ai(lambda: self._ai.ask_async(
            "Przeanalizuj architekturę zasilania tej płytki. "
            "Wskaż: sieci zasilania, kondensatory blokujące, brakujące filtry, "
            "ryzyko oscylacji regulatora, sekwencję startową, zabezpieczenia.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        ))

    # ── External app ─────────────────────────────────────────────────────────

    def _open_in_kicad(self) -> None:
        if not self._project.path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "KiCad", "Projekt nie ma ścieżki pliku. Najpierw zaimportuj .kicad_pcb.")
            return
        try:
            subprocess.Popen(["pcbnew", str(self._project.path)])
        except FileNotFoundError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "KiCad",
                "Nie znaleziono pcbnew w PATH.\n"
                "Upewnij się, że KiCad jest zainstalowany i dodany do PATH."
            )
