"""Application settings dialog — Ollama, DRC rules, PCB defaults."""
from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTabWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox,
    QSpinBox, QLineEdit, QGroupBox, QCheckBox, QDialogButtonBox,
    QMessageBox, QSlider, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

_SETTINGS_PATH = Path.home() / ".electrovision_settings.json"

_DEFAULTS: dict = {
    # Ollama
    "ollama_model":       "llama3",
    "ollama_host":        "http://localhost:11434",
    "ollama_timeout":     60,
    # DRC
    "drc_min_trace":      0.10,
    "drc_min_clearance":  0.10,
    "drc_min_via_drill":  0.20,
    "drc_min_annular":    0.10,
    "drc_edge_clearance": 0.30,
    # PCB editor defaults
    "pcb_default_trace":  0.25,
    "pcb_default_grid":   1.27,
    "pcb_default_via_d":  0.8,
    "pcb_default_via_dr": 0.4,
    "pcb_show_ratsnest":  True,
    "pcb_show_grid":      True,
    # General
    "theme":              "dark",
    "lang":               "pl",
    "autosave_min":       5,
}


def load_settings() -> dict:
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **raw}
    except Exception:
        return dict(_DEFAULTS)


def save_settings(s: dict) -> None:
    _SETTINGS_PATH.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


