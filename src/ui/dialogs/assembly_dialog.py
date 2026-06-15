"""Assembly Tracker — interactive BOM checklist for PCB population."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QProgressBar, QComboBox, QCheckBox, QLineEdit,
    QFileDialog, QMessageBox, QTextEdit, QSplitter, QWidget,
    QSpinBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from src.core.project import Project
from src.core.models.component import Component


# ── Assembly state ─────────────────────────────────────────────────────────────

STATES = ["⬜ Brak", "🟡 Pobrane", "🟢 Wlutowane", "✅ Przetestowane", "❌ Pominięte"]
STATE_COLORS = {
    "⬜ Brak":          QColor("#303030"),
    "🟡 Pobrane":       QColor("#4a3a00"),
    "🟢 Wlutowane":     QColor("#1a3a20"),
    "✅ Przetestowane": QColor("#0a3a10"),
    "❌ Pominięte":     QColor("#3a0a0a"),
}


@dataclass
class AssemblyRecord:
    """Tracks the assembly state of one component."""
    reference: str
    value: str
    footprint: str
    component_type: str
    state: str = "⬜ Brak"
    notes: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "reference":      self.reference,
            "value":          self.value,
            "footprint":      self.footprint,
            "component_type": self.component_type,
            "state":          self.state,
            "notes":          self.notes,
            "timestamp":      self.timestamp,
        }

    @staticmethod
    def from_dict(d: dict) -> "AssemblyRecord":
        return AssemblyRecord(
            reference=d.get("reference", ""),
            value=d.get("value", ""),
            footprint=d.get("footprint", ""),
            component_type=d.get("component_type", "generic"),
            state=d.get("state", "⬜ Brak"),
            notes=d.get("notes", ""),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class AssemblySession:
    project_name: str = ""
    records: list[AssemblyRecord] = field(default_factory=list)
    created: str = ""
    updated: str = ""

    def progress(self) -> tuple[int, int, int]:
        """Return (placed, tested, total) counts."""
        total   = len([r for r in self.records if r.state != "❌ Pominięte"])
        placed  = len([r for r in self.records if r.state in ("🟢 Wlutowane", "✅ Przetestowane")])
        tested  = len([r for r in self.records if r.state == "✅ Przetestowane"])
        return placed, tested, total

    def to_json(self) -> str:
        return json.dumps({
            "project_name": self.project_name,
            "created":      self.created,
            "updated":      datetime.now().isoformat(timespec="seconds"),
            "records":      [r.to_dict() for r in self.records],
        }, indent=2, ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> "AssemblySession":
        d = json.loads(text)
        sess = AssemblySession(
            project_name=d.get("project_name", ""),
            created=d.get("created", ""),
            updated=d.get("updated", ""),
        )
        sess.records = [AssemblyRecord.from_dict(r) for r in d.get("records", [])]
        return sess


def _session_from_board(board, project_name: str) -> AssemblySession:
    sess = AssemblySession(
        project_name=project_name,
        created=datetime.now().isoformat(timespec="seconds"),
    )
    for comp in sorted(board.components, key=lambda c: c.reference):
        sess.records.append(AssemblyRecord(
            reference=comp.reference,
            value=comp.value,
            footprint=comp.footprint.split(":")[-1],
            component_type=comp.component_type,
        ))
    return sess


# ── Dialog ─────────────────────────────────────────────────────────────────────

COL_CHECK = 0
COL_REF   = 1
COL_VALUE = 2
COL_TYPE  = 3
COL_FP    = 4
COL_STATE = 5
COL_NOTES = 6


class AssemblyDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._session: AssemblySession | None = None
        self._updating = False
        self.setWindowTitle("Śledzenie montażu (Assembly Tracker)")
        self.resize(1020, 680)
        self._build_ui()
        self._init_session()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = QHBoxLayout()

        btn_load = QPushButton("📂 Wczytaj sesję…")
        btn_load.clicked.connect(self._load_session)
        tb.addWidget(btn_load)

        btn_save = QPushButton("💾 Zapisz sesję…")
        btn_save.clicked.connect(self._save_session)
        tb.addWidget(btn_save)

        tb.addSpacing(8)

        btn_reset = QPushButton("🔄 Resetuj z projektu")
        btn_reset.clicked.connect(self._reset_from_project)
        tb.addWidget(btn_reset)

        tb.addSpacing(12)
        tb.addWidget(QLabel("Filtr:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("ref / wartość / typ…")
        self._filter_edit.setMaximumWidth(160)
        self._filter_edit.textChanged.connect(self._apply_filter)
        tb.addWidget(self._filter_edit)

        tb.addWidget(QLabel("Stan:"))
        self._state_filter = QComboBox()
        self._state_filter.addItem("— Wszystkie —")
        self._state_filter.addItems(STATES)
        self._state_filter.currentTextChanged.connect(self._apply_filter)
        tb.addWidget(self._state_filter)

        tb.addStretch()

        # Bulk action
        tb.addWidget(QLabel("Zaznaczonym:"))
        btn_place_sel = QPushButton("🟢 Wlutowane")
        btn_place_sel.clicked.connect(lambda: self._bulk_set("🟢 Wlutowane"))
        tb.addWidget(btn_place_sel)

        btn_test_sel = QPushButton("✅ Przetestowane")
        btn_test_sel.clicked.connect(lambda: self._bulk_set("✅ Przetestowane"))
        tb.addWidget(btn_test_sel)

        btn_skip_sel = QPushButton("❌ Pomiń")
        btn_skip_sel.clicked.connect(lambda: self._bulk_set("❌ Pominięte"))
        tb.addWidget(btn_skip_sel)

        layout.addLayout(tb)

        # ── Progress bars ──────────────────────────────────────────────────────
        prog_box = QGroupBox("Postęp montażu")
        pl = QHBoxLayout(prog_box)

        pl.addWidget(QLabel("Wlutowane:"))
        self._prog_place = QProgressBar()
        self._prog_place.setStyleSheet("QProgressBar::chunk { background: #2a6a40; }")
        pl.addWidget(self._prog_place, 1)

        pl.addWidget(QLabel("Przetestowane:"))
        self._prog_test = QProgressBar()
        self._prog_test.setStyleSheet("QProgressBar::chunk { background: #1a8a30; }")
        pl.addWidget(self._prog_test, 1)

        self._prog_label = QLabel()
        self._prog_label.setStyleSheet("font-family: Consolas; color: #80c0a0;")
        pl.addWidget(self._prog_label)

        layout.addWidget(prog_box)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "☑", "Referencja", "Wartość", "Typ", "Footprint", "Stan", "Notatki"
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.AnyKeyPressed)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table, 1)

        # ── Summary ───────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        self._summary_lbl = QLabel()
        self._summary_lbl.setStyleSheet("color: #888; font-size: 10px;")
        bottom.addWidget(self._summary_lbl)
        bottom.addStretch()
        btn_export = QPushButton("📋 Eksportuj raport TXT")
        btn_export.clicked.connect(self._export_txt)
        bottom.addWidget(btn_export)
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _init_session(self) -> None:
        board = self._project.board if self._project else None
        if board and board.components:
            name = getattr(self._project, "name", "projekt")
            self._session = _session_from_board(board, name)
            self._populate_table()
        else:
            self._summary_lbl.setText("Brak komponentów — zaimportuj projekt.")

    def _populate_table(self) -> None:
        if not self._session:
            return
        self._updating = True
        self._table.setRowCount(0)
        for rec in self._session.records:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Checkbox column
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self._table.setItem(row, COL_CHECK, chk)

            self._table.setItem(row, COL_REF,   QTableWidgetItem(rec.reference))
            self._table.setItem(row, COL_VALUE,  QTableWidgetItem(rec.value))
            self._table.setItem(row, COL_TYPE,   QTableWidgetItem(rec.component_type))
            self._table.setItem(row, COL_FP,     QTableWidgetItem(rec.footprint))

            state_item = QTableWidgetItem(rec.state)
            state_item.setBackground(QBrush(STATE_COLORS.get(rec.state, QColor("#202020"))))
            self._table.setItem(row, COL_STATE, state_item)

            self._table.setItem(row, COL_NOTES, QTableWidgetItem(rec.notes))

        self._updating = False
        self._update_progress()
        self._apply_filter()

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._updating or not self._session:
            return
        if row >= len(self._session.records):
            return
        rec = self._session.records[row]
        if col == COL_NOTES:
            item = self._table.item(row, col)
            if item:
                rec.notes = item.text()
                rec.timestamp = datetime.now().strftime("%H:%M:%S")
        self._update_progress()

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col != COL_STATE or not self._session or row >= len(self._session.records):
            return
        rec = self._session.records[row]
        cur_idx = STATES.index(rec.state) if rec.state in STATES else 0
        new_state = STATES[(cur_idx + 1) % len(STATES)]
        rec.state = new_state
        rec.timestamp = datetime.now().strftime("%H:%M:%S")

        self._updating = True
        state_item = self._table.item(row, COL_STATE)
        if state_item:
            state_item.setText(new_state)
            state_item.setBackground(QBrush(STATE_COLORS.get(new_state, QColor("#202020"))))
        self._updating = False
        self._update_progress()

    def _bulk_set(self, state: str) -> None:
        if not self._session:
            return
        self._updating = True
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, COL_CHECK)
            if chk and chk.checkState() == Qt.Checked and not self._table.isRowHidden(row):
                if row < len(self._session.records):
                    self._session.records[row].state = state
                    self._session.records[row].timestamp = datetime.now().strftime("%H:%M:%S")
                state_item = self._table.item(row, COL_STATE)
                if state_item:
                    state_item.setText(state)
                    state_item.setBackground(QBrush(STATE_COLORS.get(state, QColor("#202020"))))
        self._updating = False
        self._update_progress()

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().lower()
        state_flt = self._state_filter.currentText()
        show_all = state_flt.startswith("—")

        for row in range(self._table.rowCount()):
            ref   = (self._table.item(row, COL_REF)   or QTableWidgetItem()).text().lower()
            val   = (self._table.item(row, COL_VALUE)  or QTableWidgetItem()).text().lower()
            typ   = (self._table.item(row, COL_TYPE)   or QTableWidgetItem()).text().lower()
            state = (self._table.item(row, COL_STATE)  or QTableWidgetItem()).text()

            ok_query = not query or (query in ref or query in val or query in typ)
            ok_state = show_all or state == state_flt
            self._table.setRowHidden(row, not (ok_query and ok_state))

        self._update_progress()

    def _update_progress(self) -> None:
        if not self._session:
            return
        placed, tested, total = self._session.progress()
        self._prog_place.setMaximum(total)
        self._prog_place.setValue(placed)
        self._prog_test.setMaximum(total)
        self._prog_test.setValue(tested)

        skipped = len([r for r in self._session.records if r.state == "❌ Pominięte"])
        pct = int(100 * placed / total) if total > 0 else 0
        self._prog_label.setText(f"{placed}/{total} ({pct}%)")
        self._summary_lbl.setText(
            f"Łącznie: {len(self._session.records)}  |  "
            f"Wlutowane: {placed}  |  Przetestowane: {tested}  |  "
            f"Pominięte: {skipped}  |  Pozostałe: {total - placed}"
        )

    def _reset_from_project(self) -> None:
        board = self._project.board if self._project else None
        if not board:
            return
        reply = QMessageBox.question(
            self, "Reset",
            "Zresetować sesję montażu z aktualnych komponentów projektu?\n"
            "Wszystkie zaznaczone stany zostaną utracone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._init_session()

    def _save_session(self) -> None:
        if not self._session:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz sesję montażu", "", "JSON (*.json)"
        )
        if path:
            Path(path).write_text(self._session.to_json(), encoding="utf-8")
            QMessageBox.information(self, "Zapisano", f"Sesja zapisana: {path}")

    def _load_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Wczytaj sesję montażu", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self._session = AssemblySession.from_json(text)
            self._populate_table()
        except Exception as e:
            QMessageBox.warning(self, "Błąd", f"Nie można wczytać pliku:\n{e}")

    def _export_txt(self) -> None:
        if not self._session:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj raport", "", "Plik tekstowy (*.txt)"
        )
        if not path:
            return

        placed, tested, total = self._session.progress()
        lines = [
            f"RAPORT MONTAŻU — {self._session.project_name}",
            f"Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Postęp: {placed}/{total} wlutowanych, {tested} przetestowanych",
            "=" * 70,
            "",
        ]

        by_state: dict[str, list[AssemblyRecord]] = {}
        for rec in self._session.records:
            by_state.setdefault(rec.state, []).append(rec)

        for state in STATES:
            recs = by_state.get(state, [])
            if recs:
                lines.append(f"\n{state} ({len(recs)}):")
                lines.append("-" * 40)
                for rec in recs:
                    note_str = f"  [{rec.notes}]" if rec.notes else ""
                    lines.append(f"  {rec.reference:<8} {rec.value:<15} {rec.footprint:<25}{note_str}")

        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Eksport", f"Raport zapisany: {path}")
