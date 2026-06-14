from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QComboBox, QGroupBox, QSplitter, QProgressBar,
    QListWidget, QListWidgetItem, QLineEdit, QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, Slot, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCursor

from src.core.project import Project


class _AIWorker(QObject):
    chunk_received = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, prompt: str, system: str, model: str):
        super().__init__()
        self._prompt = prompt
        self._system = system
        self._model = model

    @Slot()
    def run(self) -> None:
        try:
            import ollama
            stream = ollama.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system},
                    {"role": "user",   "content": self._prompt},
                ],
                stream=True,
            )
            for chunk in stream:
                text = chunk["message"]["content"]
                if text:
                    self.chunk_received.emit(text)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class AIPanel(QWidget):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._model = "llama3"
        self._thread: QThread | None = None
        self._worker: _AIWorker | None = None
        self._history: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>🤖 AI Asystent ElectroVision</b>"))
        header.addStretch()
        header.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems([
            "llama3", "llama3:8b", "llama3:70b",
            "mistral", "mistral:7b", "mistral:instruct",
            "codellama", "codellama:7b", "codellama:13b",
            "llama2", "phi3", "gemma2", "deepseek-coder",
        ])
        self._model_combo.currentTextChanged.connect(lambda t: setattr(self, "_model", t))
        header.addWidget(self._model_combo)

        btn_models = QPushButton("Sprawdź dostępne")
        btn_models.clicked.connect(self._check_models)
        header.addWidget(btn_models)
        layout.addLayout(header)

        # Splitter: mode buttons + chat
        splitter = QSplitter(Qt.Horizontal)

        # Left: quick actions
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left.setMaximumWidth(240)

        left_layout.addWidget(QLabel("<b>Szybkie akcje</b>"))

        actions = [
            ("🔌  Zaproponuj schemat PCB",  "propose_pcb"),
            ("📦  Zaprojektuj obudowę STL",  "design_stl"),
            ("💻  Generuj kod Arduino",      "gen_arduino"),
            ("🔍  Analizuj BOM",             "analyze_bom"),
            ("⚡  Optymalizuj trasowanie",   "optimize_routing"),
            ("🔋  Dobierz zasilanie",        "power_design"),
            ("📡  Schemat antenowy RF",      "antenna"),
            ("🌡  Analiza termiczna",        "thermal"),
            ("✅  Sprawdź DRC",             "run_drc"),
            ("📖  Wyjaśnij komponent",       "explain_component"),
        ]
        self._action_list = QListWidget()
        for label, key in actions:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self._action_list.addItem(item)
        self._action_list.itemDoubleClicked.connect(self._on_quick_action)
        left_layout.addWidget(self._action_list)

        left_layout.addWidget(QLabel("<b>Kontekst projektu</b>"))
        self._ctx_label = QLabel("Brak projektu")
        self._ctx_label.setWordWrap(True)
        self._ctx_label.setStyleSheet("color: #aaa; font-size: 10px;")
        left_layout.addWidget(self._ctx_label)

        btn_kb = QPushButton("🔄 Aktualizuj bazę wiedzy")
        btn_kb.clicked.connect(self.start_knowledge_update)
        left_layout.addWidget(btn_kb)
        left_layout.addStretch()
        splitter.addWidget(left)

        # Right: chat area
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Consolas", 10))
        self._chat_display.setStyleSheet("background:#1a1a1a; color:#ddd; border:1px solid #333;")
        right_layout.addWidget(self._chat_display, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        right_layout.addWidget(self._progress)

        input_row = QHBoxLayout()
        self._input = QTextEdit()
        self._input.setMaximumHeight(80)
        self._input.setPlaceholderText(
            "Opisz co chcesz zaprojektować... np. 'Stwórz PCB dla ESP32 z wyświetlaczem OLED i czujnikiem BME280'\n"
            "Ctrl+Enter = wyślij"
        )
        input_row.addWidget(self._input)

        btn_col = QVBoxLayout()
        btn_send = QPushButton("Wyślij\n(Ctrl+↵)")
        btn_send.setMinimumHeight(40)
        btn_send.clicked.connect(self._send)
        btn_col.addWidget(btn_send)

        btn_clear = QPushButton("Wyczyść")
        btn_clear.clicked.connect(self._clear_chat)
        btn_col.addWidget(btn_clear)
        input_row.addLayout(btn_col)
        right_layout.addLayout(input_row)
        splitter.addWidget(right)

        splitter.setSizes([240, 800])
        layout.addWidget(splitter)

        self._chat_display.append(
            "<span style='color:#5af;'><b>ElectroVision AI</b></span> — Ollama lokalny asystent projektowania elektroniki<br>"
            "<span style='color:#888;'>Wymaga Ollama: https://ollama.ai — uruchom lokalnie, nie wysyła danych do chmury.</span><br>"
        )

    def keyPressEvent(self, event) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Return:
            self._send()
        else:
            super().keyPressEvent(event)

    def _build_context(self) -> str:
        if not self._project.board:
            return "Brak załadowanego projektu PCB."
        board = self._project.board
        comp_summary = ", ".join(
            f"{c.reference}({c.value})" for c in board.components[:20]
        )
        if len(board.components) > 20:
            comp_summary += f"... (+{len(board.components)-20} więcej)"
        return (
            f"Projekt: {self._project.name}\n"
            f"Wymiary PCB: {board.width_mm:.1f} x {board.height_mm:.1f} mm\n"
            f"Komponenty ({len(board.components)}): {comp_summary}\n"
            f"Sieci: {len(board.nets)}, Ścieżki: {len(board.traces)}, Przelotki: {len(board.vias)}"
        )

    def _system_prompt(self) -> str:
        from src.ai.prompts.loader import load_prompt
        base = load_prompt("pcb_system")
        context = self._build_context()
        return f"{base}\n\n## Aktualny projekt:\n{context}"

    def _send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._thread and self._thread.isRunning():
            return
        self._input.clear()
        self._append_user(text)
        self._start_ai(text)

    def _start_ai(self, prompt: str) -> None:
        self._progress.setVisible(True)
        self._worker = _AIWorker(prompt, self._system_prompt(), self._model)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk_received.connect(self._append_chunk)
        self._worker.finished.connect(self._on_ai_done)
        self._worker.error.connect(self._on_ai_error)
        self._chat_display.append("<span style='color:#5af;'><b>AI:</b></span> ")
        self._thread.start()

    def _append_user(self, text: str) -> None:
        self._chat_display.append(f"<span style='color:#fa0;'><b>Ty:</b></span> {text}<br>")

    @Slot(str)
    def _append_chunk(self, chunk: str) -> None:
        cursor = self._chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._chat_display.setTextCursor(cursor)
        self._chat_display.insertPlainText(chunk)
        self._chat_display.ensureCursorVisible()

    @Slot()
    def _on_ai_done(self) -> None:
        self._progress.setVisible(False)
        self._chat_display.append("<br>")
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    @Slot(str)
    def _on_ai_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._chat_display.append(
            f"<span style='color:#f55;'><b>Błąd:</b> {msg}</span><br>"
            "<span style='color:#888;'>Upewnij się że Ollama jest uruchomiona: <code>ollama serve</code></span><br>"
        )
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    def _on_quick_action(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.UserRole)
        prompts = {
            "propose_pcb": "Na podstawie projektu, zaproponuj optymalny schemat PCB z rozmieszczeniem komponentów, trasowaniem i zabezpieczeniami. Uwzględnij impedancję, EMI i termikę.",
            "design_stl": "Zaprojektuj obudowę 3D dla tej płytki PCB. Podaj wymiary, grubości ścianek, miejsca na złącza, otwory montażowe i wskazówki do druku 3D.",
            "gen_arduino": "Wygeneruj kompletny szkic Arduino dla wszystkich komponentów na tej płytce. Dołącz biblioteki, definicje pinów, setup() i loop() z obsługą wszystkich peryferiów.",
            "analyze_bom": "Przeanalizuj BOM tego projektu. Wskaż potencjalne problemy z dostępnością, zaproponuj zamienniki i oszacuj koszt.",
            "optimize_routing": "Zaproponuj optymalną strategię trasowania ścieżek dla tej płytki. Uwzględnij prądy, impedancję, crossowanie i minimalne odległości.",
            "power_design": "Zaproponuj układ zasilania dla tej płytki. Dobierz filtry, kondensatory blokujące, regulator i zabezpieczenia.",
            "antenna": "Zaprojektuj układ antenowy RF dla tego projektu. Podaj wymiary, impedancję i rozmieszczenie.",
            "thermal": "Przeanalizuj termikę tej płytki. Wskaż elementy wymagające chłodzenia i zaproponuj rozwiązania.",
            "run_drc": "Przeprowadź symulację DRC (Design Rule Check) dla tej płytki. Wskaż potencjalne problemy.",
            "explain_component": "Wyjaśnij funkcję i sposób podłączenia każdego komponentu na tej płytce.",
        }
        prompt = prompts.get(key, "")
        if prompt:
            self._input.setPlainText(prompt)
            self._send()

    def _clear_chat(self) -> None:
        self._chat_display.clear()

    def _check_models(self) -> None:
        try:
            import ollama
            models = ollama.list()
            names = [m["name"] for m in models.get("models", [])]
            if names:
                QMessageBox.information(self, "Modele Ollama", "Dostępne modele:\n" + "\n".join(names))
            else:
                QMessageBox.warning(self, "Ollama", "Brak pobranych modeli.\nUżyj: ollama pull llama3")
        except Exception as e:
            QMessageBox.critical(self, "Ollama", f"Nie można połączyć z Ollama:\n{e}\n\nUruchom: ollama serve")

    def start_knowledge_update(self) -> None:
        self._chat_display.append(
            "<span style='color:#5af;'><b>System:</b></span> Aktualizowanie bazy wiedzy PCB/STL…<br>"
        )
        try:
            from src.ai.knowledge.fetcher import KnowledgeFetcher
            fetcher = KnowledgeFetcher()
            report = fetcher.fetch_all()
            self._chat_display.append(
                f"<span style='color:#4f4;'><b>✓ Baza wiedzy zaktualizowana:</b></span> {report}<br>"
            )
        except Exception as e:
            self._chat_display.append(
                f"<span style='color:#f55;'>Błąd aktualizacji bazy wiedzy: {e}</span><br>"
            )

    def show_model_selector(self) -> None:
        self._model_combo.showPopup()

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        if project.board:
            self._ctx_label.setText(
                f"Projekt: {project.name}\n"
                f"PCB: {project.board.width_mm:.0f}×{project.board.height_mm:.0f}mm\n"
                f"Komp.: {len(project.board.components)}"
            )
        else:
            self._ctx_label.setText("Brak projektu")
