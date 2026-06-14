"""Net Inspector panel — highlight nets, show connected components, net statistics."""
from __future__ import annotations
import math
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QProgressBar, QTabWidget, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard
from src.ai.bridge import AIBridge


class NetInspectorPanel(QWidget):
    net_highlight_requested = Signal(str)  # net name → PCB viewer can highlight

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._ai = AIBridge.instance()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Search ────────────────────────────────────────────────────────────
        top = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtruj sieci…")
        self._search.textChanged.connect(self._filter_nets)
        top.addWidget(self._search, 1)
        btn_refresh = QPushButton("🔄 Odśwież")
        btn_refresh.clicked.connect(self._rebuild)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: net tree ────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Sieci elektryczne")
        lbl.setStyleSheet("font-weight: bold; color: #4a90d9; font-size: 10px;")
        ll.addWidget(lbl)

        self._net_tree = QTreeWidget()
        self._net_tree.setHeaderLabels(["Sieć", "Połączenia", "Długość"])
        self._net_tree.setColumnWidth(0, 140)
        self._net_tree.setColumnWidth(1, 60)
        self._net_tree.setAlternatingRowColors(True)
        self._net_tree.setStyleSheet(
            "QTreeWidget { background: #0d1117; border: 1px solid #2a2a3a; }"
            "QTreeWidget::item:selected { background: #1a4a8f; }"
            "QTreeWidget::item:alternate { background: #131820; }"
        )
        self._net_tree.currentItemChanged.connect(self._on_net_select)
        ll.addWidget(self._net_tree, 1)

        self._stats_label = QLabel("—")
        self._stats_label.setStyleSheet("color: #888; font-size: 9px;")
        ll.addWidget(self._stats_label)
        splitter.addWidget(left)

        # ── Right: details ────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 1: connected components
        comp_tab = QWidget()
        cl = QVBoxLayout(comp_tab)
        cl.setContentsMargins(4, 4, 4, 4)
        self._comp_list = QListWidget()
        self._comp_list.setFont(QFont("Consolas", 9))
        self._comp_list.setStyleSheet("background: #0d1117;")
        cl.addWidget(QLabel("Komponenty w sieci:"))
        cl.addWidget(self._comp_list, 1)
        tabs.addTab(comp_tab, "Komponenty")

        # Tab 2: traces
        trace_tab = QWidget()
        tl = QVBoxLayout(trace_tab)
        tl.setContentsMargins(4, 4, 4, 4)
        self._trace_list = QListWidget()
        self._trace_list.setFont(QFont("Consolas", 8))
        self._trace_list.setStyleSheet("background: #0d1117;")
        tl.addWidget(QLabel("Ścieżki w sieci:"))
        tl.addWidget(self._trace_list, 1)
        tabs.addTab(trace_tab, "Ścieżki")

        # Tab 3: AI analysis
        ai_tab = QWidget()
        al = QVBoxLayout(ai_tab)
        al.setContentsMargins(4, 4, 4, 4)

        btn_row = QHBoxLayout()
        btn_analyze = QPushButton("🤖 Analizuj sieć")
        btn_analyze.clicked.connect(self._ai_analyze_net)
        btn_row.addWidget(btn_analyze)

        btn_all = QPushButton("Analizuj wszystkie sieci")
        btn_all.clicked.connect(self._ai_analyze_all)
        btn_row.addWidget(btn_all)
        al.addLayout(btn_row)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(5)
        al.addWidget(self._ai_progress)

        self._ai_out = QTextEdit()
        self._ai_out.setReadOnly(True)
        self._ai_out.setFont(QFont("Consolas", 9))
        self._ai_out.setPlaceholderText("Wybierz sieć i kliknij Analizuj…")
        al.addWidget(self._ai_out, 1)
        tabs.addTab(ai_tab, "🤖 AI")

        rl.addWidget(tabs)
        splitter.addWidget(right)
        splitter.setSizes([280, 400])
        layout.addWidget(splitter)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._rebuild()

    def _rebuild(self) -> None:
        board = self._project.board
        self._net_tree.clear()
        if not board:
            self._stats_label.setText("Brak projektu")
            return

        # Build net → traces mapping
        net_traces: dict[str, list] = {}
        for t in board.traces:
            nn = t.net_name or "(brak sieci)"
            net_traces.setdefault(nn, []).append(t)

        # Build net → pads mapping
        net_pads: dict[str, list] = {}
        for comp in board.components:
            for p in comp.pads:
                nn = p.net_name or "(brak sieci)"
                net_pads.setdefault(nn, []).append((comp.reference, p.number))

        # Create tree items
        # Power nets first
        power_kw = ("VCC", "VDD", "GND", "3V3", "5V", "12V", "3.3V", "VBUS", "VBAT")
        power_nets = []
        signal_nets = []
        for n in board.nets:
            nn = n.name
            if any(kw in nn.upper() for kw in power_kw):
                power_nets.append(nn)
            else:
                signal_nets.append(nn)

        # Also include unnamed nets from traces
        all_known = {n.name for n in board.nets}
        for nn in net_traces:
            if nn not in all_known and nn != "(brak sieci)":
                signal_nets.append(nn)

        cat_power  = QTreeWidgetItem(["⚡ Zasilanie",   str(len(power_nets)),  ""])
        cat_signal = QTreeWidgetItem(["〰 Sygnały",     str(len(signal_nets)), ""])
        cat_noname = QTreeWidgetItem(["— Brak nazwy", "", ""])

        for cat_item, net_list in [(cat_power, power_nets), (cat_signal, signal_nets)]:
            cat_item.setExpanded(True)
            cat_item.setFont(0, QFont("Arial", 9, QFont.Bold))
            for nn in sorted(net_list):
                traces  = net_traces.get(nn, [])
                pads    = net_pads.get(nn, [])
                length  = sum(math.hypot(t.x2-t.x1, t.y2-t.y1) for t in traces)
                child   = QTreeWidgetItem([
                    nn,
                    str(len(pads)),
                    f"{length:.1f}mm" if length > 0 else "—",
                ])
                child.setData(0, Qt.UserRole, nn)
                # Color by type
                if any(kw in nn.upper() for kw in ("GND", "AGND", "PGND")):
                    child.setForeground(0, QBrush(QColor("#60a0e0")))
                elif any(kw in nn.upper() for kw in ("VCC", "VDD", "3V3", "5V", "VBUS")):
                    child.setForeground(0, QBrush(QColor("#e06060")))
                else:
                    child.setForeground(0, QBrush(QColor("#c0c0c0")))
                cat_item.addChild(child)
            self._net_tree.addTopLevelItem(cat_item)

        # Unnamed traces
        unnamed = net_traces.get("(brak sieci)", [])
        if unnamed:
            cat_noname.setData(0, Qt.UserRole, "(brak sieci)")
            cat_noname.setForeground(0, QBrush(QColor("#666")))
            self._net_tree.addTopLevelItem(cat_noname)

        total_nets = len(power_nets) + len(signal_nets)
        total_len  = sum(
            math.hypot(t.x2-t.x1, t.y2-t.y1) for t in board.traces
        )
        self._stats_label.setText(
            f"Sieci: {total_nets}  |  "
            f"Zasilanie: {len(power_nets)}  |  "
            f"Łączna dł. ścieżek: {total_len:.0f}mm"
        )

    def _filter_nets(self, text: str) -> None:
        text = text.lower()
        for i in range(self._net_tree.topLevelItemCount()):
            cat = self._net_tree.topLevelItem(i)
            any_vis = False
            for j in range(cat.childCount()):
                child = cat.child(j)
                show = not text or text in child.text(0).lower()
                child.setHidden(not show)
                if show:
                    any_vis = True
            cat.setHidden(not any_vis and bool(text))

    def _on_net_select(self, current: QTreeWidgetItem, _prev) -> None:
        if not current:
            return
        nn = current.data(0, Qt.UserRole)
        if not nn:
            return

        board = self._project.board
        if not board:
            return

        self.net_highlight_requested.emit(nn)

        # Populate component list
        self._comp_list.clear()
        for comp in board.components:
            nets_in_comp = {p.net_name for p in comp.pads if p.net_name == nn}
            if nets_in_comp:
                pads_on_net = [p.number for p in comp.pads if p.net_name == nn]
                item = QListWidgetItem(
                    f"{comp.reference}  ({comp.value})  piny: {', '.join(pads_on_net)}"
                )
                item.setForeground(QBrush(QColor("#e8c060")))
                self._comp_list.addItem(item)

        # Populate trace list
        self._trace_list.clear()
        for i, t in enumerate(board.traces):
            if t.net_name == nn:
                length = math.hypot(t.x2-t.x1, t.y2-t.y1)
                item = QListWidgetItem(
                    f"[{t.layer}] ({t.x1:.2f},{t.y1:.2f})→({t.x2:.2f},{t.y2:.2f})  "
                    f"W={t.width:.2f}mm  L={length:.2f}mm"
                )
                item.setForeground(QBrush(QColor("#a0c0e0")))
                self._trace_list.addItem(item)

    def _current_net(self) -> Optional[str]:
        item = self._net_tree.currentItem()
        if item:
            return item.data(0, Qt.UserRole)
        return None

    def _ai_analyze_net(self) -> None:
        nn = self._current_net()
        if not nn or not self._project.board:
            self._ai_out.setPlainText("Wybierz sieć z listy.")
            return
        board = self._project.board
        comps_on_net = [
            f"{c.reference}({c.value})"
            for c in board.components
            for p in c.pads if p.net_name == nn
        ]
        traces = [t for t in board.traces if t.net_name == nn]
        total_len = sum(math.hypot(t.x2-t.x1, t.y2-t.y1) for t in traces)

        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"Przeanalizuj sieć elektryczną '{nn}' w projekcie PCB.\n"
            f"Komponenty podłączone: {', '.join(comps_on_net[:20])}\n"
            f"Ścieżki: {len(traces)}, łączna długość: {total_len:.1f}mm\n\n"
            f"Odpowiedz na:\n"
            f"1. Jaka jest rola tej sieci w układzie?\n"
            f"2. Czy wymaga kontrolowanej impedancji?\n"
            f"3. Czy długość ścieżek jest odpowiednia?\n"
            f"4. Zalecenia dotyczące trasowania (szerokość, topologia).\n"
            f"5. Potencjalne problemy EMI/SI.",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=lambda _: self._ai_progress.setVisible(False),
            on_error=lambda e: (self._ai_progress.setVisible(False),
                                self._ai_out.append(f"\n⚠ {e}")),
        )

    def _ai_analyze_all(self) -> None:
        board = self._project.board
        if not board:
            return
        power = [n.name for n in board.nets if any(
            k in n.name.upper() for k in ("VCC","VDD","GND","3V3","5V")
        )]
        signals = [n.name for n in board.nets if n.name not in power][:15]
        self._ai_out.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"Dokonaj przeglądu sieci elektrycznych projektu PCB '{self._project.name}':\n"
            f"Sieci zasilania: {', '.join(power)}\n"
            f"Sieci sygnałowe (pierwsze 15): {', '.join(signals)}\n"
            f"Łączna liczba sieci: {len(board.nets)}\n\n"
            f"Zidentyfikuj:\n"
            f"1. Sieci krytyczne wymagające uwagi\n"
            f"2. Brakujące sieci (np. brak RESET, BOOT, NRST)\n"
            f"3. Sieci z potencjalnym problemem EMI\n"
            f"4. Zalecenia dotyczące grupowania sygnałów\n"
            f"5. Priorytet trasowania sieci",
            system_key="pcb_system",
            on_chunk=self._ai_out.insertPlainText,
            on_done=lambda _: self._ai_progress.setVisible(False),
            on_error=lambda e: (self._ai_progress.setVisible(False),
                                self._ai_out.append(f"\n⚠ {e}")),
        )
