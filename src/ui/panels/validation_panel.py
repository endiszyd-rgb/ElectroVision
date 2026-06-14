"""Validation panel — PCB DRC + STL checks + AI explanations."""
import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox, QProgressBar,
    QHeaderView, QTextEdit, QTabWidget, QFileDialog, QSplitter,
    QCheckBox
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from PySide6.QtGui import QColor, QFont

from src.core.project import Project
from src.ai.bridge import AIBridge

_POS_RE = re.compile(r"\(?([-\d.]+)[,\s]+([-\d.]+)\)?")


class _ValidateThread(QThread):
    from PySide6.QtCore import Signal
    pcb_done = Signal(list)
    stl_done = Signal(list)
    error    = Signal(str)

    def __init__(self, project: Project, stl_path: str = ""):
        super().__init__()
        self._project  = project
        self._stl_path = stl_path

    def run(self) -> None:
        try:
            from src.validators.pcb_drc import PCBValidator
            pcb_issues = PCBValidator(self._project.board).run() if self._project.board else []
            self.pcb_done.emit(pcb_issues)

            if self._stl_path:
                from src.validators.stl_validator import STLValidator
                stl_issues = STLValidator(self._stl_path).run()
                self.stl_done.emit(stl_issues)
            else:
                self.stl_done.emit([])
        except Exception as e:
            self.error.emit(str(e))


