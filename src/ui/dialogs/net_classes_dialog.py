"""Net Classes Manager — define routing constraints per net class."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QLineEdit,
    QSplitter, QWidget, QTextEdit, QColorDialog,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from src.core.project import Project


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class NetClass:
    name: str
    description: str = ""
    min_width_mm: float = 0.2
    min_clearance_mm: float = 0.2
    min_via_drill_mm: float = 0.3
    min_via_annular_mm: float = 0.13
    diff_pair_gap_mm: float = 0.2
    diff_pair_skew_mm: float = 0.1
    color: str = "#4080c0"          # display colour for highlight
    nets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name":               self.name,
            "description":        self.description,
            "min_width_mm":       self.min_width_mm,
            "min_clearance_mm":   self.min_clearance_mm,
            "min_via_drill_mm":   self.min_via_drill_mm,
            "min_via_annular_mm": self.min_via_annular_mm,
            "diff_pair_gap_mm":   self.diff_pair_gap_mm,
            "diff_pair_skew_mm":  self.diff_pair_skew_mm,
            "color":              self.color,
            "nets":               self.nets,
        }

    @staticmethod
    def from_dict(d: dict) -> "NetClass":
        nc = NetClass(name=d.get("name", "Nowa klasa"))
        nc.description        = d.get("description", "")
        nc.min_width_mm       = d.get("min_width_mm", 0.2)
        nc.min_clearance_mm   = d.get("min_clearance_mm", 0.2)
        nc.min_via_drill_mm   = d.get("min_via_drill_mm", 0.3)
        nc.min_via_annular_mm = d.get("min_via_annular_mm", 0.13)
        nc.diff_pair_gap_mm   = d.get("diff_pair_gap_mm", 0.2)
        nc.diff_pair_skew_mm  = d.get("diff_pair_skew_mm", 0.1)
        nc.color              = d.get("color", "#4080c0")
        nc.nets               = d.get("nets", [])
        return nc


# Built-in presets
BUILTIN_CLASSES: list[NetClass] = [
    NetClass(
        name="Default",
        description="Klasa domyślna — wszystkie sieci nieprzypisane",
        min_width_mm=0.2,
        min_clearance_mm=0.2,
        color="#607080",
    ),
    NetClass(
        name="Power",
        description="Szyny zasilania — szersze ścieżki",
        min_width_mm=0.5,
        min_clearance_mm=0.3,
        min_via_drill_mm=0.4,
        color="#a04020",
        nets=["VCC", "GND", "3.3V", "5V", "12V", "VBUS"],
    ),
    NetClass(
        name="HighSpeed",
        description="Sygnały szybkie (>50 MHz) — wąskie ścieżki, małe przelotkii",
        min_width_mm=0.1,
        min_clearance_mm=0.15,
        min_via_drill_mm=0.2,
        diff_pair_gap_mm=0.15,
        diff_pair_skew_mm=0.05,
        color="#20a060",
    ),
    NetClass(
        name="DiffPair",
        description="Pary różnicowe USB/LVDS/MIPI — 3W rule",
        min_width_mm=0.15,
        min_clearance_mm=0.3,
        diff_pair_gap_mm=0.2,
        diff_pair_skew_mm=0.025,
        color="#6040c0",
    ),
    NetClass(
        name="RF",
        description="Sygnały RF — impedancja 50Ω, minimalne wiercenia",
        min_width_mm=0.1,
        min_clearance_mm=0.4,
        min_via_drill_mm=0.15,
        color="#c08020",
    ),
    NetClass(
        name="Analog",
        description="Sygnały analogowe — izolacja od zasilania i cyfrowych",
        min_width_mm=0.15,
        min_clearance_mm=0.25,
        color="#4080a0",
    ),
]


# ── Dialog ─────────────────────────────────────────────────────────────────────

COL_NAME  = 0
COL_DESC  = 1
COL_WIDTH = 2
COL_CLR   = 3
COL_NETS  = 4
COL_COLOR = 5


class NetClassesDialog(QDialog):
    classes_changed = Signal(list)    # list[NetClass]

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._classes: list[NetClass] = [nc for nc in BUILTIN_CLASSES]
        self._sel_idx: int = -1
        self.setWindowTitle("Klasy sieci — zarządzanie regułami trasowania")
        self.resize(1000, 620)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: class list ───────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        ll.addWidget(QLabel("Klasy sieci:"))

        self._class_table = QTableWidget()
        self._class_table.setColumnCount(4)
        self._class_table.setHorizontalHeaderLabels(
            ["Nazwa", "Min. szer. (mm)", "Czysto. (mm)", "Sieci"]
        )
        self._class_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._class_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._class_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._class_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._class_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._class_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._class_table.itemSelectionChanged.connect(self._on_class_selected)
        ll.addWidget(self._class_table, 1)

        btns = QHBoxLayout()
        btn_add = QPushButton("+ Dodaj")
        btn_add.clicked.connect(self._add_class)
        btn_del = QPushButton("− Usuń")
        btn_del.clicked.connect(self._del_class)
        btn_preset = QPushButton("⚡ Wczytaj presety")
        btn_preset.clicked.connect(self._load_presets)
        btns.addWidget(btn_add)
        btns.addWidget(btn_del)
        btns.addWidget(btn_preset)
        ll.addLayout(btns)

        splitter.addWidget(left)

        # ── Right: class editor ────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        rl.addWidget(QLabel("Właściwości klasy:"))

        form = QGroupBox()
        ff = QFormLayout(form)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._save_current)
        ff.addRow("Nazwa:", self._name_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.textChanged.connect(self._save_current)
        ff.addRow("Opis:", self._desc_edit)

        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(0.05, 5.0)
        self._width_spin.setSuffix(" mm")
        self._width_spin.setSingleStep(0.025)
        self._width_spin.valueChanged.connect(self._save_current)
        ff.addRow("Min. szerokość ścieżki:", self._width_spin)

        self._clr_spin = QDoubleSpinBox()
        self._clr_spin.setRange(0.05, 5.0)
        self._clr_spin.setSuffix(" mm")
        self._clr_spin.setSingleStep(0.025)
        self._clr_spin.valueChanged.connect(self._save_current)
        ff.addRow("Min. prześwit:", self._clr_spin)

        self._via_spin = QDoubleSpinBox()
        self._via_spin.setRange(0.1, 3.0)
        self._via_spin.setSuffix(" mm")
        self._via_spin.setSingleStep(0.05)
        self._via_spin.valueChanged.connect(self._save_current)
        ff.addRow("Min. wiercenie przelotki:", self._via_spin)

        self._ann_spin = QDoubleSpinBox()
        self._ann_spin.setRange(0.05, 2.0)
        self._ann_spin.setSuffix(" mm")
        self._ann_spin.setSingleStep(0.025)
        self._ann_spin.valueChanged.connect(self._save_current)
        ff.addRow("Min. pierścień przelotki:", self._ann_spin)

        self._dp_gap_spin = QDoubleSpinBox()
        self._dp_gap_spin.setRange(0.05, 2.0)
        self._dp_gap_spin.setSuffix(" mm")
        self._dp_gap_spin.valueChanged.connect(self._save_current)
        ff.addRow("Gap pary różnicowej:", self._dp_gap_spin)

        self._dp_skew_spin = QDoubleSpinBox()
        self._dp_skew_spin.setRange(0.001, 5.0)
        self._dp_skew_spin.setSuffix(" mm")
        self._dp_skew_spin.valueChanged.connect(self._save_current)
        ff.addRow("Max skew pary diff.:", self._dp_skew_spin)

        # Color picker
        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(40, 24)
        self._color_btn.clicked.connect(self._pick_color)
        self._color_label = QLabel("#4080c0")
        color_row.addWidget(self._color_btn)
        color_row.addWidget(self._color_label)
        color_row.addStretch()
        ff.addRow("Kolor podświetlenia:", color_row)

        rl.addWidget(form)

        # Net assignment
        net_box = QGroupBox("Przypisane sieci")
        nl = QVBoxLayout(net_box)

        net_tb = QHBoxLayout()
        self._net_edit = QLineEdit()
        self._net_edit.setPlaceholderText("np. SDA, MOSI, USB_D+")
        btn_add_net = QPushButton("+ Dodaj")
        btn_add_net.clicked.connect(self._add_net)
        btn_rm_net = QPushButton("− Usuń")
        btn_rm_net.clicked.connect(self._rm_net)
        net_tb.addWidget(self._net_edit, 1)
        net_tb.addWidget(btn_add_net)
        net_tb.addWidget(btn_rm_net)
        nl.addLayout(net_tb)

        self._nets_table = QTableWidget()
        self._nets_table.setColumnCount(1)
        self._nets_table.setHorizontalHeaderLabels(["Sieć"])
        self._nets_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._nets_table.setEditTriggers(QTableWidget.NoEditTriggers)
        nl.addWidget(self._nets_table)

        # Quick-assign from board nets
        btn_auto = QPushButton("🔍 Auto-przypisz z projektu (wzorzec)")
        btn_auto.clicked.connect(self._auto_assign)
        nl.addWidget(btn_auto)

        rl.addWidget(net_box, 1)

        splitter.addWidget(right)
        splitter.setSizes([340, 560])
        layout.addWidget(splitter, 1)

        # ── Bottom ─────────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        btn_export = QPushButton("💾 Eksportuj JSON")
        btn_export.clicked.connect(self._export_json)
        bottom.addWidget(btn_export)
        btn_import = QPushButton("📂 Importuj JSON")
        btn_import.clicked.connect(self._import_json)
        bottom.addWidget(btn_import)
        bottom.addStretch()
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet("color: #888; font-size: 10px;")
        bottom.addWidget(self._stats_lbl)
        bottom.addStretch()
        btn_apply = QPushButton("✔ Zastosuj")
        btn_apply.setStyleSheet("background: #1a4a8f; color: white; padding: 4px 10px;")
        btn_apply.clicked.connect(self._apply)
        bottom.addWidget(btn_apply)
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        self._editing = False

    def _populate(self) -> None:
        self._class_table.setRowCount(0)
        for nc in self._classes:
            row = self._class_table.rowCount()
            self._class_table.insertRow(row)
            item_name = QTableWidgetItem(nc.name)
            item_name.setForeground(QColor(nc.color))
            self._class_table.setItem(row, 0, item_name)
            self._class_table.setItem(row, 1, QTableWidgetItem(f"{nc.min_width_mm:.3f}"))
            self._class_table.setItem(row, 2, QTableWidgetItem(f"{nc.min_clearance_mm:.3f}"))
            self._class_table.setItem(row, 3, QTableWidgetItem(", ".join(nc.nets[:5])))

        total_nets = sum(len(nc.nets) for nc in self._classes)
        self._stats_lbl.setText(
            f"Klas: {len(self._classes)}  |  Przypisanych sieci: {total_nets}"
        )

    def _on_class_selected(self) -> None:
        rows = self._class_table.selectedItems()
        if not rows:
            return
        idx = self._class_table.currentRow()
        if idx < 0 or idx >= len(self._classes):
            return
        self._sel_idx = idx
        self._load_class(self._classes[idx])

    def _load_class(self, nc: NetClass) -> None:
        self._editing = True
        self._name_edit.setText(nc.name)
        self._desc_edit.setText(nc.description)
        self._width_spin.setValue(nc.min_width_mm)
        self._clr_spin.setValue(nc.min_clearance_mm)
        self._via_spin.setValue(nc.min_via_drill_mm)
        self._ann_spin.setValue(nc.min_via_annular_mm)
        self._dp_gap_spin.setValue(nc.diff_pair_gap_mm)
        self._dp_skew_spin.setValue(nc.diff_pair_skew_mm)
        self._color_label.setText(nc.color)
        self._color_btn.setStyleSheet(f"background: {nc.color};")

        self._nets_table.setRowCount(0)
        for net in nc.nets:
            row = self._nets_table.rowCount()
            self._nets_table.insertRow(row)
            self._nets_table.setItem(row, 0, QTableWidgetItem(net))

        self._editing = False

    def _save_current(self) -> None:
        if self._editing or self._sel_idx < 0 or self._sel_idx >= len(self._classes):
            return
        nc = self._classes[self._sel_idx]
        nc.name               = self._name_edit.text()
        nc.description        = self._desc_edit.text()
        nc.min_width_mm       = self._width_spin.value()
        nc.min_clearance_mm   = self._clr_spin.value()
        nc.min_via_drill_mm   = self._via_spin.value()
        nc.min_via_annular_mm = self._ann_spin.value()
        nc.diff_pair_gap_mm   = self._dp_gap_spin.value()
        nc.diff_pair_skew_mm  = self._dp_skew_spin.value()
        # refresh table row
        row = self._sel_idx
        item = self._class_table.item(row, 0)
        if item:
            item.setText(nc.name)
            item.setForeground(QColor(nc.color))
        self._populate()

    def _pick_color(self) -> None:
        if self._sel_idx < 0:
            return
        nc = self._classes[self._sel_idx]
        color = QColorDialog.getColor(QColor(nc.color), self)
        if color.isValid():
            nc.color = color.name()
            self._color_label.setText(nc.color)
            self._color_btn.setStyleSheet(f"background: {nc.color};")
            self._populate()

    def _add_class(self) -> None:
        nc = NetClass(name=f"Klasa{len(self._classes) + 1}")
        self._classes.append(nc)
        self._populate()
        self._class_table.selectRow(len(self._classes) - 1)

    def _del_class(self) -> None:
        idx = self._sel_idx
        if idx < 0 or idx >= len(self._classes):
            return
        if self._classes[idx].name == "Default":
            QMessageBox.warning(self, "Błąd", "Klasy 'Default' nie można usunąć.")
            return
        self._classes.pop(idx)
        self._sel_idx = -1
        self._populate()

    def _load_presets(self) -> None:
        self._classes = [nc for nc in BUILTIN_CLASSES]
        self._populate()
        self._class_table.selectRow(0)

    def _add_net(self) -> None:
        if self._sel_idx < 0:
            return
        net = self._net_edit.text().strip()
        if not net:
            return
        nc = self._classes[self._sel_idx]
        if net not in nc.nets:
            nc.nets.append(net)
            row = self._nets_table.rowCount()
            self._nets_table.insertRow(row)
            self._nets_table.setItem(row, 0, QTableWidgetItem(net))
        self._net_edit.clear()
        self._populate()

    def _rm_net(self) -> None:
        if self._sel_idx < 0:
            return
        row = self._nets_table.currentRow()
        if row < 0:
            return
        item = self._nets_table.item(row, 0)
        if item:
            nc = self._classes[self._sel_idx]
            nc.nets = [n for n in nc.nets if n != item.text()]
            self._nets_table.removeRow(row)
        self._populate()

    def _auto_assign(self) -> None:
        """Suggest nets from the board that match a prefix typed in _net_edit."""
        board = self._project.board if self._project else None
        if not board or self._sel_idx < 0:
            return
        pattern = self._net_edit.text().strip().upper()
        nc = self._classes[self._sel_idx]
        board_nets = {pad.net_name for comp in board.components
                      for pad in comp.pads if pad.net_name}
        matched = [n for n in sorted(board_nets)
                   if not pattern or pattern in n.upper()]
        added = 0
        for net in matched[:20]:
            if net not in nc.nets:
                nc.nets.append(net)
                row = self._nets_table.rowCount()
                self._nets_table.insertRow(row)
                self._nets_table.setItem(row, 0, QTableWidgetItem(net))
                added += 1
        self._populate()
        QMessageBox.information(self, "Auto-przypisanie",
                                f"Dodano {added} sieci z projektu do klasy '{nc.name}'.")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj klasy sieci", "", "JSON (*.json)")
        if path:
            data = [nc.to_dict() for nc in self._classes]
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importuj klasy sieci", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._classes = [NetClass.from_dict(d) for d in data]
            self._populate()
            self._class_table.selectRow(0)
        except Exception as e:
            QMessageBox.warning(self, "Błąd", f"Nie można wczytać: {e}")

    def _apply(self) -> None:
        self.classes_changed.emit(self._classes)
        self.accept()
