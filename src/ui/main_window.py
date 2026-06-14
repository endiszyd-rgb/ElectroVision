from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QMenuBar, QMenu, QFileDialog, QMessageBox, QLabel, QSplitter
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QAction, QKeySequence, QIcon
from pathlib import Path

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


class MainWindow(QMainWindow):
    project_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._project = Project()
        self.setWindowTitle("ElectroVision")
        self.setMinimumSize(1280, 800)
        self._build_menu()
        self._build_central()
        self._build_status()
        self._update_title()

    def _build_menu(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&Plik")
        act_new = QAction("Nowy projekt", self)
        act_new.setShortcut(QKeySequence.New)
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        act_import = QAction("Importuj KiCad (.kicad_pcb)…", self)
        act_import.setShortcut(QKeySequence("Ctrl+O"))
        act_import.triggered.connect(self._on_import_kicad)
        file_menu.addAction(act_import)

        file_menu.addSeparator()
        act_quit = QAction("Wyjdź", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = mb.addMenu("&Widok")
        act_fullscreen = QAction("Pełny ekran", self)
        act_fullscreen.setShortcut(QKeySequence.FullScreen)
        act_fullscreen.setCheckable(True)
        act_fullscreen.triggered.connect(self._on_fullscreen)
        view_menu.addAction(act_fullscreen)

        ai_menu = mb.addMenu("&AI")
        act_kb = QAction("Aktualizuj bazę wiedzy PCB/STL…", self)
        act_kb.triggered.connect(self._on_update_knowledge)
        ai_menu.addAction(act_kb)

        act_model = QAction("Wybierz model Ollama…", self)
        act_model.triggered.connect(self._on_choose_model)
        ai_menu.addAction(act_model)

        help_menu = mb.addMenu("&Pomoc")
        act_about = QAction("O programie", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _build_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.West)
        self._tabs.setMovable(True)

        self._pcb_panel    = PCBViewerPanel(self._project)
        self._bom_panel    = BOMPanel(self._project)
        self._code_panel   = CodeGenPanel(self._project)
        self._stl_panel    = STLGenPanel(self._project)
        self._ai_panel     = AIPanel(self._project)
        self._valid_panel  = ValidationPanel(self._project)
        self._cloud_panel  = CloudPanel(self._project)
        self._learn_panel  = URLLearningPanel()

        self._tabs.addTab(self._pcb_panel,   "🖥  PCB 2D / 3D")
        self._tabs.addTab(self._bom_panel,   "📋  BOM")
        self._tabs.addTab(self._code_panel,  "💻  Kod MCU")
        self._tabs.addTab(self._stl_panel,   "📦  STL / STEP 3D")
        self._tabs.addTab(self._ai_panel,    "🤖  AI Asystent")
        self._tabs.addTab(self._valid_panel, "✅  Walidacja DRC")
        self._tabs.addTab(self._cloud_panel, "☁  Chmura / Git")
        self._tabs.addTab(self._learn_panel, "📚  Nauka AI")

        self.setCentralWidget(self._tabs)

        for panel in [self._pcb_panel, self._bom_panel, self._code_panel,
                      self._stl_panel, self._ai_panel, self._valid_panel, self._cloud_panel]:
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

    def _on_new(self) -> None:
        self._set_project(Project())
        self.statusBar().showMessage("Nowy projekt utworzony.")

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

    def _on_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def _on_update_knowledge(self) -> None:
        self._tabs.setCurrentWidget(self._ai_panel)
        self._ai_panel.start_knowledge_update()

    def _on_choose_model(self) -> None:
        self._tabs.setCurrentWidget(self._ai_panel)
        self._ai_panel.show_model_selector()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "O programie",
            "<h2>ElectroVision 0.1.0</h2>"
            "<p>Aplikacja do projektowania PCB, generowania kodu, "
            "wizualizacji 3D oraz eksportu STL/STEP.</p>"
            "<p>Lokalny AI: <b>Ollama</b> (Llama 3 / Mistral)</p>"
        )
