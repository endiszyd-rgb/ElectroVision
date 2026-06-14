"""STL / STEP generator panel with AI-assisted design."""
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QCheckBox, QProgressBar, QTextEdit,
    QTabWidget, QSplitter, QLineEdit
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from PySide6.QtGui import QFont

from src.core.project import Project
from src.generators.stl_generator import STLGenerator
from src.generators.cadquery_executor import CadQueryExecutor
from src.ai.bridge import AIBridge
from src.ui.widgets.stl_3d_view import STL3DView


class _GenerateThread(QThread):
    finished = Signal(str, str)
    progress_msg = Signal(str)
    error    = Signal(str)

    def __init__(self, board, params: dict, stl_path: str, step_path: str):
        super().__init__()
        self._board     = board
        self._params    = params
        self._stl_path  = stl_path
        self._step_path = step_path

    def run(self) -> None:
        try:
            self.progress_msg.emit("Inicjalizacja generatora 3D…")
            gen = STLGenerator(self._board, self._params)

            if self._params.get("gen_step", True):
                self.progress_msg.emit("Generowanie STEP (CadQuery)…")
                gen.export_step(self._step_path)

            if self._params.get("gen_stl", True):
                self.progress_msg.emit("Generowanie STL…")
                gen.export_stl(self._stl_path)

            self.finished.emit(self._stl_path, self._step_path)
        except Exception as e:
            self.error.emit(str(e))


