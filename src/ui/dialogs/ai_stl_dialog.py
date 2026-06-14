"""AI STL/STEP Design Dialog — describe enclosure in natural language → CadQuery/trimesh code → STL."""
from __future__ import annotations
import re
import json
import tempfile
import traceback
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QSplitter, QWidget, QGroupBox, QFormLayout,
    QComboBox, QCheckBox, QDoubleSpinBox, QProgressBar,
    QFileDialog, QMessageBox, QScrollArea, QLineEdit, QTabWidget,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, Slot
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter

from src.core.project import Project


# ── Quick-fill templates ──────────────────────────────────────────────────────

_EXAMPLES = [
    ("Obudowa drukowana 3D",
     "Zaprojektuj standardową obudowę do druku 3D dla tej płytki PCB. "
     "Obudowa powinna mieć zaokrąglone narożniki (promień 3mm), grubość ścianki 2mm, "
     "wieko z zatrzaskami snap-fit, standoffy M3 w narożnikach, "
     "i wycięcia na złącza USB oraz DC jack."),

    ("Obudowa wodoszczelna IP54",
     "Zaprojektuj obudowę o stopniu ochrony IP54 dla tej płytki. "
     "Grubość ścianki 3mm, rowek na uszczelkę O-ring 1.5mm przy wieku, "
     "śruby M3 mocujące wieko w 4 narożnikach, kablowe dławnice PG7 "
     "dla przewodów. Obudowa powinna być montowana na ścianie (uszy montażowe)."),

    ("Panel sterowania DIN",
     "Zaprojektuj obudowę do szyny DIN (35mm) dla tej płytki. "
     "Klips DIN w podstawie, wymiary pasujące do standardu DIN 43880, "
     "otwory wentylacyjne w pokrywie, okienko z przeźroczystego plastiku "
     "na wyświetlacz, zacisk kablowy z boku."),

    ("Obudowa zewnętrzna IP65",
     "Zaprojektuj szczelną obudowę do zastosowań zewnętrznych IP65. "
     "Polietylenowe materiały (PETG/ASA do druku), grubość ścianki 3.5mm, "
     "liczne żebra usztywniające na zewnątrz, uszczelka kompresyjna, "
     "4 śruby M4 nierdzewne, wsporniki montażowe do ściany/słupa, "
     "UV-odporna powierzchnia."),

    ("Minimalistyczna obudowa SMD",
     "Zaprojektuj minimalną, płaską obudowę dla małej płytki SMD. "
     "Wysokość całkowita max 15mm, wciskana podstawa bez śrub, "
     "gumowe nóżki antypoślizgowe, otwory na diody LED i przyciski w górnej pokrywie, "
     "kabel USB wychodzi przez bok."),

    ("Obudowa rack 1U",
     "Zaprojektuj panel rack 19 cali 1U (44.45mm wysokość) dla tej płytki. "
     "Standardowe otwory montażowe rack (szerokość 482.6mm), "
     "panel przedni z opisami otworów złączy, "
     "otwory wentylacyjne z boku, uchwyt/ucho do wyciągania z szafy."),
]

_TRIMESH_SYSTEM = """Jestes ekspertem od projektowania obudow 3D. Generujesz kod Python z biblioteka trimesh.
Zawsze pisz KOMPLETNY, GOTOWY DO WYKONANIA kod. Reguly:
1. Import: import trimesh, import numpy as np
2. Zmienne PCB_W, PCB_L, PCB_H na poczatku
3. Wszystkie wymiary jako zmienne (WALL, MARGIN, HEIGHT itp.)
4. Obudowa = zewnetrzna bryla minus wnetrze (boolean difference)
5. Standoffy jako walce (trimesh.creation.cylinder)
6. Na koncu: mesh.export(OUTPUT_PATH)  # nie zmieniaj tej linii!
7. Nie uzywaj cadquery - tylko trimesh i numpy
8. Druk wynikow: print(f"Wymiary: {w:.1f} x {l:.1f} x {h:.1f} mm")
"""

