"""AI PCB Project Generator — describe your device, AI generates the full board.

Flow:
  1. User types a natural-language description (or picks an example)
  2. AI generates a JSON spec: name, dims, components list, nets
  3. Dialog parses the JSON, builds a PCBBoard with smart auto-placement
  4. Preview table shows components; user clicks "Utwórz projekt"
  5. New project is returned to the caller
"""
from __future__ import annotations
import json
import math
import re
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QScrollArea, QWidget,
    QGroupBox, QAbstractItemView, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot
from PySide6.QtGui import QFont, QColor

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer
from src.core.models.net import Net
from src.ai.bridge import AIBridge


# ── Przykładowe opisy projektów ───────────────────────────────────────────────
_EXAMPLES: list[tuple[str, str]] = [
    ("ESP32 IoT",
     "Sterownik IoT oparty na ESP32 z WiFi. Zasilanie 5V przez USB-C, "
     "regulator 3.3V, 4 przyciski użytkownika, 4 diody LED statusu, "
     "złącze I2C do czujnika temperatury/wilgotności BME280, "
     "slot microSD, UART do debugowania."),

    ("Sterownik silnika",
     "Dwukanałowy sterownik silników DC z mostkiem H (L298N lub DRV8833), "
     "sterowany przez Arduino Nano. Zasilanie 12V dla silników, 5V dla logiki, "
     "enkodery na przerwaniach, diody ochronne, kondensatory filtrujące, "
     "złącze do akumulatora XT60."),

    ("Zasilacz lab",
     "Regulowany zasilacz laboratoryjny 0-30V / 0-5A z wyświetlaczem OLED, "
     "tranzystor mocy MOSFET, wzmacniacz operacyjny LM358, "
     "przetwornik ADC do pomiaru napięcia/prądu, wentylatorem, "
     "zabezpieczeniem OCP, złączem bananowym 4mm."),

    ("Pasek LED RGB",
     "Kontroler paska LED RGB WS2812B oparty na RP2040. "
     "Zasilanie 5V 3A, kondensatory blokujące przy każdym IC, "
     "rezystor 330R na data line, złącze JST do paska LED, "
     "przycisk reset, dioda ochronna Schottky."),

    ("BLE sensor",
     "Węzeł sensoryczny BLE oparty na nRF52840. Bateria LiPo z ładowaniem "
     "przez USB-C (TP4056), MPU6050 akcelerometr/żyroskop I2C, "
     "czujnik ciśnienia BMP280, tryb deep-sleep, antenna PCB, "
     "watchdog, buzzer 5V."),

    ("STM32 data logger",
     "Data logger oparty na STM32F103C8T6 (Blue Pill). Slot microSD przez SPI, "
     "RTC DS3231 przez I2C z baterią CR2032, czujnik temperatury DS18B20, "
     "konwerter USB-UART CP2102, dioda statusu, przycisk start/stop, "
     "zasilanie 3.3V lub 5V USB."),
]

# ── Prompt systemowy dla generatora ──────────────────────────────────────────
_SYSTEM_PROMPT = """Jesteś ekspertem projektowania PCB. Na podstawie opisu użytkownika wygeneruj listę komponentów dla projektu płytki PCB.

Odpowiedz WYŁĄCZNIE poprawnym JSON (bez markdown, bez wyjaśnień):

{
  "project_name": "Krótka nazwa projektu",
  "board_description": "Jedno zdanie opisu",
  "board_width_mm": 80,
  "board_height_mm": 60,
  "components": [
    {
      "reference": "U1",
      "value": "ESP32-WROOM-32D",
      "footprint": "RF_Module:ESP32-WROOM-32",
      "description": "Główny mikrokontroler WiFi/BT",
      "layer": "F.Cu",
      "zone": "center"
    }
  ],
  "nets": ["VCC", "GND", "3V3", "5V"],
  "power_net": "3V3",
  "design_notes": "Krótkie uwagi projektowe"
}

Zasady:
- zone: "center" dla ICs/MCU, "left"/"right" dla złączy, "top" dla zasilania, "scatter" dla elementów biernych
- Używaj standardowych nazw footprintów KiCad (Resistor_SMD, Capacitor_SMD, Package_TO_SOT_SMD itp.)
- Elementy bierne (R, C, L) jako SMD 0402 lub 0603
- Dodaj kondensatory odsprzęgające 100nF przy każdym IC (VCC pin)
- Dodaj rezystory pull-up/pull-down gdzie wymagane
- Uwzględnij zabezpieczenia: diody TVS, bezpiecznik, varistor jeśli potrzebne
- Minimalna liczba komponentów: 8, maksymalna: 40
- board_width_mm i board_height_mm: realistyczne wymiary (20-200mm)
- power_net: główna sieć zasilania logiki ("3V3" lub "5V")
"""


