"""PCB Editor panel — toolbar, component library, properties, editor canvas."""
from __future__ import annotations
import copy
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QSplitter, QComboBox, QDoubleSpinBox, QFormLayout,
    QListWidget, QListWidgetItem, QTextEdit, QToolButton, QButtonGroup,
    QLineEdit, QMessageBox, QToolBar, QSizePolicy, QScrollArea,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QFrame, QSpinBox,
    QAbstractItemView
)
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QFont, QColor, QIcon, QKeySequence, QAction
from PySide6.QtWidgets import QShortcut

from src.core.project import Project
from src.core.models.component import Component
from src.core.models.pcb_board import PCBBoard
from src.ui.widgets.pcb_editor import PCBEditor, EditorMode


# ── Component library data ────────────────────────────────────────────────────
_COMP_LIBRARY: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("Rezystory", "R", [
        ("R", "10k",  "Resistor_SMD:R_0402_1005Metric"),
        ("R", "4k7",  "Resistor_SMD:R_0402_1005Metric"),
        ("R", "1k",   "Resistor_SMD:R_0402_1005Metric"),
        ("R", "100R", "Resistor_SMD:R_0402_1005Metric"),
        ("R", "0R",   "Resistor_SMD:R_0402_1005Metric"),
        ("R", "10k",  "Resistor_SMD:R_0603_1608Metric"),
        ("R", "1k",   "Resistor_SMD:R_0603_1608Metric"),
        ("R", "10k",  "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"),
    ]),
    ("Kondensatory", "C", [
        ("C", "100nF", "Capacitor_SMD:C_0402_1005Metric"),
        ("C", "1uF",   "Capacitor_SMD:C_0402_1005Metric"),
        ("C", "10uF",  "Capacitor_SMD:C_0805_2012Metric"),
        ("C", "100uF", "Capacitor_SMD:C_1206_3216Metric"),
        ("C", "22pF",  "Capacitor_SMD:C_0402_1005Metric"),
        ("C", "10nF",  "Capacitor_SMD:C_0402_1005Metric"),
        ("C", "100uF_25V", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"),
    ]),
    ("LED", "LED", [
        ("LED", "RED",   "LED_SMD:LED_0402_1005Metric"),
        ("LED", "GREEN", "LED_SMD:LED_0402_1005Metric"),
        ("LED", "BLUE",  "LED_SMD:LED_0402_1005Metric"),
        ("LED", "WHITE", "LED_SMD:LED_0603_1608Metric"),
        ("D",   "1N4148","Diode_SMD:D_SOD-123"),
        ("D",   "SS34",  "Diode_SMD:D_SMB"),
    ]),
    ("Złącza", "J", [
        ("J", "Conn_1x02", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"),
        ("J", "Conn_1x03", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"),
        ("J", "Conn_1x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"),
        ("J", "USB_C",     "Connector_USB:USB_C_Receptacle_GCT_USB4085"),
        ("J", "USB_Micro", "Connector_USB:USB_Micro-B_Molex-105017-0001"),
        ("J", "DC_Jack",   "Connector_BarrelJack:BarrelJack_Horizontal"),
        ("J", "JST_PH_2",  "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical"),
    ]),
    ("ICs / MCU", "U", [
        ("U", "ESP32-WROOM-32D", "RF_Module:ESP32-WROOM-32"),
        ("U", "RP2040",          "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm"),
        ("U", "STM32F103C8T6",   "Package_QFP:LQFP-48_7x7mm_P0.5mm"),
        ("U", "AMS1117-3V3",     "Package_TO_SOT_SMD:SOT-223-3_TabPin2"),
        ("U", "CP2102",          "Package_SO:SOIC-28"),
        ("U", "BME280",          "Package_LGA:Bosch_LGA-8_2.5x2.5mm"),
        ("U", "SSD1306",         "Package_SO:SOIC-16"),
        ("U", "NE555",           "Package_DIP:DIP-8_W7.62mm"),
    ]),
    ("Tranzystory", "Q", [
        ("Q", "2N2222", "Package_TO_SOT_THT:TO-92_Inline"),
        ("Q", "BC547",  "Package_TO_SOT_THT:TO-92_Inline"),
        ("Q", "IRF540", "Package_TO_SOT_THT:TO-220-3_Vertical"),
        ("Q", "IRLZ44N","Package_TO_SOT_THT:TO-220-3_Vertical"),
        ("Q", "BSS138", "Package_TO_SOT_SMD:SOT-23"),
    ]),
    ("Kryształy", "Y", [
        ("Y", "8MHz",   "Crystal:Crystal_HC49-U_Vertical"),
        ("Y", "16MHz",  "Crystal:Crystal_HC49-U_Vertical"),
        ("Y", "12MHz",  "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm"),
        ("Y", "32768Hz","Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm"),
    ]),
    ("Przyciski", "SW", [
        ("SW", "RESET",  "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal_Wuerth_450301014042"),
        ("SW", "BOOT",   "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal_Wuerth_450301014042"),
        ("SW", "User",   "Button_Switch_THT:SW_Tactile_SPST_Angled_PTS645"),
        ("SW", "SPST",   "Button_Switch_THT:SW_Slide-03_P2.54mm"),
    ]),
]


class PCBEditorPanel(QWidget):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor must be created before toolbar (toolbar connects to its signals)
        self._editor = PCBEditor()

        # ── Toolbar ───────────────────────────────────────────────────────────
        layout.addWidget(self._build_toolbar())

        # ── Main splitter ─────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: library
        splitter.addWidget(self._build_library())
        splitter.setStretchFactor(0, 0)

        # Center: editor
        editor_container = QWidget()
        ec_layout = QVBoxLayout(editor_container)
        ec_layout.setContentsMargins(2, 2, 2, 2)

        self._editor.component_selected.connect(self._on_comp_selected)
        self._editor.board_modified.connect(self._on_board_modified)
        self._editor.status_message.connect(self._show_status)
        self._editor.undo_state_changed.connect(self._on_undo_state)
        ec_layout.addWidget(self._editor, 1)

        # Ctrl+F — focus find tab
        sc_find = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_find.activated.connect(self._focus_find)

        self._status_bar = QLabel("Gotowy  |  S=Wybierz  R=Trasuj  V=Przelotka  X=Usuń  Z=Strefa  N=Ratsnest  Space=Obróć  M=Lustro  F=Dopasuj  Enter=Zamknij strefę  Ctrl+Z/Y=Cofnij/Ponów")
        self._status_bar.setStyleSheet(
            "background: #0d1117; color: #666; font-size: 9px; "
            "font-family: Consolas; padding: 2px 6px;"
        )
        ec_layout.addWidget(self._status_bar)
        splitter.addWidget(editor_container)
        splitter.setStretchFactor(1, 1)

        # Right: properties
        splitter.addWidget(self._build_properties())
        splitter.setStretchFactor(2, 0)

        splitter.setSizes([200, 800, 260])
        layout.addWidget(splitter, 1)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setStyleSheet(
            "QToolBar { background: #161b22; border-bottom: 1px solid #2a2a3a; spacing: 3px; }"
            "QPushButton { min-width: 80px; padding: 3px 8px; }"
        )

        # Mode buttons
        self._btn_select = self._mode_btn("⬚ Wybierz (S)", EditorMode.SELECT, checked=True)
        self._btn_route  = self._mode_btn("〰 Trasuj (R)",  EditorMode.ROUTE)
        self._btn_via    = self._mode_btn("⊙ Przelotka (V)", EditorMode.VIA)
        self._btn_delete = self._mode_btn("✕ Usuń (X)",   EditorMode.DELETE)
        self._btn_zone   = self._mode_btn("⬡ Strefa (Z)", EditorMode.ZONE)

        self._mode_group = QButtonGroup(self)
        for btn in [self._btn_select, self._btn_route, self._btn_via, self._btn_delete, self._btn_zone]:
            btn.setCheckable(True)
            self._mode_group.addButton(btn)
            tb.addWidget(btn)
        self._btn_select.setChecked(True)

        tb.addSeparator()

        # Undo / Redo
        self._btn_undo = QPushButton("↩ Cofnij")
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._editor.undo)
        self._btn_undo.setShortcut(QKeySequence("Ctrl+Z"))
        tb.addWidget(self._btn_undo)

        self._btn_redo = QPushButton("↪ Ponów")
        self._btn_redo.setEnabled(False)
        self._btn_redo.clicked.connect(self._editor.redo)
        self._btn_redo.setShortcut(QKeySequence("Ctrl+Y"))
        tb.addWidget(self._btn_redo)

        tb.addSeparator()

        # Layer
        tb.addWidget(QLabel("  Warstwa:"))
        self._layer_combo = QComboBox()
        self._layer_combo.addItems([
            "F.Cu", "B.Cu", "In1.Cu", "In2.Cu",
            "F.SilkS", "B.SilkS", "F.Mask", "B.Mask",
        ])
        self._layer_combo.setMinimumWidth(90)
        self._layer_combo.currentTextChanged.connect(self._editor.set_active_layer)
        tb.addWidget(self._layer_combo)

        # Trace width
        tb.addWidget(QLabel("  Ścieżka:"))
        self._trace_w_combo = QComboBox()
        self._trace_w_combo.addItems(["0.10", "0.15", "0.20", "0.25", "0.30",
                                       "0.40", "0.50", "0.80", "1.00", "1.50", "2.00"])
        self._trace_w_combo.setCurrentText("0.25")
        self._trace_w_combo.setEditable(True)
        self._trace_w_combo.setMinimumWidth(65)
        self._trace_w_combo.currentTextChanged.connect(self._on_trace_w_change)
        tb.addWidget(self._trace_w_combo)
        tb.addWidget(QLabel("mm  "))

        # Grid
        tb.addWidget(QLabel("Siatka:"))
        self._grid_combo = QComboBox()
        self._grid_combo.addItems(["0.10", "0.25", "0.50", "0.635", "1.00",
                                    "1.27", "2.00", "2.54"])
        self._grid_combo.setCurrentText("1.27")
        self._grid_combo.setMinimumWidth(65)
        self._grid_combo.currentTextChanged.connect(self._on_grid_change)
        tb.addWidget(self._grid_combo)
        tb.addWidget(QLabel("mm"))

        tb.addSeparator()

        btn_fit = QPushButton("⊡ Dopasuj (F)")
        btn_fit.clicked.connect(self._editor.fit_view)
        tb.addWidget(btn_fit)

        btn_delete_sel = QPushButton("🗑 Usuń wybrane")
        btn_delete_sel.clicked.connect(self._editor.delete_selected)
        btn_delete_sel.setShortcut(QKeySequence("Delete"))
        tb.addWidget(btn_delete_sel)

        tb.addSeparator()

        btn_rot90 = QPushButton("↻ Obróć 90° (Space)")
        btn_rot90.clicked.connect(lambda: self._editor._rotate_selected(90.0))
        tb.addWidget(btn_rot90)

        btn_mirror = QPushButton("⇌ Lustro (M)")
        btn_mirror.clicked.connect(self._editor._mirror_selected)
        tb.addWidget(btn_mirror)

        tb.addSeparator()

        btn_align_l = QPushButton("⊢ Lewo")
        btn_align_l.setToolTip("Wyrównaj do lewej krawędzi wybranego")
        btn_align_l.clicked.connect(lambda: self._editor.align_selected("left"))
        tb.addWidget(btn_align_l)

        btn_align_ch = QPushButton("⊥ Centrum H")
        btn_align_ch.setToolTip("Wyrównaj centra w poziomie")
        btn_align_ch.clicked.connect(lambda: self._editor.align_selected("center_h"))
        tb.addWidget(btn_align_ch)

        btn_align_t = QPushButton("⊤ Góra")
        btn_align_t.setToolTip("Wyrównaj do górnej krawędzi wybranego")
        btn_align_t.clicked.connect(lambda: self._editor.align_selected("top"))
        tb.addWidget(btn_align_t)

        btn_dist_h = QPushButton("↔ Roz. H")
        btn_dist_h.setToolTip("Rozmieść równomiernie w poziomie")
        btn_dist_h.clicked.connect(self._editor.distribute_h)
        tb.addWidget(btn_dist_h)

        btn_dist_v = QPushButton("↕ Roz. V")
        btn_dist_v.setToolTip("Rozmieść równomiernie w pionie")
        btn_dist_v.clicked.connect(self._editor.distribute_v)
        tb.addWidget(btn_dist_v)

        tb.addSeparator()

        # Zone net selector
        tb.addWidget(QLabel("  Sieć strefy:"))
        self._zone_net_combo = QComboBox()
        self._zone_net_combo.addItem("GND")
        self._zone_net_combo.setMinimumWidth(80)
        self._zone_net_combo.setEditable(True)
        self._zone_net_combo.currentTextChanged.connect(
            lambda t: self._editor.set_zone_net(t)
        )
        tb.addWidget(self._zone_net_combo)

        self._btn_ratsnest = QPushButton("⋯ Ratsnest (N)")
        self._btn_ratsnest.setCheckable(True)
        self._btn_ratsnest.setChecked(True)
        self._btn_ratsnest.setToolTip("Pokaż/ukryj niezarastrowane połączenia (N)")
        self._btn_ratsnest.clicked.connect(
            lambda checked: self._editor.toggle_ratsnest(checked)
        )
        tb.addWidget(self._btn_ratsnest)

        tb.addSeparator()

        btn_export = QPushButton("💾 Eksportuj .kicad_pcb")
        btn_export.clicked.connect(self._export_kicad)
        btn_export.setStyleSheet("QPushButton { background: #1a4a1a; }")
        tb.addWidget(btn_export)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self._modified_label = QLabel("")
        self._modified_label.setStyleSheet("color: #fa4; font-size: 10px;")
        tb.addWidget(self._modified_label)

        return tb

    def _mode_btn(self, label: str, mode: EditorMode, checked: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setStyleSheet(
            "QPushButton:checked { background: #1a4a8f; color: white; font-weight: bold; }"
            "QPushButton { padding: 4px 10px; }"
        )
        btn.clicked.connect(lambda: self._editor.set_mode(mode))
        return btn

    # ── Component library ─────────────────────────────────────────────────────

    def _build_library(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(185)
        w.setMaximumWidth(220)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        lbl = QLabel("📦 Biblioteka komponentów")
        lbl.setStyleSheet("font-weight: bold; color: #4a90d9; font-size: 10px;")
        layout.addWidget(lbl)

        self._lib_search = QLineEdit()
        self._lib_search.setPlaceholderText("Szukaj…")
        self._lib_search.textChanged.connect(self._filter_library)
        layout.addWidget(self._lib_search)

        self._lib_tree = QTreeWidget()
        self._lib_tree.setHeaderHidden(True)
        self._lib_tree.setIndentation(12)
        self._lib_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #2a2a3a; background: #0d1117; }"
            "QTreeWidget::item { padding: 2px; }"
            "QTreeWidget::item:selected { background: #1a4a8f; }"
        )
        self._lib_tree.itemDoubleClicked.connect(self._on_lib_double_click)

        for cat_name, prefix, items in _COMP_LIBRARY:
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setForeground(0, QColor("#4a90d9"))
            cat_item.setFont(0, QFont("Arial", 9, QFont.Bold))
            for ref, val, fp in items:
                fp_short = fp.split(":")[-1] if ":" in fp else fp
                child = QTreeWidgetItem([f"{ref} — {val}  ({fp_short})"])
                child.setData(0, Qt.UserRole, (ref, val, fp))
                child.setForeground(0, QColor("#c0c0c0"))
                child.setFont(0, QFont("Consolas", 8))
                cat_item.addChild(child)
            self._lib_tree.addTopLevelItem(cat_item)

        self._lib_tree.expandAll()
        layout.addWidget(self._lib_tree, 1)

        btn_place = QPushButton("➕ Umieść na płytce")
        btn_place.clicked.connect(self._place_from_library)
        btn_place.setStyleSheet("QPushButton { background: #1a4a1a; }")
        layout.addWidget(btn_place)

        hint = QLabel("Dwuklik = umieść\nEsc = anuluj umieszczanie")
        hint.setStyleSheet("color: #555; font-size: 8px;")
        layout.addWidget(hint)
        return w

    def _filter_library(self, text: str) -> None:
        text = text.lower()
        for i in range(self._lib_tree.topLevelItemCount()):
            cat = self._lib_tree.topLevelItem(i)
            any_visible = False
            for j in range(cat.childCount()):
                child = cat.child(j)
                show = not text or text in child.text(0).lower()
                child.setHidden(not show)
                if show:
                    any_visible = True
            cat.setHidden(not any_visible)

    def _on_lib_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.UserRole)
        if data:
            self._start_place(*data)

    def _place_from_library(self) -> None:
        item = self._lib_tree.currentItem()
        if item:
            data = item.data(0, Qt.UserRole)
            if data:
                self._start_place(*data)

    def _start_place(self, ref: str, val: str, fp: str) -> None:
        if not self._project.board:
            QMessageBox.warning(self, "Brak projektu",
                                "Najpierw załaduj projekt PCB lub wybierz szablon.")
            return
        comp = Component(reference=ref, value=val, footprint=fp, x=0, y=0)
        self._editor.set_pending_component(comp)
        # Update mode buttons
        for btn in [self._btn_select, self._btn_route, self._btn_via, self._btn_delete]:
            btn.setChecked(False)
        self._show_status(f"Umieszczanie: {ref} ({val}) — kliknij na płytce, Esc = anuluj")

    # ── Properties panel ──────────────────────────────────────────────────────

    def _build_properties(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(240)
        w.setMaximumWidth(290)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 1: selected component
        comp_tab = QWidget()
        comp_layout = QVBoxLayout(comp_tab)

        comp_box = QGroupBox("Wybrany komponent")
        form = QFormLayout(comp_box)
        form.setLabelAlignment(Qt.AlignRight)

        self._prop_ref  = QLineEdit(); self._prop_ref.returnPressed.connect(self._apply_props)
        self._prop_val  = QLineEdit(); self._prop_val.returnPressed.connect(self._apply_props)
        self._prop_fp   = QLineEdit(); self._prop_fp.returnPressed.connect(self._apply_props)
        self._prop_x    = QDoubleSpinBox(); self._prop_x.setRange(-1000, 1000); self._prop_x.setDecimals(3)
        self._prop_y    = QDoubleSpinBox(); self._prop_y.setRange(-1000, 1000); self._prop_y.setDecimals(3)
        self._prop_rot  = QDoubleSpinBox(); self._prop_rot.setRange(-360, 360); self._prop_rot.setDecimals(1)
        self._prop_layer = QComboBox()
        self._prop_layer.addItems(["F.Cu", "B.Cu"])

        form.addRow("Reference:",  self._prop_ref)
        form.addRow("Wartość:",    self._prop_val)
        form.addRow("Footprint:",  self._prop_fp)
        form.addRow("X (mm):",     self._prop_x)
        form.addRow("Y (mm):",     self._prop_y)
        form.addRow("Obrót (°):",  self._prop_rot)
        form.addRow("Warstwa:",    self._prop_layer)

        btn_apply = QPushButton("✓ Zastosuj zmiany")
        btn_apply.clicked.connect(self._apply_props)
        btn_apply.setStyleSheet("background: #1a4a8f; color: white;")
        form.addRow(btn_apply)
        comp_layout.addWidget(comp_box)

        self._prop_desc = QTextEdit()
        self._prop_desc.setReadOnly(True)
        self._prop_desc.setMaximumHeight(120)
        self._prop_desc.setFont(QFont("Consolas", 8))
        self._prop_desc.setPlaceholderText("Kliknij komponent na płytce…")
        comp_layout.addWidget(self._prop_desc)
        comp_layout.addStretch()
        tabs.addTab(comp_tab, "Właściwości")

        # Tab 2: via params
        via_tab = QWidget()
        via_layout = QVBoxLayout(via_tab)
        via_box = QGroupBox("Parametry przelotki")
        vf = QFormLayout(via_box)
        self._via_drill = QDoubleSpinBox()
        self._via_drill.setRange(0.1, 5.0); self._via_drill.setValue(0.4)
        self._via_drill.setSuffix(" mm"); self._via_drill.setSingleStep(0.05)
        self._via_size = QDoubleSpinBox()
        self._via_size.setRange(0.3, 8.0); self._via_size.setValue(0.8)
        self._via_size.setSuffix(" mm"); self._via_size.setSingleStep(0.05)
        self._via_drill.valueChanged.connect(self._update_via)
        self._via_size.valueChanged.connect(self._update_via)
        vf.addRow("Wiertło:", self._via_drill)
        vf.addRow("Średnica:", self._via_size)
        via_layout.addWidget(via_box)
        via_layout.addStretch()
        tabs.addTab(via_tab, "Przelotka")

        # Tab 3: board stats
        stat_tab = QWidget()
        stat_layout = QVBoxLayout(stat_tab)
        self._stat_label = QLabel("—")
        self._stat_label.setWordWrap(True)
        self._stat_label.setTextFormat(Qt.RichText)
        self._stat_label.setAlignment(Qt.AlignTop)
        stat_layout.addWidget(self._stat_label)
        stat_layout.addStretch()
        tabs.addTab(stat_tab, "Statystyki")

        # Tab 4: layer visibility
        tabs.addTab(self._build_layer_tab(), "Warstwy")

        # Tab 5: find component
        tabs.addTab(self._build_find_tab(), "Szukaj")

        layout.addWidget(tabs)
        return w

    def _build_layer_tab(self) -> QWidget:
        from src.ui.widgets.pcb_editor import _LAYER_COLORS
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        lbl = QLabel("Widocznosc warstw:")
        lbl.setStyleSheet("font-weight:bold; color:#4a90d9; font-size:10px;")
        lay.addWidget(lbl)

        self._layer_checks: dict[str, QCheckBox] = {}
        for layer, color_hex in _LAYER_COLORS.items():
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)

            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(
                f"background:{color_hex}; border-radius:2px; border:1px solid #444;"
            )
            rl.addWidget(dot)

            cb = QCheckBox(layer)
            cb.setChecked(True)
            cb.setFont(QFont("Consolas", 8))
            layer_name = layer
            cb.toggled.connect(
                lambda checked, ln=layer_name: self._editor.set_layer_visible(ln, checked)
            )
            self._layer_checks[layer] = cb
            rl.addWidget(cb)
            rl.addStretch()
            lay.addWidget(row)

        lay.addSpacing(6)
        row_btns = QHBoxLayout()
        btn_all = QPushButton("Wszystkie")
        btn_all.setFixedHeight(22)
        btn_all.clicked.connect(self._layers_show_all)
        btn_cu = QPushButton("Tylko Cu")
        btn_cu.setFixedHeight(22)
        btn_cu.clicked.connect(self._layers_only_cu)
        row_btns.addWidget(btn_all)
        row_btns.addWidget(btn_cu)
        lay.addLayout(row_btns)
        lay.addStretch()
        return w

    def _layers_show_all(self) -> None:
        for layer, cb in self._layer_checks.items():
            cb.setChecked(True)

    def _layers_only_cu(self) -> None:
        for layer, cb in self._layer_checks.items():
            cb.setChecked("Cu" in layer or layer == "Edge.Cuts")

    def _build_find_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel("Znajdz komponent (Ctrl+F):")
        lbl.setStyleSheet("font-weight:bold; color:#4a90d9; font-size:10px;")
        lay.addWidget(lbl)

        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("np. U1, R3, C12")
        self._find_edit.returnPressed.connect(self._do_find)
        lay.addWidget(self._find_edit)

        btn_find = QPushButton("Znajdz i centruj")
        btn_find.clicked.connect(self._do_find)
        btn_find.setStyleSheet("background:#1a4a8f; color:white;")
        lay.addWidget(btn_find)

        self._find_result = QLabel("")
        self._find_result.setWordWrap(True)
        self._find_result.setStyleSheet("font-size:9px; color:#aaa;")
        lay.addWidget(self._find_result)

        lay.addSpacing(8)
        lbl2 = QLabel("Lista komponentow:")
        lbl2.setStyleSheet("color:#666; font-size:9px;")
        lay.addWidget(lbl2)

        from PySide6.QtWidgets import QListWidget
        self._comp_list = QListWidget()
        self._comp_list.setFont(QFont("Consolas", 8))
        self._comp_list.setStyleSheet(
            "QListWidget { background:#0d1117; border:1px solid #2a2a3a; }"
            "QListWidget::item:selected { background:#1a4a8f; }"
        )
        self._comp_list.itemDoubleClicked.connect(
            lambda item: self._do_find_text(item.text().split()[0])
        )
        lay.addWidget(self._comp_list, 1)
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._editor.set_board(project.board)
        self._update_stats()
        self._populate_zone_nets()
        self._populate_comp_list()

    def _populate_comp_list(self) -> None:
        self._comp_list.clear()
        board = self._project.board
        if not board:
            return
        for c in sorted(board.components, key=lambda x: x.reference):
            self._comp_list.addItem(f"{c.reference}  {c.value}")

    def _focus_find(self) -> None:
        # Switch properties tab to "Szukaj" and focus the input
        prop_widget = self._find_edit.parent()
        tabs = prop_widget.parent()
        if hasattr(tabs, 'indexOf'):
            idx = tabs.indexOf(prop_widget)
            if idx >= 0:
                tabs.setCurrentIndex(idx)
        self._find_edit.setFocus()
        self._find_edit.selectAll()

    def _do_find(self) -> None:
        self._do_find_text(self._find_edit.text())

    def _do_find_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        found = self._editor.find_component(text)
        if found:
            self._find_result.setText(f"Znaleziono: {text}")
            self._find_result.setStyleSheet("font-size:9px; color:#4caf50;")
        else:
            self._find_result.setText(f"Nie znaleziono: {text}")
            self._find_result.setStyleSheet("font-size:9px; color:#f44336;")

    def _populate_zone_nets(self) -> None:
        board = self._project.board
        self._zone_net_combo.blockSignals(True)
        current = self._zone_net_combo.currentText()
        self._zone_net_combo.clear()
        if board:
            for net in board.nets:
                self._zone_net_combo.addItem(net.name)
        if not self._zone_net_combo.count():
            self._zone_net_combo.addItem("GND")
        idx = self._zone_net_combo.findText(current)
        self._zone_net_combo.setCurrentIndex(max(0, idx))
        self._zone_net_combo.blockSignals(False)
        self._editor.set_zone_net(self._zone_net_combo.currentText())

    def _on_comp_selected(self, comp: Optional[Component]) -> None:
        if comp:
            self._prop_ref.setText(comp.reference)
            self._prop_val.setText(comp.value)
            self._prop_fp.setText(comp.footprint)
            self._prop_x.setValue(comp.x)
            self._prop_y.setValue(comp.y)
            self._prop_rot.setValue(comp.rotation)
            idx = self._prop_layer.findText(comp.layer)
            if idx >= 0:
                self._prop_layer.setCurrentIndex(idx)
            pad_info = "\n".join(
                f"Pad {p.number}: {p.net_name or '—'}" for p in comp.pads[:8]
            )
            self._prop_desc.setPlainText(
                f"Typ: {comp.component_type}\n"
                f"Opis: {comp.description or '—'}\n"
                f"Pady ({len(comp.pads)}):\n{pad_info}"
            )
        else:
            self._prop_desc.setPlaceholderText("Kliknij komponent na płytce…")
            self._prop_desc.clear()

    def _apply_props(self) -> None:
        comp = self._editor._sel_comp
        if not comp:
            return
        old = (comp.reference, comp.value, comp.footprint,
               comp.x, comp.y, comp.rotation, comp.layer)
        comp.reference = self._prop_ref.text()
        comp.value     = self._prop_val.text()
        comp.footprint = self._prop_fp.text()
        comp.x         = self._prop_x.value()
        comp.y         = self._prop_y.value()
        comp.rotation  = self._prop_rot.value()
        comp.layer     = self._prop_layer.currentText()
        self._editor.board_modified.emit()
        self._editor.update()
        self._show_status(f"Właściwości {comp.reference} zaktualizowane")

    def _update_via(self) -> None:
        self._editor.set_via_params(self._via_drill.value(), self._via_size.value())

    def _on_board_modified(self) -> None:
        self._modified_label.setText("● Niezapisane zmiany")
        self._update_stats()

    def _on_trace_w_change(self, text: str) -> None:
        try:
            self._editor.set_trace_width(float(text))
        except ValueError:
            pass

    def _on_grid_change(self, text: str) -> None:
        try:
            self._editor.set_grid(float(text))
        except ValueError:
            pass

    def _on_undo_state(self, can_undo: bool, can_redo: bool) -> None:
        self._btn_undo.setEnabled(can_undo)
        self._btn_redo.setEnabled(can_redo)

    def _show_status(self, msg: str) -> None:
        self._status_bar.setText(msg)

    def _update_stats(self) -> None:
        board = self._project.board
        if not board:
            self._stat_label.setText("—")
            return
        self._stat_label.setText(
            f"<b>Wymiary:</b> {board.width_mm:.2f}×{board.height_mm:.2f} mm<br>"
            f"<b>Komponenty:</b> {len(board.components)}<br>"
            f"<b>Ścieżki:</b> {len(board.traces)}<br>"
            f"<b>Przelotki:</b> {len(board.vias)}<br>"
            f"<b>Sieci:</b> {len(board.nets)}<br>"
            f"<b>Strefy Cu:</b> {len(board.zones)}<br>"
            f"<b>Warstwy:</b> {len(board.layers)}"
        )

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_kicad(self) -> None:
        board = self._project.board
        if not board:
            QMessageBox.warning(self, "Brak projektu", "Załaduj projekt PCB.")
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj KiCad PCB", f"{self._project.name}.kicad_pcb",
            "KiCad PCB (*.kicad_pcb)"
        )
        if not path:
            return
        try:
            from src.generators.kicad_generator import KiCadGenerator
            bb = board.bounding_box
            data = {
                "title": board.title or self._project.name,
                "board_width": board.width_mm,
                "board_height": board.height_mm,
                "components": [
                    {
                        "reference": c.reference,
                        "value": c.value,
                        "footprint": c.footprint,
                        "x": c.x - bb[0],
                        "y": c.y - bb[1],
                        "rotation": c.rotation,
                        "layer": c.layer,
                        "pads": [
                            {"number": p.number, "type": p.pad_type,
                             "shape": p.shape, "x": p.x, "y": p.y,
                             "width": p.width, "height": p.height,
                             "net": p.net_name}
                            for p in c.pads
                        ],
                    }
                    for c in board.components
                ],
                "traces": [
                    {"x1": t.x1-bb[0], "y1": t.y1-bb[1],
                     "x2": t.x2-bb[0], "y2": t.y2-bb[1],
                     "width": t.width, "layer": t.layer, "net": t.net_name}
                    for t in board.traces
                ],
                "vias": [
                    {"x": v.x-bb[0], "y": v.y-bb[1],
                     "drill": v.drill, "size": v.size, "net": v.net_name}
                    for v in board.vias
                ],
            }
            gen = KiCadGenerator(data)
            gen.generate(path)
            self._modified_label.setText("")
            QMessageBox.information(self, "Eksport", f"Zapisano:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd eksportu", str(e))
