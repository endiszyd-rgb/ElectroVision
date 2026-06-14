"""Main application window."""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox, QLabel, QSplitter,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon, QCloseEvent

from src.core.project import Project
from src.core.parsers.kicad_parser import parse_kicad_pcb
from src.core.project_io import save_project, load_project, add_recent, load_recent, clear_missing_recent
from src.ui.panels.pcb_viewer_panel import PCBViewerPanel
from src.ui.panels.bom_panel import BOMPanel
from src.ui.panels.code_gen_panel import CodeGenPanel
from src.ui.panels.stl_gen_panel import STLGenPanel
from src.ui.panels.ai_panel import AIPanel
from src.ui.panels.validation_panel import ValidationPanel
from src.ui.panels.cloud_panel import CloudPanel
from src.ui.panels.url_learning_panel import URLLearningPanel
from src.ui.panels.schematic_panel import SchematicPanel
from src.ui.panels.cost_panel import CostPanel
from src.ui.panels.routing_panel import RoutingPanel
from src.ui.panels.pcb_editor_panel import PCBEditorPanel
from src.ui.panels.components_panel import ComponentsPanel
from src.ui.panels.net_inspector_panel import NetInspectorPanel
from src.ui.tray import TrayIcon


class MainWindow(QMainWindow):
    project_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._project = Project()
        self._minimize_to_tray = True
        self.setWindowTitle("ElectroVision")
        self.setMinimumSize(1280, 800)
        self._build_menu()
        self._build_central()
        self._build_status()
        self._build_tray()
        self._update_title()
        self._load_startup_settings()

    def _load_startup_settings(self) -> None:
        try:
            from src.ui.dialogs.settings_dialog import load_settings
            self._apply_settings(load_settings())
        except Exception:
            pass

    # ── Tray ─────────────────────────────────────────────────────────────────

    def _build_tray(self) -> None:
        self._tray = TrayIcon(self, self)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._minimize_to_tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(
                "ElectroVision",
                "Aplikacja działa w tle. Kliknij dwukrotnie ikonę, aby przywrócić.",
                self._tray.Information,
                2000,
            )
            event.ignore()
        else:
            event.accept()

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # ── Plik ──────────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&Plik")

        act_new = QAction("Nowy projekt", self)
        act_new.setShortcut(QKeySequence.New)
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        act_ai_gen = QAction("🤖 Nowy projekt z opisu AI…", self)
        act_ai_gen.setShortcut(QKeySequence("Ctrl+Shift+A"))
        act_ai_gen.triggered.connect(self._on_new_from_ai)
        file_menu.addAction(act_ai_gen)

        act_template = QAction("Nowy z szablonu…", self)
        act_template.setShortcut(QKeySequence("Ctrl+Shift+N"))
        act_template.triggered.connect(self._on_new_from_template)
        file_menu.addAction(act_template)

        file_menu.addSeparator()

        act_save = QAction("Zapisz projekt (.evproj)", self)
        act_save.setShortcut(QKeySequence.Save)
        act_save.triggered.connect(self._on_save)
        file_menu.addAction(act_save)

        act_save_as = QAction("Zapisz projekt jako…", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

        act_open_ev = QAction("Otwórz projekt (.evproj)…", self)
        act_open_ev.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_ev.triggered.connect(self._on_open_evproj)
        file_menu.addAction(act_open_ev)

        self._recent_menu = file_menu.addMenu("Ostatnie projekty")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)

        file_menu.addSeparator()

        act_import = QAction("Importuj KiCad (.kicad_pcb)…", self)
        act_import.setShortcut(QKeySequence("Ctrl+O"))
        act_import.triggered.connect(self._on_import_kicad)
        file_menu.addAction(act_import)

        act_import_sch = QAction("Importuj schemat (.kicad_sch)…", self)
        act_import_sch.triggered.connect(self._on_import_sch)
        file_menu.addAction(act_import_sch)

        file_menu.addSeparator()

        # Export submenu
        export_menu = file_menu.addMenu("Eksportuj…")

        act_pdf_bom = QAction("PDF — Bill of Materials", self)
        act_pdf_bom.triggered.connect(self._export_pdf_bom)
        export_menu.addAction(act_pdf_bom)

        act_pdf_cost = QAction("PDF — Raport kosztów", self)
        act_pdf_cost.triggered.connect(self._export_pdf_cost)
        export_menu.addAction(act_pdf_cost)

        act_pdf_full = QAction("PDF — Pełny raport projektu", self)
        act_pdf_full.setShortcut(QKeySequence("Ctrl+P"))
        act_pdf_full.triggered.connect(self._export_pdf_full)
        export_menu.addAction(act_pdf_full)

        export_menu.addSeparator()

        act_gerber = QAction("Gerber + Drill (produkcja)", self)
        act_gerber.setShortcut(QKeySequence("Ctrl+G"))
        act_gerber.triggered.connect(self._export_gerber)
        export_menu.addAction(act_gerber)

        file_menu.addSeparator()

        act_tray = QAction("Minimalizuj do traya przy zamknięciu", self)
        act_tray.setCheckable(True)
        act_tray.setChecked(True)
        act_tray.toggled.connect(lambda c: setattr(self, "_minimize_to_tray", c))
        file_menu.addAction(act_tray)

        act_settings = QAction("Ustawienia…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self._on_settings)
        file_menu.addAction(act_settings)

        act_quit = QAction("Wyjdź", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self._quit_app)
        file_menu.addAction(act_quit)

        # ── Widok ─────────────────────────────────────────────────────────────
        view_menu = mb.addMenu("&Widok")
        act_fullscreen = QAction("Pełny ekran", self)
        act_fullscreen.setShortcut(QKeySequence.FullScreen)
        act_fullscreen.setCheckable(True)
        act_fullscreen.triggered.connect(self._on_fullscreen)
        view_menu.addAction(act_fullscreen)

        view_menu.addSeparator()
        for i, label in enumerate([
            "PCB 2D/3D", "Edytor PCB", "BOM", "Kod MCU", "STL/STEP",
            "Schemat", "Trasowanie AI", "Koszty",
            "Komponenty", "Sieci", "AI Asystent", "Walidacja",
        ]):
            act = QAction(label, self)
            if i < 9:
                act.setShortcut(QKeySequence(f"Alt+{i+1}"))
            idx = i
            act.triggered.connect(lambda _, x=idx: self._tabs.setCurrentIndex(x))
            view_menu.addAction(act)

        # ── AI ────────────────────────────────────────────────────────────────
        ai_menu = mb.addMenu("&AI")
        act_kb = QAction("Aktualizuj bazę wiedzy PCB/STL…", self)
        act_kb.triggered.connect(self._on_update_knowledge)
        ai_menu.addAction(act_kb)

        act_model = QAction("Wybierz model Ollama…", self)
        act_model.triggered.connect(self._on_choose_model)
        ai_menu.addAction(act_model)

        # ── Projekt ───────────────────────────────────────────────────────────
        project_menu = mb.addMenu("&Projekt")

        act_tmpl = QAction("Wybierz szablon…", self)
        act_tmpl.triggered.connect(self._on_new_from_template)
        project_menu.addAction(act_tmpl)

        project_menu.addSeparator()

        act_cost = QAction("Przelicz koszty", self)
        act_cost.triggered.connect(lambda: (
            self._tabs.setCurrentWidget(self._cost_panel),
            self._cost_panel._recalculate()
        ))
        project_menu.addAction(act_cost)

        act_drc = QAction("Sprawdź DRC", self)
        act_drc.triggered.connect(lambda: (
            self._tabs.setCurrentWidget(self._routing_panel),
            self._routing_panel._run_drc()
        ))
        project_menu.addAction(act_drc)

        # ── Pomoc ─────────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Pomoc")
        act_shortcuts = QAction("Skróty klawiszowe", self)
        act_shortcuts.triggered.connect(self._show_shortcuts)
        help_menu.addAction(act_shortcuts)

        act_about = QAction("O programie", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _build_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.West)
        self._tabs.setMovable(True)

        self._pcb_panel      = PCBViewerPanel(self._project)
        self._pcb_editor     = PCBEditorPanel(self._project)
        self._bom_panel      = BOMPanel(self._project)
        self._code_panel     = CodeGenPanel(self._project)
        self._stl_panel      = STLGenPanel(self._project)
        self._sch_panel      = SchematicPanel(self._project)
        self._routing_panel  = RoutingPanel(self._project)
        self._cost_panel     = CostPanel(self._project)
        self._ai_panel       = AIPanel(self._project)
        self._valid_panel    = ValidationPanel(self._project)
        self._cloud_panel    = CloudPanel(self._project)
        self._learn_panel    = URLLearningPanel()
        self._comp_panel     = ComponentsPanel(self._project)
        self._net_panel      = NetInspectorPanel(self._project)

        self._tabs.addTab(self._pcb_panel,     "🖥  PCB 2D / 3D")       # 0
        self._tabs.addTab(self._pcb_editor,    "✏  Edytor PCB")         # 1
        self._tabs.addTab(self._bom_panel,     "📋  BOM")                # 2
        self._tabs.addTab(self._code_panel,    "💻  Kod MCU")            # 3
        self._tabs.addTab(self._stl_panel,     "📦  STL / STEP 3D")     # 4
        self._tabs.addTab(self._sch_panel,     "📐  Schemat")            # 5
        self._tabs.addTab(self._routing_panel, "🗺  Trasowanie AI")      # 6
        self._tabs.addTab(self._cost_panel,    "💰  Koszty")             # 7
        self._tabs.addTab(self._comp_panel,    "🔍  Komponenty")         # 8
        self._tabs.addTab(self._net_panel,     "🔌  Sieci")              # 9
        self._tabs.addTab(self._ai_panel,      "🤖  AI Asystent")        # 10
        self._tabs.addTab(self._valid_panel,   "✅  Walidacja DRC")      # 11
        self._tabs.addTab(self._cloud_panel,   "☁  Chmura / Git")       # 12
        self._tabs.addTab(self._learn_panel,   "📚  Nauka AI")           # 13

        self.setCentralWidget(self._tabs)

        _notify = [
            self._pcb_panel, self._pcb_editor, self._bom_panel, self._code_panel,
            self._stl_panel, self._sch_panel, self._routing_panel,
            self._cost_panel, self._ai_panel, self._valid_panel, self._cloud_panel,
            self._comp_panel, self._net_panel,
        ]
        for panel in _notify:
            self.project_changed.connect(panel.on_project_changed)

        # Connect ComponentsPanel → PCBEditorPanel for place-from-DB
        self._comp_panel.component_add_requested.connect(self._on_comp_add_requested)

        # Connect NetInspector → PCBEditorPanel for highlight
        self._net_panel.net_highlight_requested.connect(self._on_net_highlight)

    def _build_status(self) -> None:
        self._status_label = QLabel("Brak projektu")
        self.statusBar().addPermanentWidget(self._status_label)

        self._ollama_dot = QLabel("⚫ Ollama")
        self._ollama_dot.setStyleSheet("color: #666; font-size: 10px; padding: 0 6px;")
        self._ollama_dot.setToolTip("Status serwera Ollama (AI lokalny)")
        self.statusBar().addPermanentWidget(self._ollama_dot)

        self._ollama_timer = QTimer(self)
        self._ollama_timer.timeout.connect(self._check_ollama_status)
        self._ollama_timer.start(8000)  # check every 8 s
        self._check_ollama_status()     # immediate first check

        self.statusBar().showMessage("Witaj w ElectroVision!")

    def _check_ollama_status(self) -> None:
        try:
            from src.ai.ollama_utils import is_ollama_running
            if is_ollama_running():
                self._ollama_dot.setText("🟢 Ollama")
                self._ollama_dot.setStyleSheet("color: #4caf50; font-size: 10px; padding: 0 6px;")
                self._ollama_dot.setToolTip("Ollama działa — AI dostępne")
            else:
                self._ollama_dot.setText("🔴 Ollama")
                self._ollama_dot.setStyleSheet("color: #f44336; font-size: 10px; padding: 0 6px;")
                self._ollama_dot.setToolTip("Ollama niedostępne — uruchom 'ollama serve'")
        except Exception:
            self._ollama_dot.setText("⚫ Ollama")
            self._ollama_dot.setStyleSheet("color: #666; font-size: 10px; padding: 0 6px;")

    def _update_title(self) -> None:
        name = self._project.name
        path = self._project.save_path_str()
        suffix = f" — {path}" if path else ""
        self.setWindowTitle(f"ElectroVision — {name}{suffix}")
        self._status_label.setText(name)

    def _set_project(self, project: Project) -> None:
        self._project = project
        self._update_title()
        self.project_changed.emit(project)

    # ── Cross-panel signals ───────────────────────────────────────────────────

    def _on_comp_add_requested(self, comp) -> None:
        """Route 'place component' from ComponentsPanel → PCBEditorPanel."""
        self._tabs.setCurrentWidget(self._pcb_editor)
        self._pcb_editor._start_place(comp.reference, comp.value, comp.footprint)

    def _on_net_highlight(self, net_name: str) -> None:
        """Pass net highlight request to PCB editor."""
        if hasattr(self._pcb_editor, "highlight_net"):
            self._pcb_editor.highlight_net(net_name)

    # ── Recent menu ───────────────────────────────────────────────────────────

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = clear_missing_recent()
        if not recent:
            act = QAction("(brak)", self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
            return
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda _, p=path: self._open_evproj(p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        act_clear = QAction("Wyczyść listę", self)
        act_clear.triggered.connect(lambda: clear_missing_recent())
        self._recent_menu.addAction(act_clear)

    # ── File actions ─────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        self._set_project(Project())
        self.statusBar().showMessage("Nowy projekt utworzony.")

    def _on_new_from_ai(self) -> None:
        from src.ui.dialogs.ai_project_dialog import AIProjectDialog
        dlg = AIProjectDialog(self)
        if dlg.exec():
            proj = dlg.result_project()
            if proj:
                self._set_project(proj)
                n_comp = len(proj.board.components) if proj.board else 0
                self.statusBar().showMessage(
                    f"Projekt AI: {proj.name}  |  "
                    f"Komponentów: {n_comp}  |  "
                    f"Otwarto w Edytorze PCB — ułóż ścieżki i zapisz."
                )
                self._tabs.setCurrentWidget(self._pcb_editor)

    def _on_new_from_template(self) -> None:
        from src.ui.dialogs.template_dialog import TemplateDialog
        dlg = TemplateDialog(self)
        if dlg.exec():
            proj = dlg.result_project()
            if proj:
                self._set_project(proj)
                self.statusBar().showMessage(
                    f"Projekt z szablonu: {proj.name}  |  "
                    f"Komponentów: {len(proj.board.components) if proj.board else 0}"
                )
                self._tabs.setCurrentIndex(0)

    def _on_import_kicad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Otwórz plik KiCad", "",
            "KiCad PCB (*.kicad_pcb);;Wszystkie pliki (*)"
        )
        if not path:
            return
        try:
            board = parse_kicad_pcb(path)
            project = Project(
                name=Path(path).stem,
                path=Path(path),
                board=board,
            )
            self._set_project(project)
            self.statusBar().showMessage(
                f"Załadowano: {Path(path).name}  |  "
                f"Komponentów: {len(board.components)}  |  "
                f"Ścieżek: {len(board.traces)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Błąd importu", str(e))

    def _on_import_sch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Otwórz schemat KiCad", "",
            "KiCad Schematic (*.kicad_sch);;Wszystkie pliki (*)"
        )
        if path:
            self._tabs.setCurrentWidget(self._sch_panel)
            self._sch_panel._load_sch(path)

    def _on_save(self) -> None:
        if not self._project.board:
            QMessageBox.warning(self, "Brak projektu", "Najpierw utwórz lub załaduj projekt PCB.")
            return
        existing = self._project.save_path_str()
        if existing and existing.endswith(".evproj"):
            self._do_save(existing)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        if not self._project.board:
            QMessageBox.warning(self, "Brak projektu", "Najpierw utwórz lub załaduj projekt PCB.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz projekt", f"{self._project.name}.evproj",
            "ElectroVision Project (*.evproj)"
        )
        if path:
            self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            save_project(self._project, path)
            add_recent(path)
            self._project = Project(
                name=self._project.name,
                path=Path(path),
                board=self._project.board,
            )
            self._update_title()
            self.statusBar().showMessage(f"Zapisano: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd zapisu", str(e))

    def _on_open_evproj(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Otwórz projekt ElectroVision", "",
            "ElectroVision Project (*.evproj);;Wszystkie pliki (*)"
        )
        if path:
            self._open_evproj(path)

    def _open_evproj(self, path: str) -> None:
        try:
            project = load_project(path)
            add_recent(path)
            self._set_project(project)
            self.statusBar().showMessage(
                f"Załadowano: {Path(path).name}  |  "
                f"Komponentów: {len(project.board.components) if project.board else 0}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Błąd odczytu", str(e))

    # ── PDF export ────────────────────────────────────────────────────────────

    def _check_board(self) -> bool:
        if not self._project.board:
            QMessageBox.warning(self, "Brak projektu",
                                "Najpierw załaduj lub stwórz projekt PCB.")
            return False
        return True

    def _export_pdf_bom(self) -> None:
        if not self._check_board():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz BOM PDF", f"{self._project.name}_bom.pdf", "PDF (*.pdf)"
        )
        if path:
            try:
                from src.generators.pdf_generator import PDFGenerator
                PDFGenerator(self._project).export_bom(path)
                QMessageBox.information(self, "PDF", f"Zapisano: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd PDF", str(e))

    def _export_pdf_cost(self) -> None:
        if not self._check_board():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz raport kosztów PDF", f"{self._project.name}_cost.pdf", "PDF (*.pdf)"
        )
        if path:
            try:
                from src.generators.pdf_generator import PDFGenerator
                PDFGenerator(self._project).export_cost(path)
                QMessageBox.information(self, "PDF", f"Zapisano: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd PDF", str(e))

    def _export_pdf_full(self) -> None:
        if not self._check_board():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz pełny raport PDF", f"{self._project.name}_raport.pdf", "PDF (*.pdf)"
        )
        if path:
            try:
                from src.generators.pdf_generator import PDFGenerator
                PDFGenerator(self._project).export_full_report(path)
                QMessageBox.information(self, "PDF", f"Raport zapisany: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd PDF", str(e))

    def _export_gerber(self) -> None:
        if not self._check_board():
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "Wybierz folder dla plików Gerber",
            str(Path.home()),
        )
        if not out_dir:
            return
        try:
            from src.generators.gerber_generator import GerberGenerator
            gen = GerberGenerator(self._project.board, self._project.name)
            files = gen.export_all(out_dir)
            QMessageBox.information(
                self, "Gerber",
                f"Wygenerowano {len(files)} plików w:\n{out_dir}\n\n"
                + "\n".join(Path(f).name for f in files)
            )
        except Exception as e:
            QMessageBox.critical(self, "Błąd Gerber", str(e))

    # ── View actions ─────────────────────────────────────────────────────────

    def _on_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    # ── AI actions ────────────────────────────────────────────────────────────

    def _on_update_knowledge(self) -> None:
        self._tabs.setCurrentWidget(self._ai_panel)
        self._ai_panel.start_knowledge_update()

    def _on_choose_model(self) -> None:
        self._tabs.setCurrentWidget(self._ai_panel)
        self._ai_panel.show_model_selector()

    def _on_settings(self) -> None:
        from src.ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, s: dict) -> None:
        from src.ai.bridge import AIBridge
        AIBridge.instance().set_model(s["ollama_model"])
        from src.validators.pcb_drc import PCBValidator
        PCBValidator.MIN_TRACE_WIDTH_MM  = s["drc_min_trace"]
        PCBValidator.MIN_CLEARANCE_MM    = s["drc_min_clearance"]
        PCBValidator.MIN_VIA_DRILL_MM    = s["drc_min_via_drill"]
        PCBValidator.MIN_VIA_ANNULAR_MM  = s["drc_min_annular"]
        PCBValidator.MIN_EDGE_CLEARANCE  = s["drc_edge_clearance"]
        self.statusBar().showMessage("Ustawienia zapisane.")

    # ── Help ─────────────────────────────────────────────────────────────────

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Skróty klawiszowe",
            "<h3>Skróty klawiszowe ElectroVision</h3>"
            "<table>"
            "<tr><td><b>Ctrl+N</b></td><td>Nowy projekt</td></tr>"
            "<tr><td><b>Ctrl+Shift+A</b></td><td>Nowy projekt z opisu AI</td></tr>"
            "<tr><td><b>Ctrl+Shift+N</b></td><td>Nowy z szablonu</td></tr>"
            "<tr><td><b>Ctrl+S</b></td><td>Zapisz projekt (.evproj)</td></tr>"
            "<tr><td><b>Ctrl+Shift+S</b></td><td>Zapisz projekt jako…</td></tr>"
            "<tr><td><b>Ctrl+Shift+O</b></td><td>Otwórz projekt (.evproj)</td></tr>"
            "<tr><td><b>Ctrl+O</b></td><td>Importuj .kicad_pcb</td></tr>"
            "<tr><td><b>Ctrl+G</b></td><td>Eksportuj Gerber + Drill</td></tr>"
            "<tr><td><b>Ctrl+P</b></td><td>Eksportuj pełny raport PDF</td></tr>"
            "<tr><td><b>Ctrl+,</b></td><td>Ustawienia aplikacji</td></tr>"
            "<tr><td><b>Ctrl+F (edytor PCB)</b></td><td>Znajdź komponent</td></tr>"
            "<tr><td><b>Alt+1..9</b></td><td>Przełącz zakładki 1-9</td></tr>"
            "<tr><td><b>F11</b></td><td>Pełny ekran</td></tr>"
            "<tr><td><b>F (w edytorze PCB)</b></td><td>Dopasuj widok</td></tr>"
            "<tr><td><b>S/R/V/X (edytor PCB)</b></td><td>Tryb: Select/Route/Via/Delete</td></tr>"
            "<tr><td><b>Space (edytor PCB)</b></td><td>Obróć komponent o 90°</td></tr>"
            "<tr><td><b>M (edytor PCB)</b></td><td>Lustro komponentu</td></tr>"
            "<tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>Cofnij / Ponów</td></tr>"
            "<tr><td><b>Enter (edytor PCB)</b></td><td>Zakończ trasowanie</td></tr>"
            "<tr><td><b>Esc (edytor PCB)</b></td><td>Anuluj akcję</td></tr>"
            "<tr><td><b>Scroll</b></td><td>Zoom w widokach 2D/3D/Edytor</td></tr>"
            "<tr><td><b>PPM / Środkowy</b></td><td>Przesuń widok</td></tr>"
            "</table>"
        )

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "O programie",
            "<h2>ElectroVision 0.2.0</h2>"
            "<p>Aplikacja do projektowania PCB, generowania kodu, "
            "wizualizacji 3D oraz eksportu STL/STEP.</p>"
            "<p><b>Moduły:</b></p>"
            "<ul>"
            "<li>PCB 2D/3D — przeglądarka i analizator płytki</li>"
            "<li>Schemat — parser i podgląd .kicad_sch</li>"
            "<li>BOM — lista komponentów + eksport CSV/Excel/PDF</li>"
            "<li>Kod MCU — generator kodu ESP32/STM32/RP2040</li>"
            "<li>STL/STEP 3D — generowanie obudów AI + przeglądarka</li>"
            "<li>Trasowanie AI — sugestie routing + DRC</li>"
            "<li>Koszty — kosztorys + integracja LCSC</li>"
            "<li>AI Asystent — lokalny LLM (Ollama + RAG)</li>"
            "<li>Szablony — gotowe projekty startowe</li>"
            "<li>Nauka AI — trening z URL/PDF/tekstu</li>"
            "</ul>"
            "<p>Lokalny AI: <b>Ollama</b> (Llama 3 / Mistral / CodeLlama)</p>"
        )

    def _quit_app(self) -> None:
        self._minimize_to_tray = False
        self.close()
        QApplication.quit()
