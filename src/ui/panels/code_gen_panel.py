"""Code generator panel — Arduino/MicroPython/ESP-IDF + AI assistant."""
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QTextEdit, QFileDialog, QMessageBox,
    QGroupBox, QSplitter, QListWidget, QListWidgetItem, QCheckBox,
    QProgressBar, QTabWidget
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor

from src.core.project import Project
from src.generators.code_generator import CodeGenerator
from src.ai.bridge import AIBridge


class _SyntaxHighlighter(QSyntaxHighlighter):
    KEYWORDS_C = {
        "void", "int", "float", "double", "char", "bool", "long", "unsigned",
        "return", "if", "else", "for", "while", "do", "switch", "case", "break",
        "include", "define", "const", "static", "#include", "#define",
        "pinMode", "digitalWrite", "digitalRead", "analogWrite", "analogRead",
        "Serial", "setup", "loop", "HIGH", "LOW", "INPUT", "OUTPUT",
        "void", "uint8_t", "uint16_t", "uint32_t", "int8_t", "int16_t",
    }
    KEYWORDS_PY = {
        "def", "class", "import", "from", "return", "if", "else", "elif",
        "for", "while", "in", "not", "and", "or", "True", "False", "None",
        "print", "self", "pass", "lambda", "with", "as", "try", "except",
        "finally", "raise", "yield", "async", "await",
    }

    def __init__(self, doc, lang: str = "arduino"):
        super().__init__(doc)
        self._lang = lang

    def highlightBlock(self, text: str) -> None:
        import re

        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor(86, 156, 214))
        keyword_fmt.setFontWeight(700)

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor(206, 145, 120))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor(106, 153, 85))
        comment_fmt.setFontItalic(True)

        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor(181, 206, 168))

        preprocessor_fmt = QTextCharFormat()
        preprocessor_fmt.setForeground(QColor(155, 155, 100))

        kws = self.KEYWORDS_PY if self._lang == "micropython" else self.KEYWORDS_C
        for kw in kws:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text):
                self.setFormat(m.start(), m.end() - m.start(), keyword_fmt)

        for m in re.finditer(r'"[^"\\]*(?:\\.[^"\\]*)*"', text):
            self.setFormat(m.start(), m.end() - m.start(), string_fmt)
        for m in re.finditer(r"'[^'\\]*(?:\\.[^'\\]*)*'", text):
            self.setFormat(m.start(), m.end() - m.start(), string_fmt)

        for m in re.finditer(r'\b\d+(\.\d+)?\b', text):
            self.setFormat(m.start(), m.end() - m.start(), number_fmt)

        if self._lang in ("arduino", "c_cpp"):
            if text.strip().startswith("#"):
                self.setFormat(0, len(text), preprocessor_fmt)
            comment_start = text.find("//")
        else:
            comment_start = text.find("#")

        if comment_start >= 0:
            self.setFormat(comment_start, len(text) - comment_start, comment_fmt)