# ── Wątek AI (oddzielony od main_window AIBridge, żeby nie kolidować) ─────────
class _GenWorker(QObject):
    chunk    = Signal(str)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, prompt: str, model: str):
        super().__init__()
        self._prompt = prompt
        self._model  = model

    @Slot()
    def run(self) -> None:
        full = ""
        try:
            import ollama
            messages = [
                {"role": "system",  "content": _SYSTEM_PROMPT},
                {"role": "user",    "content": self._prompt},
            ]
            stream = ollama.chat(model=self._model, messages=messages, stream=True)
            for part in stream:
                text = part["message"]["content"]
                if text:
                    full += text
                    self.chunk.emit(text)
            self.finished.emit(full)
        except ImportError:
            self.error.emit(
                "Brak biblioteki ollama.\n"
                "Zainstaluj: pip install ollama\n"
                "Następnie: ollama pull llama3"
            )
        except Exception as e:
            msg = str(e)
            if "connection" in msg.lower() or "refused" in msg.lower():
                msg = "Nie można połączyć z Ollama.\nUruchom: ollama serve"
            self.error.emit(msg)


# ── Generowanie padów na podstawie typu komponentu ────────────────────────────
def _make_pads(ref: str, value: str, fp: str,
               vcc_net: str = "VCC", gnd_net: str = "GND") -> list[Pad]:
    prefix = "".join(c for c in ref if c.isalpha()).upper()

    if prefix in ("R", "L", "FB"):
        return [
            Pad("1", "smd", "rect", -0.9, 0.0, 0.6, 0.9),
            Pad("2", "smd", "rect",  0.9, 0.0, 0.6, 0.9),
        ]
    if prefix in ("C",):
        return [
            Pad("+", "smd", "rect", -0.9, 0.0, 0.6, 0.9, net_name=vcc_net),
            Pad("-", "smd", "rect",  0.9, 0.0, 0.6, 0.9, net_name=gnd_net),
        ]
    if prefix in ("D",):
        return [
            Pad("K", "smd", "rect", -0.9, 0.0, 0.6, 0.9),
            Pad("A", "smd", "rect",  0.9, 0.0, 0.6, 0.9),
        ]
    if prefix in ("LED",):
        return [
            Pad("K", "smd", "rect", -0.75, 0.0, 0.5, 0.8, net_name=gnd_net),
            Pad("A", "smd", "rect",  0.75, 0.0, 0.5, 0.8),
        ]
    if prefix in ("Q",):
        return [
            Pad("G", "smd", "rect", 0.0, -1.0, 0.5, 0.6),
            Pad("D", "smd", "rect", 0.9, 0.0,  0.5, 0.6),
            Pad("S", "smd", "rect", -0.9, 0.0, 0.5, 0.6, net_name=gnd_net),
        ]
    if prefix in ("J", "P", "CN"):
        n = _parse_pin_count(value)
        pads = []
        for i in range(n):
            net = gnd_net if i == n-1 else (vcc_net if i == 0 else "")
            pads.append(
                Pad(str(i+1), "thru_hole", "circle",
                    0.0, i * 2.54, 1.6, 1.6, net_name=net, drill=0.8)
            )
        return pads
    if prefix in ("SW", "S", "BTN"):
        return [
            Pad("1", "thru_hole", "circle", -2.54, 0.0, 1.6, 1.6, drill=0.8),
            Pad("2", "thru_hole", "circle",  2.54, 0.0, 1.6, 1.6, drill=0.8),
        ]
    if prefix in ("Y", "X", "XT"):
        return [
            Pad("1", "smd", "rect", -2.0, 0.0, 1.2, 1.4),
            Pad("2", "smd", "rect",  2.0, 0.0, 1.2, 1.4),
        ]
    if prefix in ("F", "FU"):
        return [
            Pad("1", "smd", "rect", -2.0, 0.0, 1.0, 1.2),
            Pad("2", "smd", "rect",  2.0, 0.0, 1.0, 1.2),
        ]
    # IC / U (default: 8 SMD pads)
    n_pads = 8
    pads = []
    half = n_pads // 2
    for i in range(half):
        y = (i - (half - 1) / 2) * 1.27
        pads.append(Pad(str(i + 1),          "smd", "rect", -3.2, y, 0.5, 0.85,
                        net_name=gnd_net if i == half - 1 else ""))
        pads.append(Pad(str(n_pads - i),     "smd", "rect",  3.2, y, 0.5, 0.85,
                        net_name=vcc_net if i == 0 else ""))
    return pads


