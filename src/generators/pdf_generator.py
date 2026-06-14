"""PDF documentation generator using Qt's built-in QPrinter."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime

from PySide6.QtGui import (
    QPainter, QFont, QColor, QPageSize, QPageLayout,
    QTextDocument, QTextCursor, QTextCharFormat, QTextBlockFormat,
)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QMarginsF, QSizeF
from PySide6.QtPrintSupport import QPrinter

from src.core.project import Project
from src.core.models.component import Component


_CSS = """
body { font-family: Arial, sans-serif; font-size: 10pt; color: #111; }
h1   { font-size: 18pt; color: #1a4a8f; border-bottom: 2px solid #1a4a8f; padding-bottom: 4px; }
h2   { font-size: 13pt; color: #2a6abf; margin-top: 16px; border-bottom: 1px solid #ccc; }
h3   { font-size: 11pt; color: #444; }
table{ border-collapse: collapse; width: 100%; margin: 8px 0; }
th   { background: #1a4a8f; color: white; padding: 4px 8px; text-align: left; font-size: 9pt; }
td   { border: 1px solid #ccc; padding: 3px 6px; font-size: 9pt; }
tr:nth-child(even) td { background: #f0f4fa; }
.info { color: #555; font-size: 9pt; }
.total{ font-size: 12pt; font-weight: bold; color: #1a4a8f; }
.warn { color: #c04000; }
.ok   { color: #008000; }
"""

CURRENCY_RATES = {"USD": 1.0, "PLN": 4.02, "EUR": 0.92}
CURRENCY_SYM   = {"USD": "$", "PLN": "zł", "EUR": "€"}


def _estimate_price(comp: Component) -> float:
    from src.ui.panels.cost_panel import _estimate_price as _ep
    return _ep(comp)


class PDFGenerator:
    def __init__(self, project: Project):
        self._project = project

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _printer(self, path: str) -> QPrinter:
        pr = QPrinter(QPrinter.HighResolution)
        pr.setOutputFormat(QPrinter.PdfFormat)
        pr.setOutputFileName(path)
        pr.setPageSize(QPageSize(QPageSize.A4))
        pr.setPageLayout(QPageLayout(
            QPageSize(QPageSize.A4),
            QPageLayout.Portrait,
            QMarginsF(15, 15, 15, 15),
            QPageLayout.Millimeter,
        ))
        return pr

    def _doc(self) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultStyleSheet(_CSS)
        doc.setPageSize(QSizeF(794, 1123))  # A4 @ 96dpi
        return doc

    def _header(self, name: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        proj = self._project
        board = proj.board
        dims = ""
        if board:
            dims = f"{board.width_mm:.1f} × {board.height_mm:.1f} mm"
        return (
            f"<h1>ElectroVision — {name}</h1>"
            f"<p class='info'>"
            f"Projekt: <b>{proj.name}</b> &nbsp;|&nbsp; "
            f"Data: {ts} &nbsp;|&nbsp; "
            + (f"Wymiary płytki: <b>{dims}</b>" if dims else "")
            + f"</p><hr/>"
        )

    # ── BOM PDF ───────────────────────────────────────────────────────────────

    def export_bom(self, path: str) -> None:
        board = self._project.board
        if not board:
            raise ValueError("Brak projektu PCB")

        rows = ""
        for i, c in enumerate(board.components):
            fp = c.footprint.split(":")[-1] if ":" in c.footprint else c.footprint
            rows += (
                f"<tr><td>{i+1}</td><td><b>{c.reference}</b></td>"
                f"<td>{c.value}</td><td>{fp}</td>"
                f"<td>{c.component_type}</td>"
                f"<td>{c.manufacturer or '—'}</td>"
                f"<td>{c.manufacturer_pn or '—'}</td></tr>\n"
            )

        html = (
            self._header("Bill of Materials")
            + f"<h2>Lista komponentów ({len(board.components)} szt.)</h2>"
            + "<table><tr>"
            + "<th>#</th><th>Reference</th><th>Wartość</th><th>Footprint</th>"
            + "<th>Typ</th><th>Producent</th><th>Part#</th>"
            + f"</tr>{rows}</table>"
            + f"<p class='info'>Płytka: {board.width_mm:.1f}×{board.height_mm:.1f} mm, "
            + f"warstwy: {len(board.layers)}, sieci: {len(board.nets)}</p>"
        )

        doc = self._doc()
        doc.setHtml(html)
        pr = self._printer(path)
        doc.print_(pr)

    # ── Cost PDF ──────────────────────────────────────────────────────────────

    def export_cost(self, path: str, currency: str = "USD", qty: int = 1) -> None:
        board = self._project.board
        if not board:
            raise ValueError("Brak projektu PCB")

        rate = CURRENCY_RATES.get(currency, 1.0)
        sym  = CURRENCY_SYM.get(currency, "$")

        rows = ""
        total = 0.0
        for c in board.components:
            p = _estimate_price(c) * rate
            total += p
            fp = c.footprint.split(":")[-1] if ":" in c.footprint else c.footprint
            rows += (
                f"<tr><td><b>{c.reference}</b></td><td>{c.value}</td>"
                f"<td>{fp}</td><td>{sym}{p:.3f}</td>"
                f"<td>{qty}</td><td><b>{sym}{p*qty:.2f}</b></td></tr>\n"
            )

        html = (
            self._header("Raport kosztów")
            + f"<h2>Kosztorys projektu — {currency}, partia: {qty} szt.</h2>"
            + "<table><tr>"
            + "<th>Reference</th><th>Wartość</th><th>Footprint</th>"
            + f"<th>Cena jedn. ({currency})</th><th>Ilość</th><th>Suma</th>"
            + f"</tr>{rows}</table>"
            + f"<p class='total'>Łączny koszt komponentów (1 szt.): {sym}{total:.2f} &nbsp;|&nbsp; "
            + f"Partia {qty} szt.: {sym}{total*qty:.2f}</p>"
            + f"<p class='info'>Ceny szacunkowe na podstawie bazy LCSC (styczeń 2025). "
            + f"Przelicznik: 1 USD = {rate:.2f} {currency}.</p>"
        )

        doc = self._doc()
        doc.setHtml(html)
        pr = self._printer(path)
        doc.print_(pr)

    # ── Full project report ───────────────────────────────────────────────────

    def export_full_report(self, path: str) -> None:
        board = self._project.board
        if not board:
            raise ValueError("Brak projektu PCB")

        # BOM table
        bom_rows = ""
        total_price = 0.0
        for c in board.components:
            p = _estimate_price(c)
            total_price += p
            fp = c.footprint.split(":")[-1] if ":" in c.footprint else c.footprint
            bom_rows += (
                f"<tr><td><b>{c.reference}</b></td><td>{c.value}</td>"
                f"<td>{fp}</td><td>{c.component_type}</td>"
                f"<td>${p:.2f}</td></tr>\n"
            )

        # Layer table
        layer_rows = "".join(
            f"<tr><td>{l.name}</td><td>{l.layer_type}</td></tr>"
            for l in board.layers
        )

        # Nets table
        net_rows = "".join(
            f"<tr><td>{n.name}</td><td>{n.number}</td></tr>"
            for n in board.nets[:30]
        )
        if len(board.nets) > 30:
            net_rows += f"<tr><td colspan='2'><i>... i {len(board.nets)-30} więcej</i></td></tr>"

        html = (
            self._header("Raport Projektu")

            + "<h2>📐 Informacje o płytce</h2>"
            + "<table>"
            + f"<tr><th>Parametr</th><th>Wartość</th></tr>"
            + f"<tr><td>Tytuł</td><td>{board.title or self._project.name}</td></tr>"
            + f"<tr><td>Wymiary</td><td>{board.width_mm:.2f} × {board.height_mm:.2f} mm</td></tr>"
            + f"<tr><td>Liczba komponentów</td><td>{len(board.components)}</td></tr>"
            + f"<tr><td>Liczba ścieżek</td><td>{len(board.traces)}</td></tr>"
            + f"<tr><td>Przelotki</td><td>{len(board.vias)}</td></tr>"
            + f"<tr><td>Sieci</td><td>{len(board.nets)}</td></tr>"
            + f"<tr><td>Warstwy</td><td>{len(board.layers)}</td></tr>"
            + "</table>"

            + "<h2>📋 Bill of Materials</h2>"
            + "<table><tr><th>Reference</th><th>Wartość</th><th>Footprint</th>"
            + f"<th>Typ</th><th>Cena est.</th></tr>{bom_rows}</table>"
            + f"<p class='total'>Szacunkowy koszt komponentów: <b>${total_price:.2f} USD</b></p>"

            + "<h2>🔌 Warstwy PCB</h2>"
            + f"<table><tr><th>Warstwa</th><th>Typ</th></tr>{layer_rows}</table>"

            + "<h2>🌐 Sieci elektryczne (pierwsze 30)</h2>"
            + f"<table><tr><th>Nazwa sieci</th><th>Nr</th></tr>{net_rows}</table>"

            + "<h2>ℹ️ Uwagi</h2>"
            + "<p>Raport wygenerowany automatycznie przez ElectroVision. "
            + "Ceny komponentów są szacunkowe i mogą się różnić od aktualnych cen rynkowych.</p>"
        )

        doc = self._doc()
        doc.setHtml(html)
        pr = self._printer(path)
        doc.print_(pr)