class CodeGenPanel(QWidget):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._ai      = AIBridge.instance()
        self._highlighter: _SyntaxHighlighter | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Platforma:"))
        self._platform = QComboBox()
        self._platform.addItems([
            "Arduino (.ino)", "MicroPython (.py)",
            "ESP-IDF C++ (.cpp)", "PlatformIO (main.cpp)"
        ])
        self._platform.currentIndexChanged.connect(self._on_platform_changed)
        toolbar.addWidget(self._platform)

        toolbar.addWidget(QLabel("MCU:"))
        self._mcu = QComboBox()
        self._mcu.addItems([
            "Arduino Uno (ATmega328P)", "Arduino Nano (ATmega328P)",
            "Arduino Mega (ATmega2560)", "ESP32", "ESP32-S3", "ESP8266",
            "STM32F103 (Blue Pill)", "Raspberry Pi Pico (RP2040)",
            "ATtiny85", "Arduino Leonardo (ATmega32U4)",
        ])
        toolbar.addWidget(self._mcu)
        toolbar.addStretch()

        btn_gen = QPushButton("⚙ Generuj kod")
        btn_gen.setStyleSheet("font-weight: bold;")
        btn_gen.clicked.connect(self._generate)
        toolbar.addWidget(btn_gen)

        btn_save = QPushButton("💾 Zapisz plik…")
        btn_save.clicked.connect(self._save)
        toolbar.addWidget(btn_save)

        btn_open_ide = QPushButton("⚡ Otwórz w Arduino IDE")
        btn_open_ide.clicked.connect(self._open_in_arduino)
        toolbar.addWidget(btn_open_ide)

        layout.addLayout(toolbar)

        # ── Main splitter: components | tabs(code + AI) ───────────────────────
        main_splitter = QSplitter(Qt.Horizontal)

        # Component list
        comp_box = QGroupBox("Komponenty")
        comp_layout = QVBoxLayout(comp_box)
        self._comp_list = QListWidget()
        comp_layout.addWidget(self._comp_list)
        cb_all = QCheckBox("Zaznacz wszystkie")
        cb_all.setChecked(True)
        cb_all.toggled.connect(self._toggle_all)
        comp_layout.addWidget(cb_all)
        main_splitter.addWidget(comp_box)

        # Right: code + AI tabs
        right_tabs = QTabWidget()
        right_tabs.setDocumentMode(True)

        # Tab 1: Code editor
        code_widget = QWidget()
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(0, 4, 0, 0)
        self._code_edit = QTextEdit()
        self._code_edit.setFont(QFont("Consolas", 10))
        self._code_edit.setPlaceholderText(
            "Kliknij 'Generuj kod' aby wygenerować szkielet programu…\n\n"
            "Obsługiwane platformy:\n"
            "• Arduino — .ino szkielet z setup()/loop()\n"
            "• MicroPython — .py dla RP2040, ESP32\n"
            "• ESP-IDF C++ — FreeRTOS tasks, nvs, WiFi\n"
            "• PlatformIO — main.cpp z konfiguracją platformy"
        )
        code_layout.addWidget(self._code_edit)
        self._highlighter = _SyntaxHighlighter(self._code_edit.document(), "arduino")
        right_tabs.addTab(code_widget, "Kod")

        # Tab 2: AI assistant
        ai_widget = QWidget()
        ai_layout = QVBoxLayout(ai_widget)
        ai_layout.setContentsMargins(0, 4, 0, 0)

        ai_btns = QHBoxLayout()

        btn_improve = QPushButton("Ulepsz kod")
        btn_improve.setToolTip(
            "AI przejrzy kod, naprawi błędy, doda obsługę błędów i optymalizacje energetyczne"
        )
        btn_improve.clicked.connect(self._ai_improve)
        ai_btns.addWidget(btn_improve)

        btn_debug = QPushButton("Debug z AI")
        btn_debug.setToolTip("AI znajdzie potencjalne błędy i wyjaśni jak je naprawić")
        btn_debug.clicked.connect(self._ai_debug)
        ai_btns.addWidget(btn_debug)

        btn_extend = QPushButton("Rozbuduj dla MCU")
        btn_extend.setToolTip(
            "AI rozszerzy kod o funkcje specyficzne dla wybranego MCU: "
            "WiFi, BLE, deep sleep, watchdog, OTA"
        )
        btn_extend.clicked.connect(self._ai_extend)
        ai_btns.addWidget(btn_extend)

        btn_libs = QPushButton("Wyjaśnij biblioteki")
        btn_libs.setToolTip("AI wyjaśni każdą bibliotekę z #include — do czego służy i jak używać")
        btn_libs.clicked.connect(self._ai_explain_libs)
        ai_btns.addWidget(btn_libs)

        btn_paste = QPushButton("↑ Wklej do kodu")
        btn_paste.setToolTip("Zastąp kod w edytorze wynikiem AI")
        btn_paste.clicked.connect(self._ai_paste_to_editor)
        ai_btns.addWidget(btn_paste)

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
        self._ai_output.setFont(QFont("Consolas", 9))
        self._ai_output.setReadOnly(True)
        self._ai_output.setPlaceholderText(
            "Wyniki AI pojawią się tutaj…\n\n"
            "Możliwości:\n"
            "• 'Ulepsz kod' — refactoring, obsługa błędów, dokumentacja\n"
            "• 'Debug z AI' — analiza potencjalnych bugów i zagrożeń\n"
            "• 'Rozbuduj dla MCU' — WiFi, BLE, OTA, deep sleep, watchdog\n"
            "• 'Wyjaśnij biblioteki' — co robi każdy #include\n"
            "• 'Wklej do kodu' — zastąp edytor ulepszonym kodem od AI"
        )
        ai_layout.addWidget(self._ai_output, 1)
        right_tabs.addTab(ai_widget, "🤖 AI Asystent")

        main_splitter.addWidget(right_tabs)
        main_splitter.setSizes([220, 800])
        layout.addWidget(main_splitter)

    # ── Project / component ───────────────────────────────────────────────────

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._ai.set_project_context(project_name=project.name, board=project.board)
        self._refresh_components()

    def _refresh_components(self) -> None:
        self._comp_list.clear()
        if not self._project.board:
            return
        for comp in self._project.board.components:
            item = QListWidgetItem(f"{comp.reference} — {comp.value}")
            item.setData(Qt.UserRole, comp)
            item.setCheckState(Qt.Checked)
            self._comp_list.addItem(item)

    def _toggle_all(self, checked: bool) -> None:
        for i in range(self._comp_list.count()):
            self._comp_list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _on_platform_changed(self, idx: int) -> None:
        lang_map = {0: "arduino", 1: "micropython", 2: "c_cpp", 3: "c_cpp"}
        lang = lang_map.get(idx, "arduino")
        if self._highlighter:
            self._highlighter.deleteLater()
        self._highlighter = _SyntaxHighlighter(self._code_edit.document(), lang)

    def _selected_components(self):
        comps = []
        for i in range(self._comp_list.count()):
            item = self._comp_list.item(i)
            if item.checkState() == Qt.Checked:
                comp = item.data(Qt.UserRole)
                if comp:
                    comps.append(comp)
        return comps

    def _current_platform(self) -> str:
        return {0: "arduino", 1: "micropython", 2: "esp_idf", 3: "platformio"}.get(
            self._platform.currentIndex(), "arduino"
        )

    # ── Code generation ───────────────────────────────────────────────────────

    def _generate(self) -> None:
        if not self._project.board:
            QMessageBox.warning(self, "Kod", "Brak projektu PCB.")
            return
        comps = self._selected_components()
        if not comps:
            QMessageBox.warning(self, "Kod", "Nie wybrano żadnych komponentów.")
            return
        mcu = self._mcu.currentText()
        platform = self._current_platform()
        code = CodeGenerator.generate(comps, platform=platform, mcu=mcu, project_name=self._project.name)
        self._code_edit.setPlainText(code)

    def _save(self) -> None:
        code = self._code_edit.toPlainText()
        if not code:
            return
        ext_map = {0: ".ino", 1: ".py", 2: ".cpp", 3: ".cpp"}
        ext = ext_map.get(self._platform.currentIndex(), ".ino")
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz kod", f"{self._project.name}{ext}", f"Plik (*{ext})"
        )
        if path:
            Path(path).write_text(code, encoding="utf-8")
            QMessageBox.information(self, "Kod", f"Zapisano:\n{path}")

    def _open_in_arduino(self) -> None:
        code = self._code_edit.toPlainText()
        if not code:
            QMessageBox.warning(self, "Arduino IDE", "Brak kodu do otwarcia.")
            return
        sketch_name = self._project.name.replace(" ", "_") or "ElectroVision"
        tmp_dir = Path(tempfile.mkdtemp()) / sketch_name
        tmp_dir.mkdir(parents=True, exist_ok=True)
        sketch = tmp_dir / f"{sketch_name}.ino"
        sketch.write_text(code, encoding="utf-8")
        try:
            subprocess.Popen(["arduino", str(sketch)])
        except FileNotFoundError:
            QMessageBox.information(
                self, "Arduino IDE",
                f"Plik zapisany w:\n{sketch}\n\nOtwórz go ręcznie w Arduino IDE.\n\n"
                "Pobierz Arduino IDE: https://www.arduino.cc/en/software"
            )

    # ── AI ────────────────────────────────────────────────────────────────────

    def _start_ai(self) -> str | None:
        code = self._code_edit.toPlainText().strip()
        if not code:
            self._ai_output.setPlainText("Najpierw wygeneruj lub wpisz kod.")
            return None
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        return code

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_improve(self) -> None:
        code = self._start_ai()
        if not code:
            return
        self._ai.improve_code(
            code=code,
            platform=self._platform.currentText(),
            mcu=self._mcu.currentText(),
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_debug(self) -> None:
        code = self._start_ai()
        if not code:
            return
        platform = self._platform.currentText()
        mcu = self._mcu.currentText()
        self._ai.ask_async(
            f"Przeprowadź szczegółową analizę błędów w kodzie dla {platform} / {mcu}:\n\n"
            f"```\n{code[:4000]}\n```\n\n"
            "Znajdź i opisz:\n"
            "1. Potencjalne crashe i undefined behavior\n"
            "2. Wycieki pamięci i przepełnienia bufora\n"
            "3. Błędna inicjalizacja pinów lub peryferiów\n"
            "4. Brakująca obsługa błędów komunikacji (I2C, SPI, UART)\n"
            "5. Przepełnienia zmiennych (int vs long, signed vs unsigned)\n"
            "6. Błędne opóźnienia (delay() blokuje przerwania)\n"
            "7. Race conditions w przerwaniach (volatile, atomic)\n"
            "8. Problemy z zasilaniem (brakujące kondensatory, reset podczas startu)\n\n"
            "Dla każdego problemu: lokalizacja w kodzie + jak naprawić.",
            system_key="code_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_extend(self) -> None:
        code = self._start_ai()
        if not code:
            return
        mcu = self._mcu.currentText()
        platform = self._platform.currentText()

        mcu_features = {
            "ESP32": "WiFi (WiFiClient, MQTT), BLE (BLEServer), deep sleep (esp_deep_sleep_start), OTA (ArduinoOTA), watchdog (esp_task_wdt)",
            "ESP32-S3": "WiFi, USB HID/CDC, BLE 5.0, AI/ML (TensorFlow Lite), deep sleep, PSRAM",
            "ESP8266": "WiFi (WiFiClient, ESP8266WebServer), OTA, deep sleep (ESP.deepSleep), watchdog",
            "Raspberry Pi Pico (RP2040)": "multicore (core1, rp2.PIO), I2C/SPI/UART, timers, PWM, sleep",
            "STM32F103 (Blue Pill)": "HAL, USB CDC, CAN bus, DMA, RTC, SPI, I2C, watchdog IWDG",
        }.get(mcu, "watchdog, interrupcje, tryby niskiego poboru mocy")

        self._ai.ask_async(
            f"Rozbuduj poniższy kod dla {platform} / {mcu}:\n\n"
            f"```\n{code[:3000]}\n```\n\n"
            f"Dodaj funkcje specyficzne dla {mcu}:\n{mcu_features}\n\n"
            "Format: pełny rozbudowany kod gotowy do wgrania. "
            "Każda nowa funkcja opatrzona krótkim komentarzem.",
            system_key="code_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_explain_libs(self) -> None:
        code = self._start_ai()
        if not code:
            return
        import re
        if self._current_platform() == "micropython":
            includes = re.findall(r'^(?:import|from)\s+([\w.]+)', code, re.MULTILINE)
        else:
            includes = re.findall(r'#include\s*[<"]([^>"]+)[>"]', code)

        if not includes:
            self._ai_output.setPlainText("Brak bibliotek #include / import do wyjaśnienia.")
            return

        libs_text = "\n".join(f"• {lib}" for lib in includes)
        self._ai.ask_async(
            f"Wyjaśnij każdą z następujących bibliotek używanych w kodzie:\n\n{libs_text}\n\n"
            "Dla każdej biblioteki podaj:\n"
            "1. Do czego służy (1-2 zdania)\n"
            "2. Skąd ją zainstalować (Arduino Library Manager / pip / URL)\n"
            "3. Przykład użycia (1-3 linie kodu)\n"
            "4. Alternatywne biblioteki (jeśli istnieją)\n"
            "5. Link do dokumentacji (jeśli znasz)",
            system_key="code_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_paste_to_editor(self) -> None:
        ai_text = self._ai_output.toPlainText().strip()
        if not ai_text:
            return
        import re
        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', ai_text, re.DOTALL)
        if code_blocks:
            code = max(code_blocks, key=len)
        else:
            code = ai_text
        reply = QMessageBox.question(
            self, "Wklej kod AI",
            "Zastąpić aktualny kod w edytorze kodem z AI?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._code_edit.setPlainText(code)