def _parse_pin_count(value: str) -> int:
    for w in re.findall(r"\d+", value):
        n = int(w)
        if 2 <= n <= 20:
            return n
    return 2


# ── Auto-placement ────────────────────────────────────────────────────────────
def _auto_place(components: list[Component],
                board_w: float, board_h: float) -> None:
    """Assign x/y to components using zone-based layout."""
    zones: dict[str, list[Component]] = {
        "center": [], "left": [], "right": [], "top": [], "scatter": []
    }
    for c in components:
        zone = getattr(c, "_zone", "scatter")
        zones.setdefault(zone, []).append(c)

    cx, cy = board_w / 2, board_h / 2
    margin = 8.0

    # Center: ICs in a grid
    center = zones.get("center", [])
    if center:
        cols = max(1, math.ceil(math.sqrt(len(center))))
        cw   = min((board_w - 40) / cols, 18.0)
        ch   = min((board_h - 30) / math.ceil(len(center) / cols), 15.0)
        for idx, c in enumerate(center):
            row, col = divmod(idx, cols)
            c.x = cx - (cols - 1) * cw / 2 + col * cw
            c.y = cy - (math.ceil(len(center) / cols) - 1) * ch / 2 + row * ch

    # Left: connectors in a column
    left = zones.get("left", [])
    for idx, c in enumerate(left):
        c.x = margin + 3.0
        c.y = margin + idx * 10.0 + 5.0

    # Right: connectors in a column
    right = zones.get("right", [])
    for idx, c in enumerate(right):
        c.x = board_w - margin - 3.0
        c.y = margin + idx * 10.0 + 5.0

    # Top: power components in a row
    top = zones.get("top", [])
    for idx, c in enumerate(top):
        c.x = margin + idx * 12.0 + 6.0
        c.y = margin + 4.0

    # Scatter: passives in a grid below center
    scatter = zones.get("scatter", [])
    if scatter:
        cols    = max(3, min(8, int(board_w / 8)))
        start_y = board_h * 0.65
        for idx, c in enumerate(scatter):
            row, col = divmod(idx, cols)
            c.x = margin + col * ((board_w - 2 * margin) / cols) + 3.0
            c.y = start_y + row * 6.0

    # Clamp all to board bounds
    for c in components:
        c.x = max(margin, min(board_w - margin, c.x))
        c.y = max(margin, min(board_h - margin, c.y))


# ── JSON parser (robust, strips markdown fences) ──────────────────────────────
def _extract_json(text: str) -> Optional[dict]:
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find JSON object
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        # Try to fix common AI errors: trailing commas
        fixed = re.sub(r",\s*([}\]])", r"\1", text[start:end])
        try:
            return json.loads(fixed)
        except Exception:
            return None


# ── Board builder ─────────────────────────────────────────────────────────────
def _build_board_from_spec(spec: dict) -> tuple[PCBBoard, str]:
    """Convert AI JSON spec → PCBBoard. Returns (board, project_name)."""
    w = float(spec.get("board_width_mm",  80))
    h = float(spec.get("board_height_mm", 60))
    name = spec.get("project_name", "AI Project")
    vcc  = spec.get("power_net", "3V3")
    gnd  = "GND"

    # Layers
    layers = [
        Layer("F.Cu",    0,  "signal"),
        Layer("B.Cu",   31,  "signal"),
        Layer("F.SilkS", 37, "user"),
        Layer("B.SilkS", 36, "user"),
        Layer("F.Mask",  39, "user"),
        Layer("B.Mask",  38, "user"),
        Layer("Edge.Cuts", 44, "user"),
    ]

    # Nets
    net_names: list[str] = [gnd, vcc]
    for n in spec.get("nets", []):
        if n not in net_names:
            net_names.append(n)
    nets = [Net(n, i) for i, n in enumerate(net_names)]

    # Components
    raw_comps = spec.get("components", [])
    components: list[Component] = []
    for raw in raw_comps:
        ref  = raw.get("reference", "?")
        val  = raw.get("value", "")
        fp   = raw.get("footprint", "")
        desc = raw.get("description", "")
        layer= raw.get("layer", "F.Cu")
        zone = raw.get("zone", "scatter")
        pads = _make_pads(ref, val, fp, vcc_net=vcc, gnd_net=gnd)
        c = Component(
            reference=ref, value=val, footprint=fp,
            x=0.0, y=0.0, rotation=0.0, layer=layer,
            description=desc, pads=pads,
        )
        c._zone = zone  # type: ignore[attr-defined]
        components.append(c)

    _auto_place(components, w, h)

    # Board outline (Edge.Cuts)
    graphic_lines = [
        GraphicLine(0, 0, w, 0, 0.05, "Edge.Cuts"),
        GraphicLine(w, 0, w, h, 0.05, "Edge.Cuts"),
        GraphicLine(w, h, 0, h, 0.05, "Edge.Cuts"),
        GraphicLine(0, h, 0, 0, 0.05, "Edge.Cuts"),
    ]

    # Mounting holes (4 corners, 3mm dia)
    mh_offset = 3.5
    for mx, my in [
        (mh_offset, mh_offset), (w - mh_offset, mh_offset),
        (mh_offset, h - mh_offset), (w - mh_offset, h - mh_offset)
    ]:
        mh = Component(
            reference=f"MH{len([c for c in components if c.reference.startswith('MH')])+1}",
            value="MountingHole_3mm",
            footprint="MountingHole:MountingHole_3.2mm_M3",
            x=mx, y=my, rotation=0.0, layer="F.Cu",
            description="Otwór montażowy M3",
            pads=[Pad("1", "thru_hole", "circle", 0, 0, 3.2, 3.2, drill=3.2)],
        )
        components.append(mh)

    board = PCBBoard(
        title=name,
        company="ElectroVision AI",
        revision="A",
        kicad_version="7.0",
        components=components,
        traces=[],
        vias=[],
        graphic_lines=graphic_lines,
        nets=nets,
        layers=layers,
    )
    return board, name


