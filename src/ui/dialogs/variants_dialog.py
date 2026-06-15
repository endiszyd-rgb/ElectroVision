"""Design Variants Manager — alternate BOM configurations (DNP, substitutions)."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QSplitter, QWidget, QLineEdit, QTextEdit, QComboBox,
    QMessageBox, QFileDialog, QCheckBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from src.core.project import Project
from src.core.models.component import Component


# ── Data model ──────────────────────────────────────────────────────────────────

@dataclass
class ComponentOverride:
    """Per-component override inside a design variant."""
    reference: str
    dnp: bool = False               # Do Not Populate
    alt_value: str = ""             # substitute value (e.g. "4k7" → "10k")
    alt_footprint: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "reference":    self.reference,
            "dnp":          self.dnp,
            "alt_value":    self.alt_value,
            "alt_footprint": self.alt_footprint,
            "notes":        self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "ComponentOverride":
        ov = ComponentOverride(reference=d.get("reference", ""))
        ov.dnp          = d.get("dnp", False)
        ov.alt_value    = d.get("alt_value", "")
        ov.alt_footprint = d.get("alt_footprint", "")
        ov.notes        = d.get("notes", "")
        return ov


@dataclass
class DesignVariant:
    name: str
    description: str = ""
    overrides: list[ComponentOverride] = field(default_factory=list)

    def override_for(self, ref: str) -> ComponentOverride | None:
        for ov in self.overrides:
            if ov.reference == ref:
                return ov
        return None

    def dnp_set(self) -> set[str]:
        return {ov.reference for ov in self.overrides if ov.dnp}

    def effective_bom(self, components: list[Component]) -> list[tuple[Component, ComponentOverride | None]]:
        result = []
        for comp in components:
            ov = self.override_for(comp.reference)
            if ov and ov.dnp:
                continue
            result.append((comp, ov))
        return result

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "description": self.description,
            "overrides":   [ov.to_dict() for ov in self.overrides],
        }

    @staticmethod
    def from_dict(d: dict) -> "DesignVariant":
        v = DesignVariant(name=d.get("name", "Wariant"))
        v.description = d.get("description", "")
        v.overrides   = [ComponentOverride.from_dict(o) for o in d.get("overrides", [])]
        return v


# ── Dialog ──────────────────────────────────────────────────────────────────────

COL_REF  = 0
COL_VAL  = 1
COL_FP   = 2
COL_DNP  = 3
COL_AVAL = 4
COL_AFP  = 5
COL_NOTE = 6


class VariantsDialog(QDialog):
    variant_applied = Signal(str, list)   # (variant_name, dnp_references)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._variants: list[DesignVariant] = [DesignVariant("Produkcyjna")]
        self._sel_var: int = 0
        self.setWindowTitle("Warianty projektu — BOM Variants Manager")
        self.resize(1100, 660)
        self._build_ui()
        self._refresh_variant_list()
        self._load_variant(0)

    # ── UI construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: variant list ─────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        ll.addWidget(QLabel("Warianty:"))

        self._var_list = QTableWidget()
        self._var_list.setColumnCount(2)
        self._var_list.setHorizontalHeaderLabels(["Nazwa", "DNP"])
        self._var_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._var_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._var_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self._var_list.setSelectionBehavior(QTableWidget.SelectRows)
        self._var_list.itemSelectionChanged.connect(self._on_var_selected)
        ll.addWidget(self._var_list, 1)

        var_btns = QHBoxLayout()
        btn_add_var = QPushButton("+ Nowy")
        btn_add_var.clicked.connect(self._add_variant)
        btn_dup_var = QPushButton("⧉ Duplikuj")
        btn_dup_var.clicked.connect(self._dup_variant)
        btn_del_var = QPushButton("− Usuń")
        btn_del_var.clicked.connect(self._del_variant)
        var_btns.addWidget(btn_add_var)
        var_btns.addWidget(btn_dup_var)
        var_btns.addWidget(btn_del_var)
        ll.addLayout(var_btns)

        var_meta = QGroupBox("Właściwości wariantu")
        vm = QVBoxLayout(var_meta)
        self._var_name = QLineEdit()
        self._var_name.setPlaceholderText("Nazwa wariantu")
        self._var_name.textChanged.connect(self._save_variant_meta)
        vm.addWidget(self._var_name)
        self._var_desc = QTextEdit()
        self._var_desc.setPlaceholderText("Opis (cel, platforma, klient...)")
        self._var_desc.setMaximumHeight(80)
        self._var_desc.textChanged.connect(self._save_variant_meta)
        vm.addWidget(self._var_desc)
        ll.addWidget(var_meta)

        splitter.addWidget(left)

        # ── Right: component overrides table ───────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Komponenty w wariancie:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filtruj po ref / wartości...")
        self._filter_edit.textChanged.connect(self._apply_filter)
        top_row.addWidget(self._filter_edit, 1)
        btn_dnp_sel = QPushButton("DNP zaznaczone")
        btn_dnp_sel.clicked.connect(self._dnp_selected)
        top_row.addWidget(btn_dnp_sel)
        btn_restore_sel = QPushButton("Przywróć zaznaczone")
        btn_restore_sel.clicked.connect(self._restore_selected)
        top_row.addWidget(btn_restore_sel)
        rl.addLayout(top_row)

        self._comp_table = QTableWidget()
        self._comp_table.setColumnCount(7)
        self._comp_table.setHorizontalHeaderLabels(
            ["Ref", "Wartość", "Obudowa", "DNP", "Zast. wart.", "Zast. obudowa", "Uwagi"]
        )
        hdr = self._comp_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        self._comp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._comp_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.AnyKeyPressed)
        self._comp_table.cellChanged.connect(self._on_cell_changed)
        rl.addWidget(self._comp_table, 1)

        # Stats bar
        stats_row = QHBoxLayout()
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        stats_row.addWidget(self._stats_lbl)
        stats_row.addStretch()
        self._dnp_lbl = QLabel()
        self._dnp_lbl.setStyleSheet("color: #e08040; font-size: 11px; font-weight: bold;")
        stats_row.addWidget(self._dnp_lbl)
        rl.addLayout(stats_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 720])
        root.addWidget(splitter, 1)

        # ── Bottom ─────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        btn_export = QPushButton("💾 Eksportuj warianty JSON")
        btn_export.clicked.connect(self._export_json)
        bottom.addWidget(btn_export)
        btn_import = QPushButton("📂 Importuj JSON")
        btn_import.clicked.connect(self._import_json)
        bottom.addWidget(btn_import)
        btn_export_bom = QPushButton("📋 Eksportuj BOM wariantu")
        btn_export_bom.clicked.connect(self._export_bom)
        bottom.addWidget(btn_export_bom)
        bottom.addStretch()
        btn_apply = QPushButton("✔ Zastosuj wariant")
        btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 12px;")
        btn_apply.clicked.connect(self._apply_variant)
        bottom.addWidget(btn_apply)
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

        self._loading = False

    # ── Data helpers ─────────────────────────────────────────────────────────────

    def _components(self) -> list[Component]:
        if self._project and self._project.board:
            return self._project.board.components
        return []

    def _current_variant(self) -> DesignVariant | None:
        if 0 <= self._sel_var < len(self._variants):
            return self._variants[self._sel_var]
        return None

    # ── Variant list operations ──────────────────────────────────────────────────

    def _refresh_variant_list(self) -> None:
        self._var_list.setRowCount(0)
        for v in self._variants:
            row = self._var_list.rowCount()
            self._var_list.insertRow(row)
            self._var_list.setItem(row, 0, QTableWidgetItem(v.name))
            dnp_count = len(v.dnp_set())
            item_dnp = QTableWidgetItem(str(dnp_count) if dnp_count else "—")
            item_dnp.setForeground(QColor("#e08040") if dnp_count else QColor("#888"))
            self._var_list.setItem(row, 1, item_dnp)

    def _add_variant(self) -> None:
        v = DesignVariant(name=f"Wariant {len(self._variants) + 1}")
        self._variants.append(v)
        self._refresh_variant_list()
        self._var_list.selectRow(len(self._variants) - 1)

    def _dup_variant(self) -> None:
        v = self._current_variant()
        if not v:
            return
        import copy
        nv = copy.deepcopy(v)
        nv.name = v.name + " (kopia)"
        self._variants.append(nv)
        self._refresh_variant_list()
        self._var_list.selectRow(len(self._variants) - 1)

    def _del_variant(self) -> None:
        if len(self._variants) <= 1:
            QMessageBox.warning(self, "Błąd", "Musi istnieć przynajmniej jeden wariant.")
            return
        idx = self._sel_var
        self._variants.pop(idx)
        self._sel_var = max(0, idx - 1)
        self._refresh_variant_list()
        self._var_list.selectRow(self._sel_var)

    def _on_var_selected(self) -> None:
        rows = self._var_list.selectedItems()
        if not rows:
            return
        idx = self._var_list.currentRow()
        if idx < 0:
            return
        self._sel_var = idx
        self._load_variant(idx)

    def _load_variant(self, idx: int) -> None:
        v = self._variants[idx] if idx < len(self._variants) else None
        if not v:
            return
        self._loading = True
        self._var_name.setText(v.name)
        self._var_desc.setPlainText(v.description)
        self._loading = False
        self._populate_components()

    def _save_variant_meta(self) -> None:
        if self._loading:
            return
        v = self._current_variant()
        if not v:
            return
        v.name = self._var_name.text()
        v.description = self._var_desc.toPlainText()
        self._refresh_variant_list()

    # ── Component table ──────────────────────────────────────────────────────────

    def _populate_components(self) -> None:
        self._loading = True
        v = self._current_variant()
        comps = self._components()
        self._comp_table.setRowCount(0)

        for comp in comps:
            ov = v.override_for(comp.reference) if v else None
            self._add_comp_row(comp, ov)

        self._loading = False
        self._update_stats()

    def _add_comp_row(self, comp: Component, ov: ComponentOverride | None) -> None:
        row = self._comp_table.rowCount()
        self._comp_table.insertRow(row)

        dnp = ov.dnp if ov else False

        ref_item = QTableWidgetItem(comp.reference)
        ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
        self._comp_table.setItem(row, COL_REF, ref_item)

        val_item = QTableWidgetItem(comp.value)
        val_item.setFlags(val_item.flags() & ~Qt.ItemIsEditable)
        self._comp_table.setItem(row, COL_VAL, val_item)

        fp_item = QTableWidgetItem(comp.footprint)
        fp_item.setFlags(fp_item.flags() & ~Qt.ItemIsEditable)
        self._comp_table.setItem(row, COL_FP, fp_item)

        dnp_item = QTableWidgetItem("DNP" if dnp else "")
        dnp_item.setTextAlignment(Qt.AlignCenter)
        if dnp:
            dnp_item.setForeground(QColor("#e05030"))
            dnp_item.setBackground(QColor("#3a2020"))
        self._comp_table.setItem(row, COL_DNP, dnp_item)

        self._comp_table.setItem(row, COL_AVAL, QTableWidgetItem(ov.alt_value if ov else ""))
        self._comp_table.setItem(row, COL_AFP,  QTableWidgetItem(ov.alt_footprint if ov else ""))
        self._comp_table.setItem(row, COL_NOTE, QTableWidgetItem(ov.notes if ov else ""))

        if dnp:
            for col in range(7):
                item = self._comp_table.item(row, col)
                if item:
                    item.setForeground(QColor("#666666"))

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._loading:
            return
        v = self._current_variant()
        comps = self._components()
        if not v or row >= len(comps):
            return

        ref_item = self._comp_table.item(row, COL_REF)
        if not ref_item:
            return
        ref = ref_item.text()
        ov = v.override_for(ref)

        item = self._comp_table.item(row, col)
        text = item.text() if item else ""

        if col == COL_DNP:
            dnp = text.strip().upper() in ("DNP", "X", "1", "TAK", "YES")
            if dnp and not ov:
                ov = ComponentOverride(reference=ref)
                v.overrides.append(ov)
            if ov:
                ov.dnp = dnp
        elif col == COL_AVAL:
            if text and not ov:
                ov = ComponentOverride(reference=ref)
                v.overrides.append(ov)
            if ov:
                ov.alt_value = text
        elif col == COL_AFP:
            if text and not ov:
                ov = ComponentOverride(reference=ref)
                v.overrides.append(ov)
            if ov:
                ov.alt_footprint = text
        elif col == COL_NOTE:
            if text and not ov:
                ov = ComponentOverride(reference=ref)
                v.overrides.append(ov)
            if ov:
                ov.notes = text

        # Cleanup empty overrides
        v.overrides = [o for o in v.overrides
                       if o.dnp or o.alt_value or o.alt_footprint or o.notes]

        self._refresh_variant_list()
        self._update_stats()

    def _update_stats(self) -> None:
        v = self._current_variant()
        comps = self._components()
        if not v:
            return
        dnp_n = len(v.dnp_set())
        total = len(comps)
        populated = total - dnp_n
        self._stats_lbl.setText(f"Łącznie: {total}  |  Montowane: {populated}")
        self._dnp_lbl.setText(f"DNP: {dnp_n}" if dnp_n else "")

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for row in range(self._comp_table.rowCount()):
            ref  = (self._comp_table.item(row, COL_REF) or QTableWidgetItem()).text().lower()
            val  = (self._comp_table.item(row, COL_VAL) or QTableWidgetItem()).text().lower()
            hide = text and text not in ref and text not in val
            self._comp_table.setRowHidden(row, hide)

    def _dnp_selected(self) -> None:
        v = self._current_variant()
        comps = self._components()
        if not v:
            return
        rows = set(item.row() for item in self._comp_table.selectedItems())
        self._loading = True
        for row in rows:
            if row >= len(comps):
                continue
            ref_item = self._comp_table.item(row, COL_REF)
            if not ref_item:
                continue
            ref = ref_item.text()
            ov = v.override_for(ref)
            if not ov:
                ov = ComponentOverride(reference=ref)
                v.overrides.append(ov)
            ov.dnp = True
            dnp_item = self._comp_table.item(row, COL_DNP)
            if dnp_item:
                dnp_item.setText("DNP")
        self._loading = False
        self._populate_components()

    def _restore_selected(self) -> None:
        v = self._current_variant()
        comps = self._components()
        if not v:
            return
        rows = set(item.row() for item in self._comp_table.selectedItems())
        for row in rows:
            if row >= len(comps):
                continue
            ref_item = self._comp_table.item(row, COL_REF)
            if not ref_item:
                continue
            ref = ref_item.text()
            v.overrides = [o for o in v.overrides if o.reference != ref]
        self._populate_components()

    # ── I/O ─────────────────────────────────────────────────────────────────────

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj warianty", "", "JSON (*.json)")
        if path:
            data = [v.to_dict() for v in self._variants]
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importuj warianty", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._variants = [DesignVariant.from_dict(d) for d in data]
            self._refresh_variant_list()
            self._sel_var = 0
            self._var_list.selectRow(0)
            self._load_variant(0)
        except Exception as e:
            QMessageBox.warning(self, "Błąd importu", str(e))

    def _export_bom(self) -> None:
        v = self._current_variant()
        comps = self._components()
        if not v:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj BOM wariantu", "", "CSV (*.csv)")
        if not path:
            return
        lines = ["Reference,Wartość,Obudowa,Status,Zastępcza wartość,Uwagi"]
        for comp in comps:
            ov = v.override_for(comp.reference)
            if ov and ov.dnp:
                status = "DNP"
            else:
                status = "Montowany"
            aval  = ov.alt_value if ov else ""
            notes = ov.notes    if ov else ""
            lines.append(f'"{comp.reference}","{comp.value}","{comp.footprint}","{status}","{aval}","{notes}"')
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Eksport BOM", f"Zapisano {len(lines)-1} komponentów do:\n{path}")

    def _apply_variant(self) -> None:
        v = self._current_variant()
        if not v:
            return
        dnp = list(v.dnp_set())
        self.variant_applied.emit(v.name, dnp)
        self.accept()