class ValidationPanel(QWidget):
    drc_violations_ready = Signal(list)   # list of {x, y, message, severity}

    SEVERITY_COLORS = {
        "error":   QColor(220, 60,  60),
        "warning": QColor(220, 180, 50),
        "info":    QColor(80,  180, 220),
    }

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project  = project
        self._ai       = AIBridge.instance()
        self._thread: _ValidateThread | None = None
        self._pcb_issues: list[dict] = []
        self._stl_path  = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        btn_run = QPushButton("▶  Uruchom walidację")
        btn_run.setStyleSheet("font-weight: bold;")
        btn_run.clicked.connect(self._run_validation)
        toolbar.addWidget(btn_run)

        self._stl_path_label = QLabel("Brak pliku STL/STEP")
        self._stl_path_label.setStyleSheet("color: #888; font-size: 10px;")
        toolbar.addWidget(self._stl_path_label)

        btn_set_stl = QPushButton("📂 Wskaż STL/STEP…")
        btn_set_stl.clicked.connect(self._pick_stl)
        toolbar.addWidget(btn_set_stl)

        toolbar.addStretch()
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-weight: bold;")
        toolbar.addWidget(self._summary_label)
        layout.addLayout(toolbar)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        layout.addWidget(self._progress)

        # ── Main splitter: tables | AI ────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Results tabs
        self._tabs = QTabWidget()

        self._pcb_table = QTableWidget(0, 4)
        self._pcb_table.setHorizontalHeaderLabels(["Rodzaj", "Pozycja", "Opis", "Sugestia"])
        self._pcb_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._pcb_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._pcb_table.setAlternatingRowColors(True)
        self._pcb_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._pcb_table.itemSelectionChanged.connect(self._on_pcb_row_selected)
        self._tabs.addTab(self._pcb_table, "PCB DRC")

        self._stl_table = QTableWidget(0, 3)
        self._stl_table.setHorizontalHeaderLabels(["Rodzaj", "Element", "Opis"])
        self._stl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._stl_table.setAlternatingRowColors(True)
        self._stl_table.itemSelectionChanged.connect(self._on_stl_row_selected)
        self._tabs.addTab(self._stl_table, "STL / STEP")

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._tabs.addTab(self._log, "Log")

        splitter.addWidget(self._tabs)

        # AI explanation box
        ai_box = QGroupBox("🤖 AI — Wyjaśnienie i naprawa błędów")
        ai_layout = QVBoxLayout(ai_box)

        ai_btns = QHBoxLayout()
        btn_explain_all = QPushButton("Wyjaśnij wszystkie błędy DRC")
        btn_explain_all.clicked.connect(self._ai_explain_all)
        ai_btns.addWidget(btn_explain_all)

        btn_explain_sel = QPushButton("Wyjaśnij wybrany błąd")
        btn_explain_sel.clicked.connect(self._ai_explain_selected)
        ai_btns.addWidget(btn_explain_sel)

        btn_fix_plan = QPushButton("Plan naprawy krok po kroku")
        btn_fix_plan.clicked.connect(self._ai_fix_plan)
        ai_btns.addWidget(btn_fix_plan)

        btn_clear = QPushButton("✕")
        btn_clear.setMaximumWidth(28)
        btn_clear.clicked.connect(lambda: self._ai_output.clear())
        ai_btns.addWidget(btn_clear)
        ai_layout.addLayout(ai_btns)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(6)
        ai_layout.addWidget(self._ai_progress)

        self._ai_output = QTextEdit()
        self._ai_output.setReadOnly(True)
        self._ai_output.setFont(QFont("Consolas", 9))
        self._ai_output.setPlaceholderText(
            "Kliknij 'Wyjaśnij błędy DRC' po uruchomieniu walidacji, "
            "aby AI wyjaśniło każdy błąd i zaproponowało naprawę…"
        )
        self._ai_output.setMinimumHeight(160)
        ai_layout.addWidget(self._ai_output)
        splitter.addWidget(ai_box)

        splitter.setSizes([350, 250])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._ai.set_project_context(project_name=project.name, board=project.board)

    def _pick_stl(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Wskaż plik STL/STEP", "", "3D Files (*.stl *.step *.stp)"
        )
        if path:
            self._stl_path = path
            name = path.replace("\\", "/").split("/")[-1]
            self._stl_path_label.setText(name)

    def _run_validation(self) -> None:
        if not self._project.board and not self._stl_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Walidacja", "Brak projektu PCB ani pliku STL.")
            return
        self._pcb_table.setRowCount(0)
        self._stl_table.setRowCount(0)
        self._log.clear()
        self._pcb_issues = []
        self._progress.setVisible(True)
        self._log.append("Uruchamianie walidacji PCB + STL…")
        self._thread = _ValidateThread(self._project, self._stl_path)
        self._thread.pcb_done.connect(self._on_pcb_done)
        self._thread.stl_done.connect(self._on_stl_done)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(lambda: self._progress.setVisible(False))
        self._thread.start()

    @Slot(list)
    def _on_pcb_done(self, issues: list) -> None:
        self._pcb_issues = issues
        errors   = sum(1 for i in issues if i.get("severity") == "error")
        warnings = sum(1 for i in issues if i.get("severity") == "warning")
        infos    = sum(1 for i in issues if i.get("severity") == "info")
        self._log.append(
            f"PCB DRC: {len(issues)} wyników — "
            f"🔴 {errors} błędów, 🟡 {warnings} ostrzeżeń, 🔵 {infos} info"
        )
        self._tabs.setCurrentIndex(0)
        self._pcb_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            sev   = issue.get("severity", "info")
            color = self.SEVERITY_COLORS.get(sev, QColor(200, 200, 200))
            for col, text in enumerate([
                sev.upper(),
                issue.get("position", ""),
                issue.get("message", ""),
                issue.get("suggestion", ""),
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(color)
                item.setData(Qt.UserRole, issue)
                self._pcb_table.setItem(row, col, item)
        status_color = "🔴" if errors else ("🟡" if warnings else "🟢")
        self._summary_label.setText(f"{status_color} PCB: {errors}E {warnings}W {infos}I")

        # Build overlay markers for PCB editor
        markers = []
        for issue in issues:
            pos = issue.get("position", "")
            m = _POS_RE.search(pos)
            if m:
                markers.append({
                    "x": float(m.group(1)),
                    "y": float(m.group(2)),
                    "message": issue.get("message", ""),
                    "severity": issue.get("severity", "error"),
                })
        self.drc_violations_ready.emit(markers)

    @Slot(list)
    def _on_stl_done(self, issues: list) -> None:
        self._log.append(f"STL/STEP: {len(issues)} wyników")
        self._stl_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            sev   = issue.get("severity", "info")
            color = self.SEVERITY_COLORS.get(sev, QColor(200, 200, 200))
            for col, text in enumerate([
                sev.upper(),
                issue.get("element", ""),
                issue.get("message", ""),
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(color)
                self._stl_table.setItem(row, col, item)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._log.append(f"⚠ Błąd walidacji: {msg}")

    def _on_pcb_row_selected(self) -> None:
        items = self._pcb_table.selectedItems()
        if items:
            issue = items[0].data(Qt.UserRole)
            if issue and isinstance(issue, dict):
                self._ai_output.setPlainText(
                    f"Błąd: {issue.get('message','')}\n"
                    f"Sugestia: {issue.get('suggestion','')}\n\n"
                    "Kliknij 'Wyjaśnij wybrany błąd' dla szczegółowej analizy AI."
                )

    def _on_stl_row_selected(self) -> None:
        pass

    # ── AI ────────────────────────────────────────────────────────────────────

    def _start_ai(self) -> bool:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        return True

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_explain_all(self) -> None:
        if not self._pcb_issues:
            self._ai_output.setPlainText("Najpierw uruchom walidację DRC.")
            return
        self._start_ai()
        self._ai.explain_drc_issues(
            self._pcb_issues,
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_explain_selected(self) -> None:
        items = self._pcb_table.selectedItems()
        if not items:
            self._ai_output.setPlainText("Wybierz wiersz z błędem DRC.")
            return
        issue = items[0].data(Qt.UserRole)
        if not issue:
            return
        self._start_ai()
        self._ai.ask_async(
            f"Wyjaśnij dokładnie ten błąd DRC:\n"
            f"Typ: {issue.get('severity','?').upper()}\n"
            f"Pozycja: {issue.get('position','')}\n"
            f"Komunikat: {issue.get('message','')}\n"
            f"Sugestia: {issue.get('suggestion','')}\n\n"
            "Podaj:\n"
            "1. Dlaczego ten błąd jest ważny (co się stanie jeśli go zignorujemy)\n"
            "2. Dokładna procedura naprawy w KiCad krok po kroku\n"
            "3. Czy jest możliwy wyjątek DRC (kiedy i jak go dodać)\n"
            "4. Jak zapobiec temu błędowi w przyszłości",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_fix_plan(self) -> None:
        if not self._pcb_issues:
            self._ai_output.setPlainText("Najpierw uruchom walidację DRC.")
            return
        self._start_ai()
        errors = [i for i in self._pcb_issues if i.get("severity") == "error"]
        warnings = [i for i in self._pcb_issues if i.get("severity") == "warning"]
        summary = (
            f"Błędy ({len(errors)}): " +
            ", ".join(i.get("message","")[:60] for i in errors[:5]) + "\n"
            f"Ostrzeżenia ({len(warnings)}): " +
            ", ".join(i.get("message","")[:60] for i in warnings[:5])
        )
        self._ai.ask_async(
            f"Stwórz priorytetowy plan naprawy błędów DRC:\n{summary}\n\n"
            "Format: numerowana lista kroków od najważniejszego do najmniej ważnego.\n"
            "Każdy krok: co zrobić → gdzie w KiCad → efekt.\n"
            "Na końcu: ile czasu szacunkowo zajmie cała naprawa.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )
