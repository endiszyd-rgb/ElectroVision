"""Cost report panel — component prices, LCSC links, AI optimisation."""
from __future__ import annotations
import csv
import io
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTextEdit, QProgressBar, QSplitter, QDoubleSpinBox,
    QComboBox, QFileDialog, QMessageBox, QLineEdit, QAbstractItemView
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project
from src.core.models.component import Component
from src.ai.bridge import AIBridge


# ── Offline price database (LCSC typical prices in USD, Jan 2025) ─────────────
# Format: (partial value/type match) → unit_price_usd
_PRICE_DB: list[tuple[str, float]] = [
    # Resistors
    ("0402", 0.005), ("0603", 0.006), ("0805", 0.008), ("1206", 0.010),
    # Capacitors ceramic
    ("100nF", 0.006), ("10nF", 0.005), ("1uF", 0.008), ("10uF", 0.015),
    ("100uF", 0.080), ("22pF", 0.006), ("47pF", 0.006),
    # Electrolytic
    ("47uF", 0.050), ("220uF", 0.080), ("1000uF", 0.20),
    # LEDs
    ("LED", 0.018),
    # Crystals
    ("MHz", 0.18), ("kHz", 0.12), ("32768", 0.10),
    # Inductors
    ("uH", 0.04), ("mH", 0.08),
    # Common ICs
    ("AMS1117", 0.09), ("LM1117", 0.12), ("LM7805", 0.15),
    ("ESP32", 2.80), ("ESP8266", 1.20),
    ("STM32F103", 1.80), ("STM32F401", 3.20), ("STM32F407", 5.50),
    ("RP2040", 1.00),
    ("ATmega328", 2.50), ("ATmega2560", 5.00),
    ("nRF52840", 3.80), ("nRF52832", 2.50),
    ("CP2102", 0.60), ("CH340", 0.25), ("FT232", 1.20),
    ("W25Q16", 0.30), ("W25Q32", 0.40), ("W25Q64", 0.55), ("W25Q128", 0.80),
    ("BME280", 1.20), ("MPU6050", 0.65), ("DS18B20", 0.55),
    ("SSD1306", 0.80),
    ("MCP73831", 0.45), ("TP4056", 0.15), ("IP5306", 0.35),
    ("SS34", 0.08), ("1N4148", 0.04), ("1N5819", 0.06),
    ("MOSFET", 0.12), ("NPN", 0.04), ("PNP", 0.04),
    # Connectors
    ("USB_C", 0.25), ("USB_Micro", 0.18), ("USB_Mini", 0.15),
    ("JST", 0.10), ("Conn", 0.08),
    # Default fallback
    ("?", 0.10),
]


def _estimate_price(comp: Component) -> float:
    """Estimate unit price based on component value/footprint."""
    haystack = f"{comp.value} {comp.footprint} {comp.reference}".upper()
    for keyword, price in _PRICE_DB:
        if keyword.upper() in haystack:
            return price
    return 0.10  # default


CURRENCY_RATES = {"USD": 1.0, "PLN": 4.02, "EUR": 0.92}


class CostPanel(QWidget):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._currency = "USD"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        btn_calc = QPushButton("💰 Przelicz koszty")
        btn_calc.clicked.connect(self._recalculate)
        toolbar.addWidget(btn_calc)

        self._currency_combo = QComboBox()
        self._currency_combo.addItems(["USD", "PLN", "EUR"])
        self._currency_combo.currentTextChanged.connect(self._on_currency_change)
        toolbar.addWidget(QLabel("Waluta:"))
        toolbar.addWidget(self._currency_combo)

        self._qty_spin = QDoubleSpinBox()
        self._qty_spin.setRange(1, 10000)
        self._qty_spin.setValue(1)
        self._qty_spin.setDecimals(0)
        self._qty_spin.setSuffix(" szt.")
        self._qty_spin.valueChanged.connect(self._recalculate)
        toolbar.addWidget(QLabel("Ilość:"))
        toolbar.addWidget(self._qty_spin)

        toolbar.addStretch()

        btn_csv = QPushButton("📄 CSV")
        btn_csv.clicked.connect(self._export_csv)
        toolbar.addWidget(btn_csv)

        btn_pdf = QPushButton("📑 PDF")
        btn_pdf.clicked.connect(self._export_pdf)
        toolbar.addWidget(btn_pdf)

        layout.addLayout(toolbar)

        # ── Splitter ──────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Table
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "Reference", "Wartość", "Footprint", "Typ",
            "Cena jedn.", "Ilość", "Suma", "LCSC Link"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { gridline-color: #2a2a3a; }"
            "QTableWidget::item:alternate { background: #1a1a2a; }"
        )
        splitter.addWidget(self._table)

        # Bottom: totals + AI
        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)

        # Totals
        totals_box = QGroupBox("Podsumowanie kosztów")
        totals_layout = QVBoxLayout(totals_box)
        self._totals_label = QLabel("Brak projektu")
        self._totals_label.setTextFormat(Qt.RichText)
        self._totals_label.setFont(QFont("Consolas", 10))
        totals_layout.addWidget(self._totals_label)

        markup_row = QHBoxLayout()
        markup_row.addWidget(QLabel("Marża NRE:"))
        self._markup_spin = QDoubleSpinBox()
        self._markup_spin.setRange(0, 300)
        self._markup_spin.setValue(20)
        self._markup_spin.setSuffix("%")
        self._markup_spin.valueChanged.connect(self._recalculate)
        markup_row.addWidget(self._markup_spin)
        markup_row.addStretch()
        totals_layout.addLayout(markup_row)
        bottom_layout.addWidget(totals_box, 1)

        # AI
        ai_box = QGroupBox("🤖 AI Optymalizacja kosztów")
        ai_layout = QVBoxLayout(ai_box)

        btn_row = QHBoxLayout()
        btn_opt = QPushButton("Zaproponuj tańsze zamienniki")
        btn_opt.clicked.connect(self._ai_optimize)
        btn_row.addWidget(btn_opt)

        btn_lcsc = QPushButton("Znajdź w LCSC")
        btn_lcsc.clicked.connect(self._ai_lcsc)
        btn_row.addWidget(btn_lcsc)
        ai_layout.addLayout(btn_row)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(5)
        ai_layout.addWidget(self._ai_progress)

        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 9))
        self._ai_out.setPlaceholderText("Sugestie AI dotyczące kosztów…")
        ai_layout.addWidget(self._ai_out)
        bottom_layout.addWidget(ai_box, 2)

        splitter.addWidget(bottom)
        splitter.setSizes([400, 250])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._recalculate()

    def _on_currency_change(self, cur: str) -> None:
        self._currency = cur
        self._recalculate()

    def _recalculate(self) -> None:
        if not self._project.board:
            self._table.setRowCount(0)
            self._totals_label.setText("<i>Brak projektu PCB</i>")
            return

        qty = int(self._qty_spin.value())
        rate = CURRENCY_RATES.get(self._currency, 1.0)
        sym = {"USD": "$", "PLN": "zł", "EUR": "€"}.get(self._currency, "$")

        comps = self._project.board.components
        self._table.setRowCount(len(comps))

        total_usd = 0.0
        type_totals: dict[str, float] = {}

        for row, comp in enumerate(comps):
            price_usd = _estimate_price(comp)
            total_comp = price_usd * qty
            total_usd += price_usd

            ctype = comp.component_type
            type_totals[ctype] = type_totals.get(ctype, 0.0) + price_usd

            lcsc_search = f"https://lcsc.com/search?q={comp.value.replace(' ','+')}"

            def _item(text: str, align=Qt.AlignLeft, color: str = "") -> QTableWidgetItem:
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align | Qt.AlignVCenter)
                if color:
                    it.setForeground(QBrush(QColor(color)))
                return it

            self._table.setItem(row, 0, _item(comp.reference, color="#e8c060"))
            self._table.setItem(row, 1, _item(comp.value))
            fp_short = comp.footprint.split(":")[-1] if ":" in comp.footprint else comp.footprint
            self._table.setItem(row, 2, _item(fp_short))
            self._table.setItem(row, 3, _item(ctype))
            self._table.setItem(row, 4, _item(f"{sym}{price_usd*rate:.3f}", Qt.AlignRight))
            self._table.setItem(row, 5, _item(str(qty), Qt.AlignCenter))
            self._table.setItem(row, 6, _item(f"{sym}{total_comp*rate:.2f}", Qt.AlignRight, "#80e080"))
            self._table.setItem(row, 7, _item(lcsc_search))

        # Totals
        markup = self._markup_spin.value() / 100.0
        total_batch = total_usd * qty
        total_with_markup = total_batch * (1 + markup)
        unit_with_markup = total_with_markup / max(qty, 1)

        by_type_rows = "".join(
            f"<tr><td>{t}</td><td align='right'>{sym}{v*rate:.2f}</td></tr>"
            for t, v in sorted(type_totals.items(), key=lambda x: -x[1])
        )

        self._totals_label.setText(
            f"<table width='100%'>"
            f"<tr><td><b>Koszt komponentów (1 szt.):</b></td>"
            f"<td align='right'><b style='color:#4af;'>{sym}{total_usd*rate:.2f}</b></td></tr>"
            f"<tr><td><b>Partia {qty} szt.:</b></td>"
            f"<td align='right'><b style='color:#4af;'>{sym}{total_batch*rate:.2f}</b></td></tr>"
            f"<tr><td><b>Z marżą {self._markup_spin.value():.0f}%:</b></td>"
            f"<td align='right'><b style='color:#fa4;'>{sym}{total_with_markup*rate:.2f}</b></td></tr>"
            f"<tr><td><b>Cena jednostkowa z marżą:</b></td>"
            f"<td align='right'><b style='color:#4e4;'>{sym}{unit_with_markup*rate:.2f}</b></td></tr>"
            f"<tr><td colspan='2'><hr/></td></tr>"
            f"{by_type_rows}"
            f"</table>"
        )

    def _bom_text(self) -> str:
        if not self._project.board:
            return ""
        rows = []
        for comp in self._project.board.components:
            rows.append(f"{comp.reference}: {comp.value} ({comp.footprint})")
        return "\n".join(rows[:40])

    def _ai_optimize(self) -> None:
        if not self._project.board:
            return
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"BOM projektu '{self._project.name}':\n{self._bom_text()}\n\n"
            "Zaproponuj tańsze zamienniki dla najdroższych komponentów. "
            "Podaj: oryginalny komponent → zamiennik (producent, nr katalogowy), "
            "oszczędność szacunkowa, uwagi o kompatybilności. "
            "Format: tabela Markdown.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=lambda _: self._ai_progress.setVisible(False),
            on_error=lambda e: (self._ai_progress.setVisible(False), self._ai_out.append(f"\n⚠ {e}")),
        )

    def _ai_lcsc(self) -> None:
        if not self._project.board:
            return
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"BOM projektu:\n{self._bom_text()}\n\n"
            "Dla każdego komponentu podaj numer LCSC (C#####) jeśli znasz. "
            "Format: Reference | Wartość | LCSC Part# | Uwagi.\n"
            "Priorytet: dostępne w magazynie, low-cost.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=lambda _: self._ai_progress.setVisible(False),
            on_error=lambda e: (self._ai_progress.setVisible(False), self._ai_out.append(f"\n⚠ {e}")),
        )

    def _export_csv(self) -> None:
        if not self._project.board:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz raport kosztów", f"{self._project.name}_cost.csv", "CSV (*.csv)"
        )
        if not path:
            return
        rate = CURRENCY_RATES.get(self._currency, 1.0)
        qty = int(self._qty_spin.value())
        sym = self._currency
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Reference", "Value", "Footprint", "Type",
                             f"Unit Price ({sym})", "Qty", f"Total ({sym})"])
            for comp in self._project.board.components:
                p = _estimate_price(comp) * rate
                writer.writerow([
                    comp.reference, comp.value, comp.footprint,
                    comp.component_type, f"{p:.3f}", qty, f"{p*qty:.2f}"
                ])
        QMessageBox.information(self, "Eksport", f"Zapisano: {path}")

    def _export_pdf(self) -> None:
        from src.generators.pdf_generator import PDFGenerator
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz PDF", f"{self._project.name}_cost.pdf", "PDF (*.pdf)"
        )
        if path:
            try:
                PDFGenerator(self._project).export_cost(
                    path, self._currency, int(self._qty_spin.value())
                )
                QMessageBox.information(self, "PDF", f"Zapisano: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Błąd PDF", str(e))
