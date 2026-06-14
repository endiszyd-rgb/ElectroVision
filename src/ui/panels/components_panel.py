"""Component database panel — LCSC search, SnapEDA links, component details."""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTextEdit, QSplitter, QComboBox, QProgressBar,
    QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
    QAbstractItemView, QFormLayout, QDoubleSpinBox
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QDesktopServices
from PySide6.QtCore import QUrl

from src.core.project import Project
from src.core.models.component import Component
from src.ai.bridge import AIBridge


# ── Offline component database (common parts) ─────────────────────────────────
_OFFLINE_DB: list[dict] = [
    # MCUs
    {"lcsc": "C2040", "mfr": "Espressif", "pn": "ESP32-WROOM-32D", "desc": "WiFi+BT module, 4MB Flash", "pkg": "Module", "price": 2.80, "cat": "MCU"},
    {"lcsc": "C701342", "mfr": "Espressif", "pn": "ESP32-S3-WROOM-1-N8", "desc": "WiFi+BT5 AI module, 8MB Flash", "pkg": "Module", "price": 3.20, "cat": "MCU"},
    {"lcsc": "C8734", "mfr": "STMicro", "pn": "STM32F103C8T6", "desc": "ARM Cortex-M3 72MHz, 64kB Flash", "pkg": "LQFP-48", "price": 1.80, "cat": "MCU"},
    {"lcsc": "C2833015", "mfr": "Raspberry Pi", "pn": "RP2040", "desc": "Dual-core M0+ 133MHz, 264kB RAM", "pkg": "QFN-56", "price": 0.99, "cat": "MCU"},
    {"lcsc": "C5165", "mfr": "Nordic", "pn": "nRF52840-QIAA", "desc": "BLE5+Thread+Zigbee, 1MB Flash", "pkg": "QFN-48", "price": 3.80, "cat": "MCU"},
    {"lcsc": "C149165", "mfr": "STMicro", "pn": "STM32F401CCU6", "desc": "ARM Cortex-M4F 84MHz, 256kB", "pkg": "UFQFPN-48", "price": 2.50, "cat": "MCU"},
    {"lcsc": "C46749", "mfr": "Microchip", "pn": "ATMEGA328P-AU", "desc": "AVR 8-bit 20MHz, 32kB Flash", "pkg": "TQFP-32", "price": 2.10, "cat": "MCU"},
    # Power
    {"lcsc": "C6187", "mfr": "AMS", "pn": "AMS1117-3.3", "desc": "LDO 3.3V 1A SOT-223", "pkg": "SOT-223", "price": 0.09, "cat": "Power"},
    {"lcsc": "C1099", "mfr": "TI", "pn": "LM1117-3.3", "desc": "LDO 3.3V 800mA", "pkg": "SOT-223", "price": 0.11, "cat": "Power"},
    {"lcsc": "C89358", "mfr": "MPS", "pn": "MP2307DN-LF-Z", "desc": "Buck 23V 3A 340kHz", "pkg": "SOIC-8", "price": 0.45, "cat": "Power"},
    {"lcsc": "C84258", "mfr": "INJOINIC", "pn": "IP5306", "desc": "Li-Ion charger+boost 5V/2.4A", "pkg": "SOP-8", "price": 0.35, "cat": "Power"},
    {"lcsc": "C73245", "mfr": "Microchip", "pn": "MCP73831T-2ACI/OT", "desc": "Li-Ion charger 500mA", "pkg": "SOT-23-5", "price": 0.45, "cat": "Power"},
    {"lcsc": "C78988", "mfr": "YMDC", "pn": "TP4056", "desc": "Li-Ion charger 1A with LED", "pkg": "SOP-8", "price": 0.12, "cat": "Power"},
    # Sensors
    {"lcsc": "C92489", "mfr": "Bosch", "pn": "BME280", "desc": "Temp+Humidity+Pressure I2C/SPI", "pkg": "LGA-8", "price": 1.20, "cat": "Sensor"},
    {"lcsc": "C24112", "mfr": "InvenSense", "pn": "MPU-6050", "desc": "6-axis IMU I2C, acc+gyro", "pkg": "QFN-24", "price": 0.65, "cat": "Sensor"},
    {"lcsc": "C322893", "mfr": "SHT", "pn": "SHT31-DIS", "desc": "Temp+Humidity ±0.2°C I2C", "pkg": "DFN-8", "price": 2.10, "cat": "Sensor"},
    {"lcsc": "C9798", "mfr": "Maxim", "pn": "DS18B20", "desc": "1-Wire temp sensor -55..+125°C", "pkg": "TO-92", "price": 0.55, "cat": "Sensor"},
    {"lcsc": "C89786", "mfr": "TI", "pn": "INA226AIDGST", "desc": "Current/power monitor I2C", "pkg": "MSOP-10", "price": 1.20, "cat": "Sensor"},
    # Display
    {"lcsc": "C2040", "mfr": "Winstar", "pn": "SSD1306", "desc": "0.96\" OLED 128x64 I2C/SPI", "pkg": "Module", "price": 0.80, "cat": "Display"},
    # USB
    {"lcsc": "C6568", "mfr": "Silicon Labs", "pn": "CP2102-GMR", "desc": "USB-UART bridge", "pkg": "QFN-28", "price": 0.60, "cat": "USB"},
    {"lcsc": "C84681", "mfr": "WCH", "pn": "CH340G", "desc": "USB-UART bridge, low cost", "pkg": "SOP-16", "price": 0.23, "cat": "USB"},
    # Memory
    {"lcsc": "C97521", "mfr": "Winbond", "pn": "W25Q16JVSSIQ", "desc": "16Mbit SPI Flash", "pkg": "SOP-8", "price": 0.28, "cat": "Memory"},
    {"lcsc": "C179171", "mfr": "Winbond", "pn": "W25Q128JVSIQ", "desc": "128Mbit SPI Flash", "pkg": "SOP-8", "price": 0.80, "cat": "Memory"},
    # Logic
    {"lcsc": "C5931", "mfr": "TI", "pn": "SN74HC595DR", "desc": "8-bit shift register, 3-state", "pkg": "SOIC-16", "price": 0.15, "cat": "Logic"},
    {"lcsc": "C7484", "mfr": "TI", "pn": "SN74HC245DWR", "desc": "Octal bus transceiver", "pkg": "SOIC-20", "price": 0.20, "cat": "Logic"},
    # Passive
    {"lcsc": "C17513", "mfr": "YAGEO", "pn": "RC0402FR-0710KL", "desc": "10kΩ 1% 0.0625W 0402", "pkg": "0402", "price": 0.005, "cat": "Resistor"},
    {"lcsc": "C14663", "mfr": "YAGEO", "pn": "CC0402KRX5R8BB104", "desc": "100nF 50V X5R 0402", "pkg": "0402", "price": 0.006, "cat": "Capacitor"},
    {"lcsc": "C20197", "mfr": "YAGEO", "pn": "CC0805KKX5R8BB106", "desc": "10µF 50V X5R 0805", "pkg": "0805", "price": 0.015, "cat": "Capacitor"},
    # Connectors
    {"lcsc": "C165948", "mfr": "Korean Hroparts", "pn": "USB-C-SMD-009", "desc": "USB Type-C receptacle SMD", "pkg": "SMD", "price": 0.22, "cat": "Connector"},
    {"lcsc": "C46407", "mfr": "JST", "pn": "B2B-PH-K-S(LF)(SN)", "desc": "JST PH 2-pin 2mm vertical", "pkg": "THT", "price": 0.08, "cat": "Connector"},
]