class STLGenPanel(QWidget):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._ai      = AIBridge.instance()
        self._thread: _GenerateThread | None = None
        self._last_stl  = ""
        self._last_step = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: parameters ─────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(360)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # Tab 1: PCB params
        pcb_tab = QWidget()
        pcb_form = QFormLayout(pcb_tab)

        self._pcb_thickness = QDoubleSpinBox()
        self._pcb_thickness.setRange(0.4, 4.0)
        self._pcb_thickness.setValue(1.6)
        self._pcb_thickness.setSingleStep(0.4)
        self._pcb_thickness.setSuffix(" mm")
        self._pcb_thickness.setToolTip("Standardowe grubości FR4: 0.8 / 1.0 / 1.2 / 1.6 / 2.0 mm")
        pcb_form.addRow("Grubość PCB:", self._pcb_thickness)

        self._gen_pcb_3d = QCheckBox("Model PCB (FR4)")
        self._gen_pcb_3d.setChecked(True)
        pcb_form.addRow(self._gen_pcb_3d)

        self._gen_copper = QCheckBox("Warstwy miedzi w 3D")
        self._gen_copper.setChecked(False)
        self._gen_copper.setToolTip("Dodaje geometrię ścieżek Cu — znacznie wolniejsze")
        pcb_form.addRow(self._gen_copper)

        tabs.addTab(pcb_tab, "PCB")

        # Tab 2: Enclosure
        enc_tab = QWidget()
        enc_form = QFormLayout(enc_tab)

        self._gen_enclosure = QCheckBox("Generuj obudowę")
        self._gen_enclosure.setChecked(True)
        enc_form.addRow(self._gen_enclosure)

        self._gen_lid = QCheckBox("Generuj wieko")
        self._gen_lid.setChecked(True)
        enc_form.addRow(self._gen_lid)

        self._enclosure_margin = QDoubleSpinBox()
        self._enclosure_margin.setRange(0.5, 30.0)
        self._enclosure_margin.setValue(3.0)
        self._enclosure_margin.setSuffix(" mm")
        self._enclosure_margin.setToolTip("Luz między krawędzią PCB a ścianką obudowy")
        enc_form.addRow("Margines od PCB:", self._enclosure_margin)

        self._enclosure_height = QDoubleSpinBox()
        self._enclosure_height.setRange(5.0, 300.0)
        self._enclosure_height.setValue(30.0)
        self._enclosure_height.setSuffix(" mm")
        self._enclosure_height.setToolTip("Wewnętrzna wysokość obudowy")
        enc_form.addRow("Wys. wewnętrzna:", self._enclosure_height)

        self._wall_thickness = QDoubleSpinBox()
        self._wall_thickness.setRange(0.8, 8.0)
        self._wall_thickness.setValue(2.0)
        self._wall_thickness.setSuffix(" mm")
        self._wall_thickness.setToolTip("Min. 1.2mm dla FDM, 0.4mm dla SLA")
        enc_form.addRow("Grubość ścianki:", self._wall_thickness)

        self._corner_radius = QDoubleSpinBox()
        self._corner_radius.setRange(0.0, 15.0)
        self._corner_radius.setValue(2.0)
        self._corner_radius.setSuffix(" mm")
        enc_form.addRow("Zaokrąglenie:", self._corner_radius)

        self._standoff_h = QDoubleSpinBox()
        self._standoff_h.setRange(1.0, 20.0)
        self._standoff_h.setValue(3.0)
        self._standoff_h.setSuffix(" mm")
        enc_form.addRow("Wys. standoffów:", self._standoff_h)

        tabs.addTab(enc_tab, "Obudowa")

        # Tab 3: Export
        exp_tab = QWidget()
        exp_form = QFormLayout(exp_tab)

        self._gen_step = QCheckBox("Eksport STEP (Fusion 360)")
        self._gen_step.setChecked(True)
        exp_form.addRow(self._gen_step)

        self._gen_stl = QCheckBox("Eksport STL (slicer 3D)")
        self._gen_stl.setChecked(True)
        exp_form.addRow(self._gen_stl)

        self._stl_precision = QComboBox()
        self._stl_precision.addItems(["Gruba (szybka)", "Normalna", "Dokładna (wolna)"])
        self._stl_precision.setCurrentIndex(1)
        exp_form.addRow("Precyzja STL:", self._stl_precision)

        exp_form.addRow(QLabel("<b>Wskazówki Fusion 360:</b>"))
        hint = QLabel(
            "• Import STEP: File → Open → wybierz .step\n"
            "• Fusion zachowuje bryły parametrycznie\n"
            "• Użyj 'Split Body' dla osobnych części\n"
            "• STEP AP214 = najlepsza kompatybilność"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 10px;")
        exp_form.addRow(hint)

        tabs.addTab(exp_tab, "Eksport")
        left_layout.addWidget(tabs)

        # AI Designer — full dialog
        btn_ai_designer = QPushButton("🤖 AI Designer — Zaprojektuj przez opis")
        btn_ai_designer.setStyleSheet(
            "QPushButton{background:#1a3a6a;color:#88aaff;font-weight:bold;"
            "font-size:11px;padding:8px;border:1px solid #2a4a8a;}"
            "QPushButton:hover{background:#1e4a8a;}"
        )
        btn_ai_designer.setToolTip(
            "Otworz dedykowany dialog AI do projektowania obudowy 3D.\n"
            "Opisz obudowe slowami — AI wygeneruje kod i podglad 3D."
        )
        btn_ai_designer.clicked.connect(self._open_ai_designer)
        left_layout.addWidget(btn_ai_designer)

        # Generate buttons
        btn_gen = QPushButton("⚙  Generuj STL + STEP (parametrycznie)")
        btn_gen.setStyleSheet("font-weight: bold; font-size: 11px; padding: 7px;")
        btn_gen.clicked.connect(self._generate)
        left_layout.addWidget(btn_gen)

        open_row = QHBoxLayout()
        btn_fusion = QPushButton("Fusion 360")
        btn_fusion.clicked.connect(self._open_in_fusion)
        open_row.addWidget(btn_fusion)
        btn_slicer = QPushButton("Slicer 3D")
        btn_slicer.clicked.connect(self._open_in_slicer)
        open_row.addWidget(btn_slicer)
        btn_folder = QPushButton("📂 Folder")
        btn_folder.clicked.connect(self._open_folder)
        open_row.addWidget(btn_folder)
        left_layout.addLayout(open_row)

        splitter.addWidget(left)

        # ── Right: AI + log ───────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        ai_box = QGroupBox("🤖 AI — Projektant obudowy")
        ai_layout = QVBoxLayout(ai_box)

        ai_btns = QHBoxLayout()
        btn_ai_design = QPushButton("Zaproponuj obudowę AI")
        btn_ai_design.setToolTip(
            "AI zaprojektuje obudowę dla Twojej płytki na podstawie "
            "wymiarów, komponentów i materiałów druku 3D"
        )
        btn_ai_design.clicked.connect(self._ai_design)
        ai_btns.addWidget(btn_ai_design)

        btn_ai_text = QPushButton("Opisz obudowę tekstem")
        btn_ai_text.setToolTip("Opisz obudowę słowami — AI przetłumaczy na parametry")
        btn_ai_text.clicked.connect(self._ai_from_text)
        ai_btns.addWidget(btn_ai_text)

        btn_clear = QPushButton("✕")
        btn_clear.setMaximumWidth(28)
        btn_clear.clicked.connect(lambda: self._ai_output.clear())
        ai_btns.addWidget(btn_clear)
        ai_layout.addLayout(ai_btns)

        self._ai_text_input = QLineEdit()
        self._ai_text_input.setPlaceholderText(
            "np. 'obudowa montowana na ścianie, IP54, USB wyjście z boku, 2 przyciski na górze'"
        )
        self._ai_text_input.returnPressed.connect(self._ai_from_text)
        ai_layout.addWidget(self._ai_text_input)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(6)
        ai_layout.addWidget(self._ai_progress)

        # AI output + execute button
        self._ai_output = QTextEdit()
        self._ai_output.setReadOnly(True)
        self._ai_output.setFont(QFont("Consolas", 9))
        self._ai_output.setPlaceholderText(
            "AI zaproponuje:\n"
            "• Wymiary obudowy (dł × szer × wys)\n"
            "• Pozycje otworów na złącza\n"
            "• System mocowania PCB\n"
            "• Zalecenia druku 3D\n"
            "• Kompletny kod CadQuery\n\n"
            "Następnie kliknij 'Generuj STL z kodu AI' aby wykonać kod i zobaczyć model 3D."
        )
        ai_layout.addWidget(self._ai_output, 1)

        # Execute AI code → STL
        ai_exec_row = QHBoxLayout()
        btn_exec = QPushButton("▶  Generuj STL z kodu AI")
        btn_exec.setStyleSheet("font-weight:bold; background:#1a4a1a; color:#5f5; padding:6px;")
        btn_exec.setToolTip("Wyodrębni kod CadQuery z odpowiedzi AI i wykona go → gotowy plik STL + STEP")
        btn_exec.clicked.connect(self._execute_ai_code)
        ai_exec_row.addWidget(btn_exec)

        btn_ai_full = QPushButton("🤖 AI → Kod + STL")
        btn_ai_full.setStyleSheet("background:#1a1a4a; color:#88f; padding:6px;")
        btn_ai_full.setToolTip("AI wygeneruje kompletny kod CadQuery i automatycznie wykona go")
        btn_ai_full.clicked.connect(self._ai_generate_stl)
        ai_exec_row.addWidget(btn_ai_full)
        ai_layout.addLayout(ai_exec_row)

        right_layout.addWidget(ai_box, 1)

        # 3D Viewer (embedded in panel)
        viewer_box = QGroupBox("3D Podgląd")
        viewer_lay = QVBoxLayout(viewer_box)
        viewer_lay.setContentsMargins(4, 4, 4, 4)
        self._stl_viewer = STL3DView()
        self._stl_viewer.setMinimumHeight(280)
        viewer_lay.addWidget(self._stl_viewer)
        right_layout.addWidget(viewer_box, 2)

        # Log
        log_box = QGroupBox("Log generowania")
        log_layout = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        self._log.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self._log)
        right_layout.addWidget(log_box)

        # Progress
        self._gen_progress = QProgressBar()
        self._gen_progress.setRange(0, 0)
        self._gen_progress.setVisible(False)
        right_layout.addWidget(self._gen_progress)

        splitter.addWidget(right)
        splitter.setSizes([360, 640])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._ai.set_project_context(
            project_name=project.name,
            board=project.board,
            stl_params=self._get_params(),
        )

    def _open_ai_designer(self) -> None:
        from src.ui.dialogs.ai_stl_dialog import AISTLDialog
        dlg = AISTLDialog(self._project, parent=self)
        dlg.stl_ready.connect(self._on_ai_designer_done)
        dlg.exec()

    def _on_ai_designer_done(self, stl_path: str) -> None:
        self._last_stl = stl_path
        self._log.append(f"[AI Designer] STL zaladowany: {stl_path}")
        if Path(stl_path).exists():
            self._stl_viewer.load_stl(stl_path)

    def _get_params(self) -> dict:
        return {
            "pcb_thickness":    self._pcb_thickness.value(),
            "enclosure_margin": self._enclosure_margin.value(),
            "enclosure_height": self._enclosure_height.value(),
            "wall_thickness":   self._wall_thickness.value(),
            "corner_radius":    self._corner_radius.value(),
            "standoff_height":  self._standoff_h.value(),
            "gen_enclosure":    self._gen_enclosure.isChecked(),
            "gen_pcb_3d":       self._gen_pcb_3d.isChecked(),
            "gen_lid":          self._gen_lid.isChecked(),
            "gen_step":         self._gen_step.isChecked(),
            "gen_stl":          self._gen_stl.isChecked(),
        }

    def _generate(self) -> None:
        if not self._project.board:
            QMessageBox.warning(self, "STL", "Brak projektu PCB.")
            return
        stl_path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz plik STL/STEP",
            f"{self._project.name}.stl", "STL (*.stl)"
        )
        if not stl_path:
            return
        step_path = stl_path.replace(".stl", ".step")
        self._log.append(f"▶ Start: {Path(stl_path).name}")
        self._gen_progress.setVisible(True)
        self._thread = _GenerateThread(
            self._project.board, self._get_params(), stl_path, step_path
        )
        self._thread.finished.connect(self._on_done)
        self._thread.progress_msg.connect(self._log.append)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, stl_path: str, step_path: str) -> None:
        self._gen_progress.setVisible(False)
        self._last_stl  = stl_path
        self._last_step = step_path
        self._log.append(f"✓ STL:  {stl_path}")
        self._log.append(f"✓ STEP: {step_path}")
        # Auto-load in embedded 3D viewer
        if Path(stl_path).exists():
            self._stl_viewer.load_stl(stl_path)
        QMessageBox.information(
            self, "Gotowe",
            f"Wygenerowano:\n{stl_path}\n{step_path}\n\n"
            "Podgląd 3D dostępny w panelu poniżej.\n"
            "Otwórz STEP w Fusion 360 przez: File → Open → wybierz plik .step"
        )

    def _execute_ai_code(self) -> None:
        """Extract CadQuery code from AI output and execute it to generate real STL/STEP."""
        import re
        text = self._ai_output.toPlainText()

        # Extract code block
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
        if not blocks:
            # Try to find any CadQuery code without fences
            if "import cadquery" in text or "cq.Workplane" in text:
                blocks = [text]
            else:
                QMessageBox.warning(self, "Kod AI", "Brak bloku kodu CadQuery w odpowiedzi AI.\nKliknij 'Zaproponuj obudowę AI' aby uzyskać kod.")
                return

        code = blocks[-1]  # use the last (usually most complete) code block
        out_dir = Path(self._project.path).parent if self._project.path else Path.cwd()
        base_name = self._project.name.replace(" ", "_") if self._project.name else "ai_enclosure"

        self._log.append(f"▶ Wykonywanie kodu CadQuery ({len(code)} znaków)…")
        self._gen_progress.setVisible(True)

        class _ExecThread(QThread):
            done = Signal(dict)
            def __init__(self, code, out_dir, base_name):
                super().__init__()
                self._c, self._d, self._n = code, out_dir, base_name
            def run(self):
                ex = CadQueryExecutor(str(self._d))
                result = ex.execute(self._c, self._n)
                self.done.emit(result)

        self._exec_thread = _ExecThread(code, out_dir, base_name)
        self._exec_thread.done.connect(self._on_exec_done)
        self._exec_thread.start()

    @Slot(dict)
    def _on_exec_done(self, result: dict) -> None:
        self._gen_progress.setVisible(False)
        if result["stdout"]:
            self._log.append(result["stdout"])
        if result["success"]:
            if result["stl"]:
                self._last_stl = result["stl"]
                self._log.append(f"✓ STL: {result['stl']}")
                self._stl_viewer.load_stl(result["stl"])
            if result["step"]:
                self._last_step = result["step"]
                self._log.append(f"✓ STEP: {result['step']}")
            self._log.append("✓ Model 3D gotowy — widoczny w podglądzie poniżej")
        else:
            self._log.append(f"✗ Błąd CadQuery:\n{result['error']}")
            QMessageBox.critical(self, "Błąd wykonania CadQuery", result["error"][:600])

    def _ai_generate_stl(self) -> None:
        """AI generates complete CadQuery code → executor runs it → show in 3D viewer."""
        self._ai_output.clear()
        self._ai_progress.setVisible(True)

        board = self._project.board if self._project else None
        params = self._get_params()
        out_dir = Path(self._project.path).parent if self._project and self._project.path else Path.cwd()
        base_name = (self._project.name or "ai_enclosure").replace(" ", "_")

        board_info = ""
        if board:
            connectors = [c for c in board.components if c.component_type == "connector"]
            board_info = (
                f"Wymiary PCB: {board.width_mm:.1f} × {board.height_mm:.1f} mm\n"
                f"Grubość PCB: {params.get('pcb_thickness', 1.6)} mm\n"
                f"Łączna liczba komponentów: {len(board.components)}\n"
                f"Złącza na PCB: {', '.join(c.reference+':'+c.value for c in connectors[:6])}\n"
            )

        prompt = (
            f"Wygeneruj KOMPLETNY, GOTOWY DO WYKONANIA kod CadQuery dla obudowy 3D:\n\n"
            f"{board_info}"
            f"Parametry:\n"
            f"- Margines PCB→ściana: {params.get('enclosure_margin', 3.0)} mm\n"
            f"- Grubość ścianki: {params.get('wall_thickness', 2.0)} mm\n"
            f"- Wysokość wewnętrzna: {params.get('enclosure_height', 30.0)} mm\n"
            f"- Zaokrąglenie narożników: {params.get('corner_radius', 2.0)} mm\n"
            f"- Standoffy: {'TAK' if params.get('gen_enclosure') else 'NIE'}\n"
            f"- Wieko: {'TAK' if params.get('gen_lid') else 'NIE'}\n\n"
            f"Wymagania kodu:\n"
            f"1. import cadquery as cq + from cadquery import exporters\n"
            f"2. Parametry jako zmienne (PCB_W, PCB_L, WALL itp.) na początku\n"
            f"3. Cztery standoffy M3 w narożnikach\n"
            f"4. Wycięcia na złącza USB/DC jeśli są na PCB\n"
            f"5. exporters.export(body, '{out_dir}/{base_name}_body.stl')\n"
            f"6. exporters.export(body, '{out_dir}/{base_name}_body.step')\n"
            f"7. Jeśli jest wieko: eksportuj jako osobny plik\n"
            f"8. Na końcu: print('Done: ...')\n\n"
            f"Zwróć TYLKO kompletny kod Python, bez opisu, gotowy do exec()."
        )

        full_response = []

        def _on_chunk(chunk):
            self._ai_output.insertPlainText(chunk)
            full_response.append(chunk)

        def _on_done(text):
            self._ai_progress.setVisible(False)
            self._log.append("✓ AI wygenerowało kod. Wykonuję…")
            self._execute_ai_code()

        self._ai.ask_async(
            prompt,
            system_key="stl_system",
            on_chunk=_on_chunk,
            on_done=_on_done,
            on_error=self._ai_error,
        )

    def _on_error(self, msg: str) -> None:
        self._gen_progress.setVisible(False)
        self._log.append(f"✗ Błąd: {msg}")
        QMessageBox.critical(self, "Błąd generowania 3D", msg)

    def _open_in_fusion(self) -> None:
        path = self._last_step or self._last_stl
        if not path:
            QMessageBox.warning(self, "Fusion 360", "Najpierw wygeneruj STEP/STL.")
            return
        self._open_file(path)

    def _open_in_slicer(self) -> None:
        if not self._last_stl:
            QMessageBox.warning(self, "Slicer", "Najpierw wygeneruj STL.")
            return
        self._open_file(self._last_stl)

    def _open_folder(self) -> None:
        path = self._last_stl or self._last_step
        if not path:
            return
        folder = str(Path(path).parent)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def _open_file(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.information(self, "Otwórz plik", f"Otwórz ręcznie:\n{path}\n\n{e}")

    # ── AI ────────────────────────────────────────────────────────────────────

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_design(self) -> None:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        self._ai.design_enclosure(
            params=self._get_params(),
            board=self._project.board if self._project else None,
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_from_text(self) -> None:
        text = self._ai_text_input.text().strip()
        if not text:
            return
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        board_info = ""
        if self._project.board:
            b = self._project.board
            board_info = f"PCB: {b.width_mm:.0f}x{b.height_mm:.0f}mm, {len(b.components)} komp."
        self._ai.ask_async(
            f"Użytkownik opisuje obudowę dla płytki PCB ({board_info}):\n\n'{text}'\n\n"
            "Na podstawie tego opisu:\n"
            "1. Zaproponuj dokładne wymiary obudowy (dł × szer × wys)\n"
            "2. Przelicz opis na parametry: margines, grubość ścian, wysokość\n"
            "3. Podaj pozycje i wymiary wszystkich otworów\n"
            "4. Zaproponuj materiał druku 3D i parametry slicera\n"
            "5. Wskaż potencjalne problemy z realizacją\n"
            "6. Wygeneruj pseudokod CadQuery dla tej obudowy",
            system_key="stl_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )
