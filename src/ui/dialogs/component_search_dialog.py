"""Component Search Dialog — search for parts by value/footprint with shop links."""
from __future__ import annotations
import re
import webbrowser
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QTextEdit, QMessageBox, QSplitter,
    QWidget, QCheckBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QUrl
from PySide6.QtGui import QFont, QColor, QBrush, QDesktopServices

from src.core.project import Project
from src.core.models.component import Component


# ── Component DB ───────────────────────────────────────────────────────────────

class PartSuggestion:
    __slots__ = ("name", "value", "footprint", "description", "lcsc", "package",
                 "category", "estimated_price_usd")

    def __init__(self, name, value, footprint, description, lcsc="",
                 package="", category="", price=0.0):
        self.name = name
        self.value = value
        self.footprint = footprint
        self.description = description
        self.lcsc = lcsc
        self.package = package
        self.category = category
        self.estimated_price_usd = price


_COMMON_PARTS = [
    PartSuggestion("Rezystor 100Ω", "100R", "0402", "Rezystor SMD 1% 1/16W", "C25108", "0402", "resistor", 0.01),
    PartSuggestion("Rezystor 10kΩ", "10K", "0402", "Rezystor SMD 1% 1/16W", "C25744", "0402", "resistor", 0.01),
    PartSuggestion("Rezystor 4.7kΩ", "4K7", "0402", "Rezystor SMD 1% 1/16W", "C25900", "0402", "resistor", 0.01),
    PartSuggestion("Kondensator 100nF", "100nF", "0402", "MLCC X5R 10V", "C307331", "0402", "capacitor", 0.02),
    PartSuggestion("Kondensator 10µF", "10uF", "0805", "MLCC X5R 16V", "C15850", "0805", "capacitor", 0.05),
    PartSuggestion("Kondensator 100µF", "100uF", "SMD 6.3×7.7", "Elektrolityczny 10V", "C72535", "6.3x7.7", "capacitor", 0.10),
    PartSuggestion("LED czerwona", "RED", "LED_0805", "LED SMD 0805 czerwona", "C84256", "0805", "led", 0.05),
    PartSuggestion("LED zielona", "GREEN", "LED_0805", "LED SMD 0805 zielona", "C72044", "0805", "led", 0.05),
    PartSuggestion("AMS1117-3.3", "3.3V", "SOT-223", "LDO 1A 3.3V", "C6186", "SOT-223", "ic", 0.12),
    PartSuggestion("AMS1117-5.0", "5V", "SOT-223", "LDO 1A 5V", "C6187", "SOT-223", "ic", 0.12),
    PartSuggestion("STM32F103C8T6", "STM32F103C8T6", "LQFP-48", "ARM Cortex-M3 72MHz", "C8734", "LQFP-48", "ic", 1.50),
    PartSuggestion("ESP32-WROOM-32", "ESP32", "Module", "WiFi+BT SoC module", "C82899", "Module", "ic", 2.50),
    PartSuggestion("CH340C", "CH340C", "SOP-16", "USB-UART bridge", "C84681", "SOP-16", "ic", 0.30),
    PartSuggestion("NRF24L01+", "NRF24L01+", "QFN-20", "2.4GHz RF transceiver", "C114073", "QFN-20", "ic", 0.80),
    PartSuggestion("LM358", "LM358", "SOP-8", "Dual op-amp", "C7950", "SOP-8", "ic", 0.08),
    PartSuggestion("MOSFET N IRLZ44N", "IRLZ44N", "TO-220", "N-channel 55V 47A logic-level", "", "TO-220", "transistor", 0.60),
    PartSuggestion("MOSFET N AO3400", "AO3400", "SOT-23", "N-ch 30V 5.7A SMD", "C20917", "SOT-23", "transistor", 0.08),
    PartSuggestion("Dioda 1N4007", "1N4007", "DO-41", "Dioda prostownicza 1A 1000V", "C152562", "DO-41", "diode", 0.02),
    PartSuggestion("Schottky SS34", "SS34", "DO-214AC", "Schottky 3A 40V", "C8678", "DO-214AC", "diode", 0.06),
    PartSuggestion("Kryształ 16MHz", "16MHz", "HC-49S", "Kryształ kwarcowy 16MHz", "C393939", "HC-49S", "crystal", 0.20),
    PartSuggestion("Przycisk TACT", "SW_PUSH", "SW_PUSH_6mm", "Mikroprzycisk SMD 6×6mm", "C318884", "6x6mm", "switch", 0.05),
    PartSuggestion("Złącze USB-B micro", "USB_B_MICRO", "USB_Micro-B", "Złącze microUSB żeńskie SMD", "C10418", "USB-Micro-B", "connector", 0.15),
    PartSuggestion("Złącze JST 2-pin", "JST_2P", "JST_PH_2p", "Złącze JST PH 2mm 2-pin", "C131337", "JST-PH", "connector", 0.10),
    PartSuggestion("Induktor 10µH", "10uH", "0805", "Induktor SMD 10µH 300mA", "C1034", "0805", "inductor", 0.08),
    PartSuggestion("Bezpiecznik 500mA", "F500mA", "1206", "Bezpiecznik SMD slow-blow", "C914877", "1206", "fuse", 0.05),
    PartSuggestion("RP2040", "RP2040", "QFN-56", "Raspberry Pi MCU, 133MHz dual-core", "C2040", "QFN-56", "ic", 1.20),
    PartSuggestion("ATmega328P", "ATmega328P", "TQFP-32", "8-bit AVR MCU (Arduino core)", "C14877", "TQFP-32", "ic", 1.80),
    PartSuggestion("74HC595", "74HC595", "SOP-16", "8-bit shift register", "C5947", "SOP-16", "ic", 0.07),
    PartSuggestion("74HC245", "74HC245", "SOP-20", "Octal bus transceiver", "C5765", "SOP-20", "ic", 0.10),
    PartSuggestion("TXS0102", "TXS0102", "SOT-23-6", "2-bit voltage translator", "C17206", "SOT-23-6", "ic", 0.25),
    PartSuggestion("MPU-6050", "MPU6050", "QFN-24", "6-axis IMU gyro+accel I2C", "C24112", "QFN-24", "ic", 0.80),
    PartSuggestion("BMP280", "BMP280", "LGA-8", "Temp+pressure sensor I2C/SPI", "C166782", "LGA-8", "ic", 0.80),
    PartSuggestion("W25Q32", "W25Q32", "SOP-8", "32Mbit NOR Flash SPI", "C179171", "SOP-8", "ic", 0.30),
]


def _search_parts(query: str, category: str = "Wszystkie") -> list[PartSuggestion]:
    q = query.strip().upper()
    results = []
    for p in _COMMON_PARTS:
        if category != "Wszystkie" and p.category != category:
            continue
        haystack = f"{p.name} {p.value} {p.footprint} {p.description} {p.lcsc}".upper()
        if not q or q in haystack:
            results.append(p)
    return results


def _make_shop_links(part: PartSuggestion) -> dict[str, str]:
    q = part.value.replace(" ", "+")
    links = {
        "LCSC": f"https://www.lcsc.com/search?q={q}",
        "DigiKey": f"https://www.digikey.pl/en/products/filter?keywords={q}",
        "Mouser": f"https://eu.mouser.com/Search/Refine?Keyword={q}",
        "TME": f"https://www.tme.eu/pl/katalog/?search={q}",
        "Botland": f"https://botland.com.pl/szukaj/?s={q}",
    }
    if part.lcsc:
        links["LCSC (direct)"] = f"https://www.lcsc.com/product-detail/{part.lcsc}.html"
    return links


# ── Dialog ─────────────────────────────────────────────────────────────────────

class ComponentSearchDialog(QDialog):
    component_add_requested = Signal(object)  # Component

    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Wyszukiwarka komponentów")
        self.resize(900, 600)
        self._results: list[PartSuggestion] = []
        self._build_ui()
        self._search()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Search bar ────────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Szukaj: ATmega, 100nF, NRF24, AMS1117…")
        self._query.returnPressed.connect(self._search)
        search_row.addWidget(self._query, 1)

        self._cat_combo = QComboBox()
        self._cat_combo.addItems([
            "Wszystkie", "ic", "resistor", "capacitor", "led", "diode",
            "transistor", "crystal", "connector", "switch", "inductor", "fuse"
        ])
        self._cat_combo.currentIndexChanged.connect(self._search)
        search_row.addWidget(self._cat_combo)

        btn_search = QPushButton("🔍 Szukaj")
        btn_search.clicked.connect(self._search)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        # ── Splitter ──────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Results table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Nazwa", "Wartość", "Obudowa", "Kategoria", "LCSC#", "Cena (USD)"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_select)
        self._table.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self._table)

        # Detail panel
        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(4, 4, 4, 4)

        self._detail_label = QLabel("Wybierz komponent z listy")
        self._detail_label.setWordWrap(True)
        dl.addWidget(self._detail_label)

        self._desc_text = QTextEdit()
        self._desc_text.setReadOnly(True)
        self._desc_text.setFont(QFont("Consolas", 9))
        self._desc_text.setMaximumHeight(100)
        dl.addWidget(self._desc_text)

        links_box = QGroupBox("Sklepy — kliknij aby otworzyć")
        self._links_layout = QVBoxLayout(links_box)
        dl.addWidget(links_box)
        self._link_buttons: list[QPushButton] = []

        btn_add = QPushButton("+ Dodaj do projektu")
        btn_add.clicked.connect(self._add_to_project)
        dl.addWidget(btn_add)

        dl.addStretch()
        splitter.addWidget(detail)
        splitter.setSizes([580, 320])
        layout.addWidget(splitter, 1)

        # ── Status ────────────────────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setStyleSheet("color: #aaa; font-size: 10px;")
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _search(self) -> None:
        q = self._query.text()
        cat = self._cat_combo.currentText()
        self._results = _search_parts(q, cat)
        self._populate_table()
        self._status.setText(f"Znaleziono: {len(self._results)} komponentów (baza lokalna)")

    def _populate_table(self) -> None:
        self._table.setRowCount(0)
        for p in self._results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(p.name))
            self._table.setItem(row, 1, QTableWidgetItem(p.value))
            self._table.setItem(row, 2, QTableWidgetItem(p.package or p.footprint))
            cat_item = QTableWidgetItem(p.category)
            cat_colors = {
                "ic": QColor("#1a3a5a"), "resistor": QColor("#2a2a1a"),
                "capacitor": QColor("#1a2a3a"), "led": QColor("#2a1a1a"),
                "diode": QColor("#2a1a2a"), "transistor": QColor("#1a2a1a"),
            }
            cat_item.setBackground(QBrush(cat_colors.get(p.category, QColor("#222"))))
            self._table.setItem(row, 3, cat_item)
            self._table.setItem(row, 4, QTableWidgetItem(p.lcsc))
            price_str = f"${p.estimated_price_usd:.2f}" if p.estimated_price_usd else "-"
            self._table.setItem(row, 5, QTableWidgetItem(price_str))

    def _on_select(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._results):
            return
        part = self._results[row]

        self._detail_label.setText(
            f"<b>{part.name}</b><br>"
            f"Wartość: {part.value}  |  Obudowa: {part.package}  |  LCSC: {part.lcsc or 'N/A'}<br>"
            f"Cena: ${part.estimated_price_usd:.2f} (szacunkowa)"
        )
        self._detail_label.setTextFormat(Qt.RichText)
        self._desc_text.setPlainText(part.description)

        # Rebuild link buttons
        for btn in self._link_buttons:
            btn.deleteLater()
        self._link_buttons.clear()

        links = _make_shop_links(part)
        for shop, url in links.items():
            btn = QPushButton(f"🌐 {shop}")
            captured_url = url
            btn.clicked.connect(lambda _, u=captured_url: QDesktopServices.openUrl(QUrl(u)))
            self._links_layout.addWidget(btn)
            self._link_buttons.append(btn)

    def _on_double_click(self) -> None:
        self._add_to_project()

    def _add_to_project(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._results):
            QMessageBox.warning(self, "Dodaj", "Wybierz komponent.")
            return
        part = self._results[row]

        board = self._project.board if self._project else None
        if not board:
            QMessageBox.warning(self, "Dodaj", "Załaduj lub utwórz projekt PCB.")
            return

        # Auto-generate reference
        cat = part.category
        prefix = {
            "ic": "U", "resistor": "R", "capacitor": "C", "led": "LED",
            "diode": "D", "transistor": "Q", "crystal": "X", "connector": "J",
            "switch": "SW", "inductor": "L", "fuse": "F",
        }.get(cat, "U")
        existing_nums = [
            int(re.search(r"\d+", c.reference).group())
            for c in board.components
            if c.reference.startswith(prefix) and re.search(r"\d+", c.reference)
        ]
        num = max(existing_nums, default=0) + 1
        ref = f"{prefix}{num}"

        from src.core.models.component import Component
        comp = Component(
            reference=ref,
            value=part.value,
            footprint=part.footprint,
            x=10.0 + (num % 10) * 5.0,
            y=10.0 + (num // 10) * 5.0,
        )
        comp.manufacturer_pn = part.lcsc
        comp.description = part.description
        board.components.append(comp)

        self._status.setText(f"Dodano {ref} ({part.name}) do projektu")
        self.component_add_requested.emit(comp)