# ── LCSC search worker ─────────────────────────────────────────────────────────

class _LCSCSearchWorker(QThread):
    """Search LCSC component database via unofficial API."""
    results_ready = Signal(list)
    error         = Signal(str)

    def __init__(self, query: str, category: str = ""):
        super().__init__()
        self._query = query
        self._category = category

    def run(self) -> None:
        try:
            # LCSC public search endpoint
            params = urllib.parse.urlencode({
                "keyword": self._query,
                "currentPage": 1,
                "pageSize": 30,
            })
            url = f"https://wmsc.lcsc.com/ftps/wm/product/search?{params}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ElectroVision/1.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            products = data.get("result", {}).get("productSearchResultVO", {}).get("productList", [])
            results = []
            for p in products:
                results.append({
                    "lcsc":  p.get("productCode", ""),
                    "mfr":   p.get("brandNameEn", ""),
                    "pn":    p.get("productModel", ""),
                    "desc":  p.get("productDescEn", ""),
                    "pkg":   p.get("encapStandard", ""),
                    "price": p.get("prices", [{}])[0].get("productPrice", 0) if p.get("prices") else 0,
                    "stock": p.get("stockNumber", 0),
                    "cat":   p.get("catalogName", ""),
                    "datasheet": p.get("pdfUrl", ""),
                })
            self.results_ready.emit(results)
        except Exception as e:
            # Fall through to offline DB filter
            self.results_ready.emit([])


# ── Panel ─────────────────────────────────────────────────────────────────────

class ComponentsPanel(QWidget):
    component_add_requested = Signal(object)  # Component

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._results: list[dict] = []
        self._search_worker: Optional[_LCSCSearchWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Search bar ────────────────────────────────────────────────────────
        search_box = QGroupBox("Wyszukaj komponent")
        search_layout = QVBoxLayout(search_box)

        row1 = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Np. ESP32, AMS1117, 100nF, BME280…")
        self._search_edit.returnPressed.connect(self._do_search)
        row1.addWidget(self._search_edit, 1)

        self._cat_combo = QComboBox()
        self._cat_combo.addItems([
            "Wszystkie", "MCU", "Power", "Sensor", "USB",
            "Memory", "Logic", "Resistor", "Capacitor", "Connector", "Display",
        ])
        self._cat_combo.setMinimumWidth(110)
        row1.addWidget(self._cat_combo)

        btn_search = QPushButton("🔍 Szukaj")
        btn_search.clicked.connect(self._do_search)
        btn_search.setStyleSheet("QPushButton { background: #1a4a8f; color: white; padding: 4px 12px; }")
        row1.addWidget(btn_search)
        search_layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_offline = QPushButton("📦 Offline DB")
        btn_offline.setToolTip("Pokaż lokalną bazę 30 popularnych komponentów")
        btn_offline.clicked.connect(self._show_offline)
        row2.addWidget(btn_offline)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        row2.addWidget(self._progress, 1)

        self._result_count = QLabel("Wpisz frazę i naciśnij Szukaj")
        self._result_count.setStyleSheet("color: #888; font-size: 10px;")
        row2.addWidget(self._result_count)
        search_layout.addLayout(row2)

        layout.addWidget(search_box)

        # ── Splitter: results + details ───────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Results table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "LCSC#", "Producent", "Part Number", "Opis", "Pakiet", "Cena", "Kategoria"
        ])
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { gridline-color: #2a2a3a; }"
            "QTableWidget::item:alternate { background: #1a1a2a; }"
        )
        self._table.currentCellChanged.connect(lambda row, *_: self._on_row_select(row))
        self._table.doubleClicked.connect(self._on_add_to_bom)
        splitter.addWidget(self._table)

        # Details + actions
        bottom = QWidget()
        bl = QHBoxLayout(bottom)

        # Detail
        detail_box = QGroupBox("Szczegóły komponentu")
        dl = QVBoxLayout(detail_box)
        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setFont(QFont("Consolas", 9))
        self._detail_text.setPlaceholderText("Kliknij komponent…")
        dl.addWidget(self._detail_text)
        bl.addWidget(detail_box, 2)

        # Actions
        actions_box = QGroupBox("Akcje")
        al = QVBoxLayout(actions_box)

        btn_add_bom = QPushButton("📋 Dodaj do BOM projektu")
        btn_add_bom.clicked.connect(self._on_add_to_bom)
        btn_add_bom.setStyleSheet("QPushButton { background: #1a4a1a; }")
        al.addWidget(btn_add_bom)

        btn_add_editor = QPushButton("✏ Umieść na płytce (Edytor)")
        btn_add_editor.clicked.connect(self._on_add_to_editor)
        btn_add_editor.setStyleSheet("QPushButton { background: #1a3a4a; }")
        al.addWidget(btn_add_editor)

        btn_lcsc = QPushButton("🌐 Otwórz w LCSC")
        btn_lcsc.clicked.connect(self._open_lcsc)
        al.addWidget(btn_lcsc)

        btn_datasheet = QPushButton("📄 Datasheet")
        btn_datasheet.clicked.connect(self._open_datasheet)
        al.addWidget(btn_datasheet)

        btn_snapeda = QPushButton("🔗 SnapEDA (KiCad footprint)")
        btn_snapeda.clicked.connect(self._open_snapeda)
        al.addWidget(btn_snapeda)

        al.addStretch()

        # AI analysis
        btn_ai = QPushButton("🤖 AI: wyjaśnij komponent")
        btn_ai.clicked.connect(self._ai_explain)
        al.addWidget(btn_ai)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(5)
        al.addWidget(self._ai_progress)

        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 8))
        self._ai_out.setMaximumHeight(140)
        self._ai_out.setPlaceholderText("Opis AI…")
        al.addWidget(self._ai_out)

        bl.addWidget(actions_box, 1)

        splitter.addWidget(bottom)
        splitter.setSizes([380, 260])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project

    # ── Search ────────────────────────────────────────────────────────────────

    def _do_search(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            self._show_offline()
            return
        cat = self._cat_combo.currentText()

        # First show offline matches
        offline = self._filter_offline(query, cat)
        self._populate_table(offline)
        self._result_count.setText(f"Offline: {len(offline)}  — Szukam online…")
        self._progress.setVisible(True)

        # Then search LCSC
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.terminate()
        self._search_worker = _LCSCSearchWorker(query, cat)
        self._search_worker.results_ready.connect(self._on_online_results)
        self._search_worker.start()

    def _show_offline(self) -> None:
        cat = self._cat_combo.currentText()
        query = self._search_edit.text().strip()
        results = self._filter_offline(query, cat)
        self._populate_table(results)
        self._result_count.setText(f"Offline DB: {len(results)} komponentów")
        self._progress.setVisible(False)

    def _filter_offline(self, query: str, cat: str) -> list[dict]:
        q = query.lower()
        results = []
        for c in _OFFLINE_DB:
            if cat not in ("Wszystkie", "") and c.get("cat", "") != cat:
                continue
            if q and not any(q in str(v).lower() for v in c.values()):
                continue
            results.append(c)
        return results

    @Slot(list)
    def _on_online_results(self, results: list) -> None:
        self._progress.setVisible(False)
        if results:
            existing_pns = {r.get("pn", "") for r in self._results}
            new = [r for r in results if r.get("pn", "") not in existing_pns]
            combined = self._results + new
            self._populate_table(combined)
            self._result_count.setText(
                f"Offline: {len(self._results)}  +  Online: {len(new)}  =  {len(combined)} łącznie"
            )
        else:
            self._result_count.setText(
                f"{len(self._results)} wyników (offline) — brak połączenia z LCSC"
            )

    # ── Table ─────────────────────────────────────────────────────────────────

    def _populate_table(self, items: list[dict]) -> None:
        self._results = items
        self._table.setRowCount(len(items))
        cat_colors = {
            "MCU": "#2a4a8f", "Power": "#4a2a1a", "Sensor": "#1a4a2a",
            "USB": "#4a3a1a", "Memory": "#2a2a4a", "Logic": "#3a1a4a",
        }
        for row, c in enumerate(items):
            price_str = f"${c.get('price', 0):.3f}" if c.get("price", 0) else "—"
            self._table.setItem(row, 0, self._item(c.get("lcsc", ""),  "#4a90d9"))
            self._table.setItem(row, 1, self._item(c.get("mfr", "")))
            self._table.setItem(row, 2, self._item(c.get("pn",  ""),  "#e8c060"))
            self._table.setItem(row, 3, self._item(c.get("desc", "")))
            self._table.setItem(row, 4, self._item(c.get("pkg",  "")))
            self._table.setItem(row, 5, self._item(price_str,         "#80e080", Qt.AlignRight))
            cat = c.get("cat", "")
            it = self._item(cat)
            it.setBackground(QBrush(QColor(cat_colors.get(cat, "#1a1a2a"))))
            self._table.setItem(row, 6, it)
        self._table.resizeColumnToContents(0)
        self._table.resizeColumnToContents(4)
        self._table.resizeColumnToContents(5)

    def _item(self, text: str, color: str = "", align=Qt.AlignLeft) -> QTableWidgetItem:
        it = QTableWidgetItem(str(text))
        it.setTextAlignment(align | Qt.AlignVCenter)
        if color:
            it.setForeground(QBrush(QColor(color)))
        return it

    # ── Selection ─────────────────────────────────────────────────────────────

    def _current_component(self) -> Optional[dict]:
        row = self._table.currentRow()
        if 0 <= row < len(self._results):
            return self._results[row]
        return None

    def _on_row_select(self, row: int) -> None:
        if not (0 <= row < len(self._results)):
            return
        c = self._results[row]
        stock = c.get("stock", "N/A")
        ds = c.get("datasheet", "—")
        self._detail_text.setHtml(
            f"<b style='color:#e8c060;'>{c.get('pn','')}</b> "
            f"<span style='color:#4a90d9;'>[{c.get('lcsc','')}]</span><br>"
            f"<b>Producent:</b> {c.get('mfr','')}<br>"
            f"<b>Opis:</b> {c.get('desc','')}<br>"
            f"<b>Pakiet:</b> {c.get('pkg','')}<br>"
            f"<b>Kategoria:</b> {c.get('cat','')}<br>"
            f"<b>Cena:</b> ${c.get('price',0):.4f}<br>"
            + (f"<b>Stan mag.:</b> {stock}<br>" if stock != "N/A" else "")
            + (f"<b>Datasheet:</b> <a href='{ds}'>{ds[:60]}</a>" if ds and ds != "—" else "")
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_add_to_bom(self) -> None:
        c = self._current_component()
        if not c or not self._project.board:
            QMessageBox.information(self, "Info", "Wybierz komponent i załaduj projekt.")
            return
        ref_prefix = c.get("pn", "U")[:1].upper()
        if ref_prefix not in "RCLDQUYJSWF":
            ref_prefix = "U"
        # Find next available number
        existing = [
            int(comp.reference[len(ref_prefix):])
            for comp in self._project.board.components
            if comp.reference.startswith(ref_prefix)
            and comp.reference[len(ref_prefix):].isdigit()
        ]
        num = max(existing, default=0) + 1
        new_comp = Component(
            reference=f"{ref_prefix}{num}",
            value=c.get("pn", ""),
            footprint="",
            x=0, y=0,
            description=c.get("desc", ""),
            manufacturer=c.get("mfr", ""),
            manufacturer_pn=c.get("pn", ""),
        )
        self._project.board.components.append(new_comp)
        QMessageBox.information(
            self, "Dodano",
            f"Dodano {new_comp.reference} ({new_comp.value}) do BOM projektu."
        )

    def _on_add_to_editor(self) -> None:
        c = self._current_component()
        if not c:
            return
        ref_prefix = "U"
        pn = c.get("pn", "Component")
        comp = Component(
            reference=ref_prefix,
            value=pn,
            footprint="",
            x=0, y=0,
            description=c.get("desc", ""),
            manufacturer=c.get("mfr", ""),
            manufacturer_pn=pn,
        )
        self.component_add_requested.emit(comp)

    def _open_lcsc(self) -> None:
        c = self._current_component()
        if not c:
            return
        lcsc = c.get("lcsc", "")
        pn   = c.get("pn", "")
        if lcsc:
            QDesktopServices.openUrl(QUrl(f"https://www.lcsc.com/product-detail/{lcsc}.html"))
        elif pn:
            q = urllib.parse.quote(pn)
            QDesktopServices.openUrl(QUrl(f"https://www.lcsc.com/search?q={q}"))

    def _open_datasheet(self) -> None:
        c = self._current_component()
        if not c:
            return
        ds = c.get("datasheet", "")
        if ds and ds.startswith("http"):
            QDesktopServices.openUrl(QUrl(ds))
        else:
            pn = urllib.parse.quote(c.get("pn", ""))
            QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={pn}+datasheet+filetype:pdf"))

    def _open_snapeda(self) -> None:
        c = self._current_component()
        if not c:
            return
        pn = urllib.parse.quote(c.get("pn", ""))
        QDesktopServices.openUrl(QUrl(f"https://www.snapeda.com/search/?q={pn}&search-type=parts"))

    def _ai_explain(self) -> None:
        c = self._current_component()
        if not c:
            return
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"Wyjaśnij komponent {c.get('mfr','')} {c.get('pn','')}:\n"
            f"Opis: {c.get('desc','')}\n"
            f"Pakiet: {c.get('pkg','')}\n\n"
            "Podaj: do czego służy, jak podłączyć (zasilanie, I2C/SPI/UART adresy), "
            "typowy schemat aplikacji, przykładowy kod inicjalizacji (C lub MicroPython), "
            "najczęstsze pułapki.",
            system_key="code_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=lambda _: self._ai_progress.setVisible(False),
            on_error=lambda e: (self._ai_progress.setVisible(False),
                                self._ai_out.append(f"\n⚠ {e}")),
        )
