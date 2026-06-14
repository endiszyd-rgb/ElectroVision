"""BOM panel — component table, export, AI analysis."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QMessageBox,
    QGroupBox, QTextEdit, QProgressBar, QSplitter
)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QFont

from src.core.project import Project
from src.ui.widgets.component_table import ComponentTableWidget
from src.generators.bom_generator import BOMGenerator
from src.ai.bridge import AIBridge


class BOMPanel(QWidget):
    component_selected = Signal(str)   # reference — for cross-panel highlight

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._count_label = QLabel("Brak komponentów")
        self._count_label.setStyleSheet("color: #aaa; font-size: 11px;")
        toolbar.addWidget(self._count_label)
        toolbar.addStretch()

        btn_refresh = QPushButton("🔄 Odśwież")
        btn_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(btn_refresh)

        self._group_combo = QComboBox()
        self._group_combo.addItems([
            "Bez grupowania", "Grupuj wg wartości",
            "Grupuj wg footprintu", "Grupuj wg typu",
        ])
        self._group_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self._group_combo)

        btn_csv   = QPushButton("📄 CSV")
        btn_excel = QPushButton("📊 Excel")
        btn_html  = QPushButton("🌐 HTML")
        btn_lcsc  = QPushButton("🏪 LCSC CSV")
        btn_csv.clicked.connect(self._export_csv)
        btn_excel.clicked.connect(self._export_excel)
        btn_html.clicked.connect(self._export_html)
        btn_lcsc.clicked.connect(self._export_lcsc)
        btn_lcsc.setToolTip("Eksportuj BOM w formacie LCSC/JLCPCB do złożenia SMT")
        toolbar.addWidget(btn_csv)
        toolbar.addWidget(btn_excel)
        toolbar.addWidget(btn_html)
        toolbar.addWidget(btn_lcsc)
        layout.addLayout(toolbar)

        # ── Splitter: table + AI ──────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        self._table = ComponentTableWidget()
        self._table.component_selected.connect(self.component_selected)
        splitter.addWidget(self._table)

        # AI analysis box
        ai_box = QGroupBox("🤖 AI — Analiza BOM")
        ai_layout = QVBoxLayout(ai_box)

        ai_btns = QHBoxLayout()
        btn_ai_analyze = QPushButton("Analizuj BOM")
        btn_ai_analyze.setToolTip("AI oceni BOM: dostępność, koszty, zamienniki, braki")
        btn_ai_analyze.clicked.connect(self._ai_analyze)
        ai_btns.addWidget(btn_ai_analyze)

        btn_ai_alt = QPushButton("Znajdź zamienniki")
        btn_ai_alt.setToolTip("AI zaproponuje tańsze lub łatwiej dostępne zamienniki")
        btn_ai_alt.clicked.connect(self._ai_alternatives)
        ai_btns.addWidget(btn_ai_alt)

        btn_ai_cost = QPushButton("Szacuj koszt")
        btn_ai_cost.clicked.connect(self._ai_cost)
        ai_btns.addWidget(btn_ai_cost)

        btn_ai_missing = QPushButton("Sprawdź braki")
        btn_ai_missing.setToolTip("AI sprawdzi czy brakuje filtrów, zabezpieczeń, kondensatorów")
        btn_ai_missing.clicked.connect(self._ai_missing)
        ai_btns.addWidget(btn_ai_missing)

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
        self._ai_output.setPlaceholderText("Analiza AI pojawi się tutaj…")
        self._ai_output.setMinimumHeight(120)
        ai_layout.addWidget(self._ai_output)
        splitter.addWidget(ai_box)

        splitter.setSizes([400, 200])
        layout.addWidget(splitter)

        # ── Summary ───────────────────────────────────────────────────────────
        summary_box = QGroupBox("Podsumowanie")
        summary_layout = QHBoxLayout(summary_box)
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        summary_layout.addWidget(self._summary_label)
        layout.addWidget(summary_box)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._ai.set_project_context(project_name=project.name, board=project.board)
        self._refresh()

    def _refresh(self) -> None:
        if not self._project.board:
            self._table.set_components([])
            self._count_label.setText("Brak komponentów")
            self._summary_label.setText("")
            return
        comps = self._project.board.components
        self._table.set_components(comps)
        self._count_label.setText(f"<b>{len(comps)}</b> komponentów")
        types: dict[str, int] = {}
        for c in comps:
            types[c.component_type] = types.get(c.component_type, 0) + 1
        parts = [f"<b>{v}</b>× {k}" for k, v in sorted(types.items(), key=lambda x: -x[1])]
        self._summary_label.setText("  |  ".join(parts))

    # ── Export ────────────────────────────────────────────────────────────────

    def _get_components(self):
        if not self._project.board:
            QMessageBox.warning(self, "BOM", "Brak projektu do eksportu.")
            return None
        return self._project.board.components

    def _export_csv(self) -> None:
        comps = self._get_components()
        if not comps:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz BOM jako CSV",
            f"{self._project.name}_bom.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            BOMGenerator.to_csv(comps, path)
            QMessageBox.information(self, "BOM", f"BOM wyeksportowany:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))

    def _export_excel(self) -> None:
        comps = self._get_components()
        if not comps:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz BOM jako Excel",
            f"{self._project.name}_bom.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            BOMGenerator.to_excel(comps, path)
            QMessageBox.information(self, "BOM", f"BOM wyeksportowany:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))

    def _export_lcsc(self) -> None:
        comps = self._get_components()
        if not comps:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz BOM LCSC/JLCPCB",
            f"{self._project.name}_bom_lcsc.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            from src.generators.jlcpcb_generator import generate_bom_csv
            csv_text = generate_bom_csv(self._project.board)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_text)
            QMessageBox.information(self, "LCSC BOM", f"Zapisano:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))

    def _export_html(self) -> None:
        comps = self._get_components()
        if not comps:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz BOM jako HTML",
            f"{self._project.name}_bom.html", "HTML (*.html)"
        )
        if not path:
            return
        try:
            BOMGenerator.to_html(comps, path, project_name=self._project.name)
            QMessageBox.information(self, "BOM", f"BOM HTML wyeksportowany:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", str(e))

    # ── AI ────────────────────────────────────────────────────────────────────

    def _start_ai(self) -> bool:
        if not self._project.board:
            self._ai_output.setPlainText("Załaduj projekt PCB.")
            return False
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        return True

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_analyze(self) -> None:
        if not self._start_ai():
            return
        self._ai.analyze_bom(
            self._project.board.components,
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_alternatives(self) -> None:
        if not self._start_ai():
            return
        comp_text = "\n".join(
            f"- {c.reference}: {c.value}, fp={c.footprint.split(':')[-1]}"
            for c in self._project.board.components
        )
        self._ai.ask_async(
            f"Dla każdego komponentu z listy BOM zaproponuj tańszy lub łatwiej dostępny zamiennik:\n{comp_text}\n\n"
            "Format odpowiedzi: ORYGINAŁ → ZAMIENNIK (producent, nr katalogowy, powód wyboru)",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_cost(self) -> None:
        if not self._start_ai():
            return
        comp_text = "\n".join(
            f"- {c.reference}: {c.value} ({c.component_type})"
            for c in self._project.board.components
        )
        self._ai.ask_async(
            f"Oszacuj koszt materiałów dla BOM:\n{comp_text}\n\n"
            "Podaj koszt dla serii: 1 szt, 10 szt, 100 szt.\n"
            "Uwzględnij: ceny rynkowe Mouser/Digi-Key, koszt PCB (JLCPCB 5 szt), "
            "koszt druku 3D obudowy (szacunkowo). Zakończ podsumowaniem.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_missing(self) -> None:
        if not self._start_ai():
            return
        comp_text = "\n".join(
            f"- {c.reference}: {c.value} ({c.component_type})"
            for c in self._project.board.components
        )
        self._ai.ask_async(
            f"Sprawdź czy w BOM brakuje ważnych komponentów:\n{comp_text}\n\n"
            "Szukaj braków:\n"
            "- Kondensatory blokujące (100nF przy każdym IC)\n"
            "- Rezystory pull-up/pull-down (I2C, przyciski, UART)\n"
            "- Filtrowanie zasilania (bulk caps, LC filter)\n"
            "- Zabezpieczenia (TVS, bezpiecznik, diody zabezpieczające)\n"
            "- Reset i boot piny (jeśli MCU)\n"
            "- Kryształ/oscylator (jeśli potrzebny)\n"
            "- Złącze programowania (JTAG, SWD, UART)\n"
            "Podaj konkretne wartości i footprinty brakujących elementów.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )
