"""Main application window."""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox, QLabel, QSplitter,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QEvent
from PySide6.QtGui import QAction, QKeySequence, QIcon, QCloseEvent

from src.core.project import Project
from src.core.parsers.kicad_parser import parse_kicad_pcb
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

        act_template = QAction("Nowy z szablonu…", self)
        act_template.setShortcut(QKeySequence("Ctrl+Shift+N"))
        act_template.triggered.connect(self._on_new_from_template)
        file_menu.addAction(act_template)

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

        file_menu.addSeparator()

        act_tray = QAction("Minimalizuj do traya przy zamknięciu", self)
        act_tray.setCheckable(True)
        act_tray.setChecked(True)
        act_tray.toggled.connect(lambda c: setattr(self, "_minimize_to_tray", c))
        file_menu.addAction(act_tray)

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
            "PCB 2D/3D", "BOM", "Kod MCU", "STL/STEP",
            "Schemat", "Trasowanie AI", "Koszty",
            "AI Asystent", "Walidacja", "Chmura", "Nauka AI",
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

        self._tabs.addTab(self._pcb_panel,     "🖥  PCB 2D / 3D")       # 0
        self._tabs.addTab(self._bom_panel,     "📋  BOM")                # 1
        self._tabs.addTab(self._code_panel,    "💻  Kod MCU")            # 2
        self._tabs.addTab(self._stl_panel,     "📦  STL / STEP 3D")     # 3
        self._tabs.addTab(self._sch_panel,     "📐  Schemat")            # 4
        self._tabs.addTab(self._routing_panel, "🗺  Trasowanie AI")      # 5
        self._tabs.addTab(self._cost_panel,    "💰  Koszty")             # 6
        self._tabs.addTab(self._ai_panel,      "🤖  AI Asystent")        # 7
        self._tabs.addTab(self._valid_panel,   "✅  Walidacja DRC")      # 8
        self._tabs.addTab(self._cloud_panel,   "☁  Chmura / Git")       # 9
        self._tabs.addTab(self._learn_panel,   "📚  Nauka AI")           # 10

        self.setCentralWidget(self._tabs)

        _notify = [
            self._pcb_panel, self._bom_panel, self._code_panel,
            self._stl_panel, self._sch_panel, self._routing_panel,
            self._cost_panel, self._ai_panel, self._valid_panel, self._cloud_panel,
        ]
        for panel in _notify:
            self.project_changed.connect(panel.on_project_changed)

    def _build_status(self) -> None:
        self._status_label = QLabel("Brak projektu")
        self.statusBar().addPermanentWidget(self._status_label)
        self.statusBar().showMessage("Witaj w ElectroVision!")

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

    # ── File actions ─────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        self._set_project(Project())
        self.statusBar().showMessage("Nowy projekt utworzony.")

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

    # ── Help ─────────────────────────────────────────────────────────────────

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Skróty klawiszowe",
            "<h3>Skróty klawiszowe ElectroVision</h3>"
            "<table>"
            "<tr><td><b>Ctrl+N</b></td><td>Nowy projekt</td></tr>"
            "<tr><td><b>Ctrl+Shift+N</b></td><td>Nowy z szablonu</td></tr>"
            "<tr><td><b>Ctrl+O</b></td><td>Importuj .kicad_pcb</td></tr>"
            "<tr><td><b>Ctrl+P</b></td><td>Eksportuj pełny raport PDF</td></tr>"
            "<tr><td><b>Alt+1..9</b></td><td>Przełącz zakładki 1-9</td></tr>"
            "<tr><td><b>F11</b></td><td>Pełny ekran</td></tr>"
            "<tr><td><b>F (w widoku)</b></td><td>Dopasuj widok do ekranu</td></tr>"
            "<tr><td><b>Scroll</b></td><td>Zoom w widokach 2D/3D</td></tr>"
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