_CADQUERY_SYSTEM = """Jestes ekspertem od projektowania obudow 3D. Generujesz kod Python z biblioteka cadquery.
Zawsze pisz KOMPLETNY, GOTOWY DO WYKONANIA kod. Reguly:
1. Import: import cadquery as cq; from cadquery import exporters
2. Zmienne PCB_W, PCB_L, PCB_H na poczatku
3. Wszystkie wymiary jako zmienne
4. Uzywaj .fillet() dla zaokraglen
5. Na koncu: exporters.export(result, OUTPUT_PATH)  # nie zmieniaj tej linii!
6. Druk wynikow: print(f"Wymiary: ...")
"""


# ── Python syntax highlighter ─────────────────────────────────────────────────

class _PySyntaxHL(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569cd6"))
        kw_fmt.setFontWeight(QFont.Bold)
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#ce9178"))
        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#6a9955"))
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#b5cea8"))
        fn_fmt  = QTextCharFormat()
        fn_fmt.setForeground(QColor("#dcdcaa"))

        kw = r"\b(import|from|as|def|class|return|if|else|elif|for|while|try|except|with|in|not|and|or|True|False|None|lambda|yield|pass|break|continue|raise|global)\b"
        self._rules = [
            (re.compile(kw),                kw_fmt),
            (re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'), str_fmt),
            (re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'"), str_fmt),
            (re.compile(r"#[^\n]*"),         cmt_fmt),
            (re.compile(r"\b\d+\.?\d*\b"),   num_fmt),
            (re.compile(r"\b\w+(?=\s*\()"),  fn_fmt),
        ]

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── Background worker ─────────────────────────────────────────────────────────

class _AiWorker(QObject):
    chunk    = Signal(str)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, prompt: str, system: str, model: str):
        super().__init__()
        self._prompt = prompt
        self._system = system
        self._model  = model

    @Slot()
    def run(self) -> None:
        full = ""
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
            for part in stream:
                text = part["message"]["content"]
                if text:
                    full += text
                    self.chunk.emit(text)
            self.finished.emit(full)
        except Exception as e:
            from src.ai.ollama_utils import friendly_error
            self.error.emit(friendly_error(e))


class _ExecWorker(QObject):
    finished = Signal(dict)

    def __init__(self, code: str, output_path: str):
        super().__init__()
        self._code = code
        self._path = output_path

    @Slot()
    def run(self) -> None:
        import io, sys
        buf = io.StringIO()
        try:
            code = self._code.replace("OUTPUT_PATH", repr(self._path))
            old_stdout = sys.stdout
            sys.stdout = buf
            exec(compile(code, "<ai_stl>", "exec"), {})
            sys.stdout = old_stdout
            self.finished.emit({
                "success": True,
                "path":    self._path,
                "stdout":  buf.getvalue(),
                "error":   "",
            })
        except Exception:
            sys.stdout = buf
            self.finished.emit({
                "success": False,
                "path":    "",
                "stdout":  buf.getvalue(),
                "error":   traceback.format_exc(),
            })


# ── Main dialog ───────────────────────────────────────────────────────────────

class AISTLDialog(QDialog):
    stl_ready = Signal(str)   # emits path to generated STL

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI — Projektowanie obudowy 3D")
        self.setMinimumSize(1100, 720)
        self.setModal(True)

        self._project   = project
        self._ai_thread: QThread | None = None
        self._ai_worker: _AiWorker | None = None
        self._ex_thread: QThread | None = None
        self._ex_worker: _ExecWorker | None = None
        self._generated_code = ""
        self._last_stl  = ""

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: input ───────────────────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(360)
        left.setMaximumWidth(440)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)

        lbl_title = QLabel("Opisz obudowe 3D (jezyk naturalny)")
        lbl_title.setStyleSheet("font-weight:bold; color:#4a90d9; font-size:11px;")
        ll.addWidget(lbl_title)

        self._desc = QTextEdit()
        self._desc.setPlaceholderText(
            "Opisz obudowe ktorej potrzebujesz, np.:\n\n"
            "'Obudowa do druku 3D dla ESP32 z ekranem OLED.\n"
            " Grubosc scianki 2mm, zaokraglone narozniki 3mm,\n"
            " wieko z zatrzaskami, wycięcie na USB-C z przodu,\n"
            " otwory montazowe M3 w naroznikach.'"
        )
        self._desc.setMinimumHeight(140)
        self._desc.setFont(QFont("Segoe UI", 9))
        ll.addWidget(self._desc)

        # PCB info
        board = self._project.board if self._project else None
        if board:
            info = QLabel(
                f"PCB: {board.width_mm:.1f} x {board.height_mm:.1f} mm  |  "
                f"{len(board.components)} komp.  |  {len(board.nets)} sieci"
            )
            info.setStyleSheet("color:#4caf50; font-size:9px; font-family:Consolas;")
            ll.addWidget(info)

        # Examples
        lbl_ex = QLabel("Szybki start — kliknij szablon:")
        lbl_ex.setStyleSheet("color:#888; font-size:9px; margin-top:6px;")
        ll.addWidget(lbl_ex)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(170)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        ex_w = QWidget()
        ex_l = QVBoxLayout(ex_w)
        ex_l.setContentsMargins(0, 0, 0, 0)
        ex_l.setSpacing(3)
        for name, text in _EXAMPLES:
            btn = QPushButton(name)
            btn.setStyleSheet(
                "QPushButton{background:#161b22;color:#aaa;border:1px solid #2a2a3a;"
                "font-size:9px;padding:3px 6px;text-align:left;}"
                "QPushButton:hover{background:#1e2635;color:#ddd;}"
            )
            btn.clicked.connect(lambda _, t=text: self._desc.setPlainText(t))
            ex_l.addWidget(btn)
        ex_w.setLayout(ex_l)
        scroll.setWidget(ex_w)
        ll.addWidget(scroll)

        # Options
        opt_box = QGroupBox("Parametry generowania")
        opt_form = QFormLayout(opt_box)
        opt_form.setSpacing(6)

        self._lib_combo = QComboBox()
        self._lib_combo.addItems(["trimesh (Python 3.13+)", "cadquery (Python <=3.12)"])
        opt_form.addRow("Biblioteka:", self._lib_combo)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(["llama3", "codellama", "mistral", "qwen2.5-coder"])
        try:
            from src.ai.bridge import AIBridge
            self._model_combo.setCurrentText(AIBridge.instance().get_model())
        except Exception:
            pass
        opt_form.addRow("Model AI:", self._model_combo)

        self._wall_sp = QDoubleSpinBox()
        self._wall_sp.setRange(0.8, 8.0); self._wall_sp.setValue(2.0)
        self._wall_sp.setSuffix(" mm")
        opt_form.addRow("Grubosc scianki:", self._wall_sp)

        self._margin_sp = QDoubleSpinBox()
        self._margin_sp.setRange(1.0, 20.0); self._margin_sp.setValue(3.0)
        self._margin_sp.setSuffix(" mm")
        opt_form.addRow("Margines PCB:", self._margin_sp)

        self._chk_lid = QCheckBox("Generuj wieko")
        self._chk_lid.setChecked(True)
        opt_form.addRow(self._chk_lid)

        self._chk_standoffs = QCheckBox("Standoffy M3")
        self._chk_standoffs.setChecked(True)
        opt_form.addRow(self._chk_standoffs)

        ll.addWidget(opt_box)

        # Generate button
        self._btn_gen = QPushButton("Generuj kod obudowy z AI")
        self._btn_gen.setStyleSheet(
            "QPushButton{background:#1a4a1a;color:#5f5;font-weight:bold;"
            "font-size:11px;padding:8px;border:none;}"
            "QPushButton:hover{background:#1e5a1e;}"
            "QPushButton:disabled{background:#111;color:#555;}"
        )
        self._btn_gen.clicked.connect(self._generate_code)
        ll.addWidget(self._btn_gen)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(4)
        ll.addWidget(self._progress)

        ll.addStretch()
        splitter.addWidget(left)

        # ── Right: code + viewer + log ────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)

        tabs = QTabWidget()

        # Tab 1: generated code
        code_tab = QWidget()
        ct_l = QVBoxLayout(code_tab)

        code_hdr = QHBoxLayout()
        code_hdr.addWidget(QLabel("Wygenerowany kod Python:"))
        code_hdr.addStretch()
        self._btn_copy = QPushButton("Kopiuj")
        self._btn_copy.setFixedWidth(70)
        self._btn_copy.clicked.connect(self._copy_code)
        code_hdr.addWidget(self._btn_copy)
        self._btn_clear_code = QPushButton("Wyczysc")
        self._btn_clear_code.setFixedWidth(70)
        self._btn_clear_code.clicked.connect(lambda: self._code_edit.clear())
        code_hdr.addWidget(self._btn_clear_code)
        ct_l.addLayout(code_hdr)

        self._code_edit = QTextEdit()
        self._code_edit.setFont(QFont("Consolas", 9))
        self._code_edit.setStyleSheet(
            "QTextEdit{background:#0d1117;color:#d4d4d4;"
            "border:1px solid #2a2a3a; selection-background-color:#264f78;}"
        )
        self._code_edit.setPlaceholderText(
            "# Tutaj pojawi sie wygenerowany kod Python\n"
            "# Opis -> AI -> kod -> STL/STEP\n"
        )
        _PySyntaxHL(self._code_edit.document())
        ct_l.addWidget(self._code_edit, 1)
        tabs.addTab(code_tab, "Kod AI")

        # Tab 2: 3D preview
        viewer_tab = QWidget()
        vt_l = QVBoxLayout(viewer_tab)
        from src.ui.widgets.stl_3d_view import STL3DView
        self._viewer = STL3DView()
        vt_l.addWidget(self._viewer)
        tabs.addTab(viewer_tab, "Podglad 3D")

        # Tab 3: log
        log_tab = QWidget()
        lt_l = QVBoxLayout(log_tab)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 8))
        self._log.setStyleSheet("QTextEdit{background:#0a0e14;color:#888;}")
        lt_l.addWidget(self._log)
        tabs.addTab(log_tab, "Log")

        rl.addWidget(tabs, 1)

        # Action buttons
        btn_row = QHBoxLayout()

        self._btn_exec = QPushButton("Wykonaj kod -> STL")
        self._btn_exec.setEnabled(False)
        self._btn_exec.setStyleSheet(
            "QPushButton{background:#1a3a6a;color:#88aaff;font-weight:bold;padding:7px 14px;}"
            "QPushButton:hover{background:#1e4a8a;}"
            "QPushButton:disabled{background:#111;color:#444;}"
        )
        self._btn_exec.clicked.connect(self._execute_code)
        btn_row.addWidget(self._btn_exec)

        self._btn_gen_exec = QPushButton("AI -> Kod + STL (auto)")
        self._btn_gen_exec.setStyleSheet(
            "QPushButton{background:#1a4a1a;color:#5f5;font-weight:bold;padding:7px 14px;}"
            "QPushButton:hover{background:#1e5a1e;}"
        )
        self._btn_gen_exec.clicked.connect(self._generate_and_execute)
        btn_row.addWidget(self._btn_gen_exec)

        btn_row.addStretch()

        self._btn_save_stl = QPushButton("Zapisz STL...")
        self._btn_save_stl.setEnabled(False)
        self._btn_save_stl.clicked.connect(self._save_stl)
        btn_row.addWidget(self._btn_save_stl)

        self._btn_use = QPushButton("Uzyj w projekcie")
        self._btn_use.setEnabled(False)
        self._btn_use.setStyleSheet("QPushButton{background:#2a2a00;color:#cc0;padding:7px 14px;}")
        self._btn_use.clicked.connect(self._use_in_project)
        btn_row.addWidget(self._btn_use)

        btn_row.addWidget(QPushButton("Zamknij"))
        btn_row.itemAt(btn_row.count() - 1).widget().clicked.connect(self.reject)

        rl.addLayout(btn_row)

        self._exec_progress = QProgressBar()
        self._exec_progress.setRange(0, 0)
        self._exec_progress.setVisible(False)
        self._exec_progress.setMaximumHeight(4)
        rl.addWidget(self._exec_progress)

        splitter.addWidget(right)
        splitter.setSizes([420, 680])
        root.addWidget(splitter)

    # ── AI generation ─────────────────────────────────────────────────────────

    def _build_prompt(self) -> str:
        desc   = self._desc.toPlainText().strip()
        board  = self._project.board if self._project else None
        wall   = self._wall_sp.value()
        margin = self._margin_sp.value()
        lid    = self._chk_lid.isChecked()
        stands = self._chk_standoffs.isChecked()
        use_cq = self._lib_combo.currentIndex() == 1

        board_info = ""
        if board:
            bb = board.bounding_box
            connectors = [c for c in board.components if c.component_type == "connector"]
            board_info = (
                f"PCB wymiary: {board.width_mm:.2f} x {board.height_mm:.2f} mm\n"
                f"Liczba komponentow: {len(board.components)}\n"
                f"Zlacza: {', '.join(c.reference+':'+c.value for c in connectors[:8]) or 'brak'}\n"
            )
            pcb_w = f"{board.width_mm:.2f}"
            pcb_l = f"{board.height_mm:.2f}"
        else:
            board_info = "Brak danych PCB — uzyj typowych wartosci.\n"
            pcb_w, pcb_l = "80.0", "60.0"

        if use_cq:
            lib_hint = (
                "Uzyj WYLACZNIE cadquery. Zmienne na poczatku:\n"
                f"PCB_W, PCB_L, PCB_H = {pcb_w}, {pcb_l}, 1.6\n"
                "Na koncu: exporters.export(result.val(), OUTPUT_PATH)\n"
            )
        else:
            lib_hint = (
                "Uzyj WYLACZNIE trimesh i numpy. Zmienne na poczatku:\n"
                f"PCB_W, PCB_L, PCB_H = {pcb_w}, {pcb_l}, 1.6\n"
                "Uzyj trimesh.creation.box() i trimesh.boolean dla cial. "
                "Jezeli boolean nie dziala uzywaj trimesh.util.concatenate.\n"
                "Na koncu: mesh.export(OUTPUT_PATH)\n"
            )

        opts = (
            f"Grubosc scianki: {wall} mm\n"
            f"Margines PCB: {margin} mm\n"
            f"Wieko: {'TAK' if lid else 'NIE'}\n"
            f"Standoffy M3: {'TAK — walce r=1.5mm, h=3mm, otworki r=0.75mm' if stands else 'NIE'}\n"
        )

        return (
            f"Zaprojektuj obudowe 3D dla nastepujacego opisu uzytkownika:\n\n"
            f"OPIS: {desc}\n\n"
            f"DANE PCB:\n{board_info}\n"
            f"PARAMETRY UZYTKOWNIKA:\n{opts}\n"
            f"WYMAGANIA KODU:\n{lib_hint}\n"
            f"WAZNE:\n"
            f"- Zwroc TYLKO gotowy, kompletny kod Python bez markdown\n"
            f"- Nie pisz zadnych wyjasniencz przed ani po kodzie\n"
            f"- Kod musi sie wykonac bez bledow\n"
            f"- Wymiary obudowy obliczaj na podstawie PCB_W/PCB_L\n"
            f"- OUTPUT_PATH to stala — nie zmieniaj jej nazwy\n"
        )

    def _get_system(self) -> str:
        return _CADQUERY_SYSTEM if self._lib_combo.currentIndex() == 1 else _TRIMESH_SYSTEM

    def _generate_code(self) -> None:
        desc = self._desc.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Brak opisu", "Opisz obudowe przed generowaniem.")
            return
        if self._ai_thread and self._ai_thread.isRunning():
            self._ai_thread.quit()

        from src.ai.ollama_utils import is_ollama_running
        if not is_ollama_running():
            from src.ui.dialogs.ollama_error_dialog import show_ollama_error
            show_ollama_error("Ollama nie jest uruchomiona.", self)
            return

        self._code_edit.clear()
        self._btn_gen.setEnabled(False)
        self._btn_exec.setEnabled(False)
        self._progress.setVisible(True)
        self._log.append("[AI] Generowanie kodu...")

        self._ai_worker = _AiWorker(
            self._build_prompt(),
            self._get_system(),
            self._model_combo.currentText().strip(),
        )
        self._ai_thread = QThread()
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.chunk.connect(self._on_ai_chunk)
        self._ai_worker.finished.connect(self._on_ai_done)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_thread.start()

    def _on_ai_chunk(self, text: str) -> None:
        self._code_edit.insertPlainText(text)
        sb = self._code_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_ai_done(self, full: str) -> None:
        self._progress.setVisible(False)
        self._btn_gen.setEnabled(True)
        if self._ai_thread:
            self._ai_thread.quit()
        raw = self._code_edit.toPlainText()
        cleaned = self._extract_code(raw)
        if cleaned != raw:
            self._code_edit.setPlainText(cleaned)
        self._generated_code = cleaned
        self._btn_exec.setEnabled(True)
        self._log.append(f"[AI] Wygenerowano {len(cleaned)} znakow kodu.")

    def _on_ai_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._btn_gen.setEnabled(True)
        if self._ai_thread:
            self._ai_thread.quit()
        self._log.append(f"[ERR] {msg}")
        QMessageBox.critical(self, "Blad AI", msg)

    def _extract_code(self, text: str) -> str:
        # Strip markdown code fences
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
        if blocks:
            return max(blocks, key=len).strip()
        # Remove trailing commas that break JSON (if any leaked)
        text = re.sub(r",\s*\n\s*}", "\n}", text)
        # If starts with "import" or comment it's probably raw code
        stripped = text.strip()
        if stripped.startswith("#") or stripped.startswith("import") or stripped.startswith("PCB"):
            return stripped
        return text.strip()

    # ── Code execution ────────────────────────────────────────────────────────

    def _execute_code(self) -> None:
        code = self._code_edit.toPlainText().strip()
        if not code:
            QMessageBox.warning(self, "Brak kodu", "Najpierw wygeneruj kod AI.")
            return

        # Output path
        tmp_path = str(Path(tempfile.gettempdir()) / "ev_ai_enclosure.stl")

        self._exec_progress.setVisible(True)
        self._btn_exec.setEnabled(False)
        self._log.append(f"[EXEC] Wykonywanie kodu ({len(code)} znakow)...")
        self._log.append(f"[EXEC] Output: {tmp_path}")

        self._ex_worker = _ExecWorker(code, tmp_path)
        self._ex_thread = QThread()
        self._ex_worker.moveToThread(self._ex_thread)
        self._ex_thread.started.connect(self._ex_worker.run)
        self._ex_worker.finished.connect(self._on_exec_done)
        self._ex_thread.start()

    @Slot(dict)
    def _on_exec_done(self, result: dict) -> None:
        self._exec_progress.setVisible(False)
        self._btn_exec.setEnabled(True)
        if self._ex_thread:
            self._ex_thread.quit()

        if result["stdout"]:
            self._log.append(result["stdout"])

        if result["success"] and result["path"] and Path(result["path"]).exists():
            self._last_stl = result["path"]
            self._log.append(f"[OK] STL wygenerowany: {result['path']}")
            self._viewer.load_stl(result["path"])
            # Switch to preview tab
            parent = self._viewer.parent()
            tabs = parent.parent()
            if hasattr(tabs, "setCurrentIndex"):
                tabs.setCurrentIndex(1)
            self._btn_save_stl.setEnabled(True)
            self._btn_use.setEnabled(True)
        else:
            self._log.append(f"[ERR] {result['error']}")
            err_short = result["error"].split("\n")[-2] if result["error"] else "nieznany blad"
            QMessageBox.critical(
                self, "Blad wykonania",
                f"Kod AI nie wykonal sie poprawnie:\n\n{err_short}\n\n"
                "Sprawdz log. Mozesz recznie poprawic kod w edytorze i sprobowac ponownie."
            )

    def _generate_and_execute(self) -> None:
        """Generate code + immediately execute it after AI finishes."""
        self._auto_execute = True
        self._generate_code()
        # _on_ai_done will call _execute_code when _auto_execute is True
        original_done = self._ai_worker.finished
        def _auto_exec(text):
            if getattr(self, "_auto_execute", False):
                self._auto_execute = False
                self._execute_code()
        if self._ai_worker:
            self._ai_worker.finished.connect(_auto_exec)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _copy_code(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._code_edit.toPlainText())
        self._btn_copy.setText("Skopiowano!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._btn_copy.setText("Kopiuj"))

    def _save_stl(self) -> None:
        if not self._last_stl or not Path(self._last_stl).exists():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz STL", "obudowa_ai.stl", "STL (*.stl)"
        )
        if path:
            import shutil
            shutil.copy2(self._last_stl, path)
            self._last_stl = path
            self._log.append(f"[OK] Zapisano: {path}")

    def _use_in_project(self) -> None:
        if self._last_stl:
            self.stl_ready.emit(self._last_stl)
            self.accept()