# ── Dialog ────────────────────────────────────────────────────────────────────
class AIProjectDialog(QDialog):
    """Full-screen dialog for AI-driven PCB project generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 Generuj projekt PCB z opisu AI")
        self.setMinimumSize(1100, 720)
        self.resize(1200, 800)
        self._result_project: Optional[Project] = None
        self._ai_bridge = AIBridge.instance()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_GenWorker] = None
        self._full_response = ""
        self._parsed_spec:   Optional[dict] = None
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        # Header
        hdr = QLabel(
            "🤖  <b>Generator projektu PCB z opisu AI</b>  — "
            "Opisz urządzenie, AI dobierze komponenty i rozplanuje płytkę"
        )
        hdr.setStyleSheet(
            "font-size: 13px; color: #4a90d9; "
            "background: #0d1a2a; padding: 8px 12px; border-radius: 4px;"
        )
        root.addWidget(hdr)

        splitter = QSplitter(Qt.Vertical)

        # ── Top: input area ───────────────────────────────────────────────────
        top_w = QWidget()
        top_l = QVBoxLayout(top_w)
        top_l.setContentsMargins(0, 4, 0, 0)

        top_l.addWidget(QLabel("Opisz swój projekt (co ma robić, jakie czujniki/złącza, napięcie zasilania):"))

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "Przykład: Sterownik silnika krokowego oparty na ESP32 z WiFi. "
            "Zasilanie 12V / 2A, driver TB6600, enkoder kwadratowy, "
            "złącze RJ45 do sterowania CNC, 3 krańcówki, buzzer, OLED 128x64..."
        )
        self._desc_edit.setFont(QFont("Consolas", 10))
        self._desc_edit.setMaximumHeight(90)
        top_l.addWidget(self._desc_edit)

        # Quick examples
        examples_row = QHBoxLayout()
        examples_row.addWidget(QLabel("Przykłady:"))
        for title, desc in _EXAMPLES:
            btn = QPushButton(title)
            btn.setMaximumHeight(24)
            btn.setStyleSheet(
                "QPushButton { background: #1a2a3a; color: #89b4fa; "
                "border: 1px solid #2a4a6a; padding: 2px 8px; border-radius: 3px; font-size: 9px; }"
                "QPushButton:hover { background: #1a3a5a; }"
            )
            btn.clicked.connect(lambda _, d=desc: self._desc_edit.setPlainText(d))
            examples_row.addWidget(btn)
        examples_row.addStretch()
        top_l.addLayout(examples_row)

        # Buttons row
        btn_row = QHBoxLayout()
        self._btn_gen = QPushButton("▶  Generuj projekt (AI)")
        self._btn_gen.setStyleSheet(
            "QPushButton { background: #1a4a8f; color: white; font-weight: bold; "
            "padding: 8px 20px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #2a5aaf; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._btn_gen.clicked.connect(self._start_generation)
        btn_row.addWidget(self._btn_gen)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_generation)
        btn_row.addWidget(self._btn_stop)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        btn_row.addWidget(self._progress, 1)

        self._model_label = QLabel()
        self._model_label.setStyleSheet("color: #888; font-size: 9px;")
        self._model_label.setText(f"Model: {self._ai_bridge.get_model()}")
        btn_row.addWidget(self._model_label)

        top_l.addLayout(btn_row)
        splitter.addWidget(top_w)

        # ── Bottom: response + preview ────────────────────────────────────────
        bottom_splitter = QSplitter(Qt.Horizontal)

        # Left: AI raw response
        left_w = QWidget()
        left_l = QVBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 4, 0)
        lbl_ai = QLabel("Odpowiedź AI (JSON):")
        lbl_ai.setStyleSheet("font-size: 9px; color: #888;")
        left_l.addWidget(lbl_ai)
        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 8))
        self._ai_out.setStyleSheet("background: #0a0f17; color: #78dcaa;")
        left_l.addWidget(self._ai_out)
        bottom_splitter.addWidget(left_w)

        # Right: parsed preview
        right_w = QWidget()
        right_l = QVBoxLayout(right_w)
        right_l.setContentsMargins(4, 0, 0, 0)

        info_row = QHBoxLayout()
        self._board_info = QLabel("—")
        self._board_info.setStyleSheet(
            "color: #89b4fa; font-weight: bold; "
            "background: #0d1a2a; padding: 4px 8px; border-radius: 3px;"
        )
        info_row.addWidget(self._board_info, 1)
        right_l.addLayout(info_row)

        self._comp_table = QTableWidget(0, 5)
        self._comp_table.setHorizontalHeaderLabels(
            ["Ref", "Wartość", "Footprint", "Opis", "Strefa"]
        )
        self._comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._comp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._comp_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._comp_table.setColumnWidth(0, 60)
        self._comp_table.setColumnWidth(4, 60)
        self._comp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._comp_table.setAlternatingRowColors(True)
        self._comp_table.setStyleSheet(
            "QTableWidget { background: #0d1117; gridline-color: #2a2a3a; }"
            "QTableWidget::item:alternate { background: #131820; }"
        )
        self._comp_table.setFont(QFont("Consolas", 8))
        right_l.addWidget(self._comp_table, 1)

        self._notes_label = QLabel()
        self._notes_label.setWordWrap(True)
        self._notes_label.setStyleSheet("color: #a0a0a0; font-size: 9px; padding: 4px;")
        right_l.addWidget(self._notes_label)
        bottom_splitter.addWidget(right_w)
        bottom_splitter.setSizes([500, 560])
        splitter.addWidget(bottom_splitter)

        splitter.setSizes([180, 540])
        root.addWidget(splitter, 1)

        # ── Footer buttons ────────────────────────────────────────────────────
        footer = QHBoxLayout()

        self._btn_create = QPushButton("✓  Utwórz projekt PCB")
        self._btn_create.setEnabled(False)
        self._btn_create.setStyleSheet(
            "QPushButton { background: #1a6a1a; color: white; font-weight: bold; "
            "padding: 8px 24px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #2a8a2a; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._btn_create.clicked.connect(self._create_project)
        footer.addWidget(self._btn_create)

        self._status_label = QLabel("Wpisz opis projektu i kliknij Generuj.")
        self._status_label.setStyleSheet("color: #888; font-size: 9px;")
        footer.addWidget(self._status_label, 1)

        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        root.addLayout(footer)

    # ── AI generation ─────────────────────────────────────────────────────────
    def _start_generation(self) -> None:
        desc = self._desc_edit.toPlainText().strip()
        if not desc:
            self._status_label.setText("⚠  Wpisz opis projektu.")
            return

        self._ai_out.clear()
        self._comp_table.setRowCount(0)
        self._board_info.setText("Generowanie…")
        self._notes_label.clear()
        self._parsed_spec = None
        self._full_response = ""
        self._btn_create.setEnabled(False)
        self._btn_gen.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress.setVisible(True)
        self._status_label.setText("AI generuje specyfikację projektu…")

        # Kill any previous thread
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        prompt = (
            f"Użytkownik chce stworzyć następujący projekt PCB:\n\n{desc}\n\n"
            "Wygeneruj pełną specyfikację JSON zgodnie z formatem systemowym."
        )
        model = self._ai_bridge.get_model()
        self._worker = _GenWorker(prompt, model)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_ai_chunk)
        self._worker.finished.connect(self._on_ai_done)
        self._worker.error.connect(self._on_ai_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _stop_generation(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self._progress.setVisible(False)
        self._btn_gen.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_label.setText("Zatrzymano.")

    @Slot(str)
    def _on_ai_chunk(self, text: str) -> None:
        self._full_response += text
        self._ai_out.insertPlainText(text)
        # Scroll to bottom
        sb = self._ai_out.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(str)
    def _on_ai_done(self, full: str) -> None:
        self._progress.setVisible(False)
        self._btn_gen.setEnabled(True)
        self._btn_stop.setEnabled(False)

        spec = _extract_json(full)
        if spec is None:
            self._status_label.setText("⚠  AI nie zwróciło poprawnego JSON. Spróbuj ponownie.")
            return

        self._parsed_spec = spec
        self._populate_preview(spec)

    @Slot(str)
    def _on_ai_error(self, err: str) -> None:
        self._progress.setVisible(False)
        self._btn_gen.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_label.setText(f"⚠  Błąd AI: {err.splitlines()[0]}")
        self._ai_out.append(f"\n\n⚠ BŁĄD:\n{err}")

    # ── Preview ───────────────────────────────────────────────────────────────
    def _populate_preview(self, spec: dict) -> None:
        name   = spec.get("project_name", "—")
        desc   = spec.get("board_description", "")
        w      = spec.get("board_width_mm", "?")
        h      = spec.get("board_height_mm", "?")
        nets   = spec.get("nets", [])
        notes  = spec.get("design_notes", "")
        comps  = spec.get("components", [])

        self._board_info.setText(
            f"📋 <b>{name}</b>  |  Wymiary: {w}×{h} mm  |  "
            f"Sieci: {len(nets)}  |  Komponenty: {len(comps)}"
        )

        zone_colors = {
            "center":  "#1a2a3a",
            "left":    "#1a2a1a",
            "right":   "#2a1a2a",
            "top":     "#2a2a1a",
            "scatter": "#1a1a1a",
        }
        zone_labels = {
            "center": "Centrum", "left": "Lewo", "right": "Prawo",
            "top": "Góra", "scatter": "Rozproszone",
        }

        self._comp_table.setRowCount(len(comps))
        for row, c in enumerate(comps):
            ref   = c.get("reference", "?")
            val   = c.get("value", "")
            fp    = c.get("footprint", "").split(":")[-1] if ":" in c.get("footprint","") else c.get("footprint","")
            cdesc = c.get("description", "")
            zone  = c.get("zone", "scatter")

            for col, text in enumerate([ref, val, fp, cdesc, zone_labels.get(zone, zone)]):
                item = QTableWidgetItem(text)
                item.setBackground(QColor(zone_colors.get(zone, "#1a1a1a")))
                self._comp_table.setItem(row, col, item)

        self._notes_label.setText(
            f"<b>Opis:</b> {desc}<br><b>Uwagi projektowe:</b> {notes}"
        )
        self._status_label.setText(
            f"✓  Wygenerowano {len(comps)} komponentów — "
            f"kliknij 'Utwórz projekt PCB' aby załadować do edytora."
        )
        self._btn_create.setEnabled(True)

    # ── Create project ────────────────────────────────────────────────────────
    def _create_project(self) -> None:
        if not self._parsed_spec:
            return
        try:
            board, name = _build_board_from_spec(self._parsed_spec)
            self._result_project = Project(name=name, board=board)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można zbudować projektu:\n{e}")

    def result_project(self) -> Optional[Project]:
        return self._result_project

    def closeEvent(self, event) -> None:
        self._stop_generation()
        super().closeEvent(event)