class SettingsDialog(QDialog):
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ustawienia ElectroVision")
        self.setMinimumSize(520, 480)
        self.setModal(True)
        self._settings = load_settings()
        self._build_ui()
        self._load_into_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._tab_ollama(),  "AI / Ollama")
        tabs.addTab(self._tab_drc(),     "Reguly DRC")
        tabs.addTab(self._tab_editor(),  "Edytor PCB")
        tabs.addTab(self._tab_general(), "Ogolne")
        layout.addWidget(tabs)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._on_reset)
        layout.addWidget(btns)

    # ── Tab: AI / Ollama ──────────────────────────────────────────────────────

    def _tab_ollama(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp = QGroupBox("Serwer Ollama")
        f = QFormLayout(grp)

        self._w_model = QComboBox()
        self._w_model.setEditable(True)
        self._w_model.addItems([
            "llama3", "llama3:8b", "llama3:70b",
            "mistral", "mistral:7b",
            "codellama", "codellama:7b", "codellama:13b",
            "phi3", "phi3:mini",
            "gemma2", "gemma2:9b",
            "qwen2.5-coder", "qwen2.5-coder:7b",
        ])
        f.addRow("Model:", self._w_model)

        self._w_host = QLineEdit()
        self._w_host.setPlaceholderText("http://localhost:11434")
        f.addRow("Host:", self._w_host)

        self._w_timeout = QSpinBox()
        self._w_timeout.setRange(5, 300)
        self._w_timeout.setSuffix(" s")
        f.addRow("Timeout:", self._w_timeout)

        btn_test = QPushButton("Testuj polaczenie")
        btn_test.clicked.connect(self._test_ollama)
        f.addRow("", btn_test)

        self._ollama_status = QLabel("")
        self._ollama_status.setWordWrap(True)
        f.addRow("Status:", self._ollama_status)

        lay.addWidget(grp)

        info = QLabel(
            "Modele do pobrania: ollama pull llama3\n"
            "Lista modeli: ollama list\n"
            "Uruchomienie: ollama serve"
        )
        info.setStyleSheet("color:#666; font-size:9px; font-family:Consolas;")
        lay.addWidget(info)
        lay.addStretch()
        return w

    # ── Tab: DRC ──────────────────────────────────────────────────────────────

    def _tab_drc(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)

        def dspin(lo, hi, step=0.01, suffix=" mm") -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(3)
            s.setSingleStep(step)
            s.setSuffix(suffix)
            return s

        self._w_drc_trace   = dspin(0.01, 5.0)
        self._w_drc_clear   = dspin(0.01, 5.0)
        self._w_drc_via_d   = dspin(0.05, 5.0)
        self._w_drc_annular = dspin(0.01, 2.0)
        self._w_drc_edge    = dspin(0.01, 5.0)

        f.addRow("Min. szerokosc sciezki:", self._w_drc_trace)
        f.addRow("Min. przeswit (clearance):", self._w_drc_clear)
        f.addRow("Min. wiertlo przelotki:", self._w_drc_via_d)
        f.addRow("Min. pierscien anularny:", self._w_drc_annular)
        f.addRow("Min. odl. od krawedzi:", self._w_drc_edge)

        note = QLabel("Wartosci zgodne ze standardem IPC-2221 dla klasy B.")
        note.setStyleSheet("color:#666; font-size:9px;")
        f.addRow(note)
        return w

    # ── Tab: PCB Editor ───────────────────────────────────────────────────────

    def _tab_editor(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)

        def dspin(lo, hi, val, step=0.05, suffix=" mm") -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(lo, hi); s.setDecimals(3)
            s.setSingleStep(step); s.setSuffix(suffix)
            s.setValue(val)
            return s

        self._w_def_trace = dspin(0.05, 5.0, 0.25)
        self._w_def_grid  = QComboBox()
        self._w_def_grid.addItems(["0.10", "0.25", "0.50", "0.635", "1.00", "1.27", "2.00", "2.54"])
        self._w_def_grid.setCurrentText("1.27")

        self._w_def_via_d  = dspin(0.3, 8.0, 0.8)
        self._w_def_via_dr = dspin(0.1, 5.0, 0.4)
        self._w_show_rat   = QCheckBox("Pokazuj ratsnest domyslnie")
        self._w_show_grid  = QCheckBox("Pokazuj siatke")

        f.addRow("Domyslna szerokosc sciezki:", self._w_def_trace)
        f.addRow("Domyslna siatka:", self._w_def_grid)
        f.addRow("Srednica przelotki:", self._w_def_via_d)
        f.addRow("Wiertlo przelotki:", self._w_def_via_dr)
        f.addRow("", self._w_show_rat)
        f.addRow("", self._w_show_grid)
        return w

    # ── Tab: General ──────────────────────────────────────────────────────────

    def _tab_general(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        f.setSpacing(10)

        self._w_autosave = QSpinBox()
        self._w_autosave.setRange(0, 60)
        self._w_autosave.setSuffix(" min (0 = wyl.)")
        self._w_autosave.setSpecialValueText("Wylaczony")

        self._w_lang = QComboBox()
        self._w_lang.addItems(["pl — Polski", "en — English"])

        f.addRow("Autozapis co:", self._w_autosave)
        f.addRow("Jezyk:", self._w_lang)

        ver = QLabel("ElectroVision v0.2.0  |  Python + PySide6  |  AI: Ollama (lokalny)")
        ver.setStyleSheet("color:#555; font-size:9px;")
        ver.setAlignment(Qt.AlignRight)
        f.addRow(ver)
        return w

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load_into_ui(self) -> None:
        s = self._settings
        idx = self._w_model.findText(s["ollama_model"])
        self._w_model.setCurrentIndex(idx if idx >= 0 else 0)
        self._w_model.setCurrentText(s["ollama_model"])
        self._w_host.setText(s["ollama_host"])
        self._w_timeout.setValue(s["ollama_timeout"])

        self._w_drc_trace.setValue(s["drc_min_trace"])
        self._w_drc_clear.setValue(s["drc_min_clearance"])
        self._w_drc_via_d.setValue(s["drc_min_via_drill"])
        self._w_drc_annular.setValue(s["drc_min_annular"])
        self._w_drc_edge.setValue(s["drc_edge_clearance"])

        self._w_def_trace.setValue(s["pcb_default_trace"])
        self._w_def_grid.setCurrentText(str(s["pcb_default_grid"]))
        self._w_def_via_d.setValue(s["pcb_default_via_d"])
        self._w_def_via_dr.setValue(s["pcb_default_via_dr"])
        self._w_show_rat.setChecked(s["pcb_show_ratsnest"])
        self._w_show_grid.setChecked(s["pcb_show_grid"])

        self._w_autosave.setValue(s["autosave_min"])
        lang_idx = 0 if s.get("lang", "pl") == "pl" else 1
        self._w_lang.setCurrentIndex(lang_idx)

    def _collect_from_ui(self) -> dict:
        return {
            "ollama_model":       self._w_model.currentText().strip(),
            "ollama_host":        self._w_host.text().strip() or "http://localhost:11434",
            "ollama_timeout":     self._w_timeout.value(),
            "drc_min_trace":      self._w_drc_trace.value(),
            "drc_min_clearance":  self._w_drc_clear.value(),
            "drc_min_via_drill":  self._w_drc_via_d.value(),
            "drc_min_annular":    self._w_drc_annular.value(),
            "drc_edge_clearance": self._w_drc_edge.value(),
            "pcb_default_trace":  self._w_def_trace.value(),
            "pcb_default_grid":   float(self._w_def_grid.currentText()),
            "pcb_default_via_d":  self._w_def_via_d.value(),
            "pcb_default_via_dr": self._w_def_via_dr.value(),
            "pcb_show_ratsnest":  self._w_show_rat.isChecked(),
            "pcb_show_grid":      self._w_show_grid.isChecked(),
            "autosave_min":       self._w_autosave.value(),
            "lang":               "pl" if self._w_lang.currentIndex() == 0 else "en",
            "theme":              "dark",
        }

    def _on_ok(self) -> None:
        self._settings = self._collect_from_ui()
        save_settings(self._settings)
        # Apply Ollama model immediately
        try:
            from src.ai.bridge import AIBridge
            AIBridge.instance().set_model(self._settings["ollama_model"])
        except Exception:
            pass
        self.settings_changed.emit(self._settings)
        self.accept()

    def _on_reset(self) -> None:
        self._settings = dict(_DEFAULTS)
        self._load_into_ui()

    def _test_ollama(self) -> None:
        host = self._w_host.text().strip() or "http://localhost:11434"
        try:
            import urllib.request
            with urllib.request.urlopen(host, timeout=3) as r:
                body = r.read(200).decode("utf-8", errors="ignore")
            self._ollama_status.setText("Polaczono. Odpowiedz: " + body[:80])
            self._ollama_status.setStyleSheet("color: #4caf50;")
        except Exception as e:
            self._ollama_status.setText(f"Blad: {e}")
            self._ollama_status.setStyleSheet("color: #f44336;")
