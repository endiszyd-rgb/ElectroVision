"""Dialog autoroutingu PCB — algorytm A*/Lee na siatce 2-warstwowej (F.Cu/B.Cu)."""
from __future__ import annotations
import copy

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFormLayout, QDoubleSpinBox, QSpinBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox, QCheckBox,
    QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

from src.core.project import Project
from src.algorithms.autorouter import autoroute_board, collect_unrouted_nets, AutorouteResult


class _AutorouteThread(QThread):
    done  = Signal(object)   # AutorouteResult
    error = Signal(str)

    def __init__(self, board, cell_mm, trace_width, clearance_mm,
                 via_drill, via_size, max_nets):
        super().__init__()
        self._board = board
        self._cell_mm = cell_mm
        self._trace_width = trace_width
        self._clearance_mm = clearance_mm
        self._via_drill = via_drill
        self._via_size = via_size
        self._max_nets = max_nets

    def run(self):
        try:
            result = autoroute_board(
                self._board, cell_mm=self._cell_mm, trace_width=self._trace_width,
                clearance_mm=self._clearance_mm, via_drill=self._via_drill,
                via_size=self._via_size, max_nets=self._max_nets,
                apply_to_board=False,
            )
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AutorouterDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._board = project.board
        self._result: AutorouteResult | None = None
        self._thread: _AutorouteThread | None = None
        self.setWindowTitle("Auto-routing — automatyczne trasowanie ścieżek")
        self.resize(680, 580)
        self._build_ui()
        self._refresh_unrouted_count()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        info = QLabel(
            "Autorouter przeszukuje siatkę 2-warstwową (F.Cu / B.Cu) algorytmem A* "
            "(odmiana algorytmu Lee), łącząc niepołączone pady tej samej sieci ścieżkami "
            "i przelotkami. Sieci sortowane są od najprostszych. Wynik możesz przeglądnąć "
            "przed zastosowaniem do projektu."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#999; font-size:10px;")
        root.addWidget(info)

        self._unrouted_lbl = QLabel()
        self._unrouted_lbl.setStyleSheet("color:#fc6; font-weight:bold; padding:4px;")
        root.addWidget(self._unrouted_lbl)

        params = QGroupBox("Parametry")
        pf = QFormLayout(params)

        self._cell = QDoubleSpinBox()
        self._cell.setRange(0.1, 2.0); self._cell.setValue(0.5)
        self._cell.setSuffix(" mm"); self._cell.setSingleStep(0.05)
        pf.addRow("Rozmiar komórki siatki:", self._cell)

        self._trace_w = QDoubleSpinBox()
        self._trace_w.setRange(0.1, 5.0); self._trace_w.setValue(0.25)
        self._trace_w.setSuffix(" mm"); self._trace_w.setSingleStep(0.05)
        pf.addRow("Szerokość ścieżki:", self._trace_w)

        self._clearance = QDoubleSpinBox()
        self._clearance.setRange(0.05, 2.0); self._clearance.setValue(0.2)
        self._clearance.setSuffix(" mm"); self._clearance.setSingleStep(0.05)
        pf.addRow("Prześwit (clearance):", self._clearance)

        self._via_drill = QDoubleSpinBox()
        self._via_drill.setRange(0.1, 2.0); self._via_drill.setValue(0.3)
        self._via_drill.setSuffix(" mm"); self._via_drill.setSingleStep(0.05)
        pf.addRow("Wiertło przelotki:", self._via_drill)

        self._via_size = QDoubleSpinBox()
        self._via_size.setRange(0.2, 4.0); self._via_size.setValue(0.6)
        self._via_size.setSuffix(" mm"); self._via_size.setSingleStep(0.05)
        pf.addRow("Średnica przelotki:", self._via_size)

        self._max_nets = QSpinBox()
        self._max_nets.setRange(0, 9999); self._max_nets.setValue(0)
        self._max_nets.setSpecialValueText("Wszystkie")
        pf.addRow("Limit sieci (0 = bez limitu):", self._max_nets)

        root.addWidget(params)

        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("▶ Uruchom autorouting")
        self._btn_run.setStyleSheet("background:#1a4a1a; color:#5f5; font-weight:bold; padding:6px;")
        self._btn_run.clicked.connect(self._run)
        btn_row.addWidget(self._btn_run)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        btn_row.addWidget(self._progress)
        root.addLayout(btn_row)

        # Wyniki
        res_box = QGroupBox("Wynik")
        rl = QVBoxLayout(res_box)
        self._result_lbl = QLabel("Nie uruchomiono jeszcze autoroutingu.")
        self._result_lbl.setWordWrap(True)
        rl.addWidget(self._result_lbl)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Sieć", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        rl.addWidget(self._table, 1)
        root.addWidget(res_box, 1)

        bot = QHBoxLayout()
        self._btn_apply = QPushButton("✔ Zastosuj do projektu")
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._apply)
        bot.addWidget(self._btn_apply)
        bot.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bot.addWidget(btn_close)
        root.addLayout(bot)

    def _refresh_unrouted_count(self) -> None:
        if not self._board:
            self._unrouted_lbl.setText("Brak wczytanej płytki.")
            self._btn_run.setEnabled(False)
            return
        unrouted = collect_unrouted_nets(self._board)
        if unrouted:
            self._unrouted_lbl.setText(
                f"Niepołączone sieci: {len(unrouted)} "
                f"({sum(len(p) for p in unrouted.values())} padów)."
            )
        else:
            self._unrouted_lbl.setText("Wszystkie sieci wydają się być już połączone.")

    # ── Run ───────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        if not self._board:
            return
        self._btn_run.setEnabled(False)
        self._btn_apply.setEnabled(False)
        self._progress.setVisible(True)
        self._table.setRowCount(0)
        self._result_lbl.setText("Trasowanie w toku…")

        max_nets = self._max_nets.value() or None
        self._thread = _AutorouteThread(
            self._board, self._cell.value(), self._trace_w.value(),
            self._clearance.value(), self._via_drill.value(),
            self._via_size.value(), max_nets,
        )
        self._thread.done.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, result: AutorouteResult) -> None:
        self._progress.setVisible(False)
        self._btn_run.setEnabled(True)
        self._result = result
        self._result_lbl.setText(result.summary)
        self._table.setRowCount(0)
        for net in result.nets_routed:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(net))
            ok_item = QTableWidgetItem("✓ Trasowano")
            ok_item.setForeground(QColor("#5f5"))
            self._table.setItem(row, 1, ok_item)
        for net in result.nets_failed:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(net))
            fail_item = QTableWidgetItem("✗ Nie udało się")
            fail_item.setForeground(QColor("#f55"))
            self._table.setItem(row, 1, fail_item)
        self._btn_apply.setEnabled(bool(result.traces_added or result.vias_added))

    def _on_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._btn_run.setEnabled(True)
        QMessageBox.critical(self, "Błąd autoroutingu", msg)

    def _apply(self) -> None:
        if not self._result or not self._board:
            return
        self._board.traces.extend(self._result.traces_added)
        self._board.vias.extend(self._result.vias_added)
        QMessageBox.information(
            self, "Autorouting zastosowany",
            f"Dodano {len(self._result.traces_added)} segmentów ścieżek i "
            f"{len(self._result.vias_added)} przelotek do projektu."
        )
        self._btn_apply.setEnabled(False)
        self._refresh_unrouted_count()
        self.accept()
