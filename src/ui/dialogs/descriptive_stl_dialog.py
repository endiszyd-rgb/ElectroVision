"""Dialog opisowego tworzenia obiektów 3D i eksportu STL."""
from __future__ import annotations
import os, sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QLineEdit,
    QSplitter, QWidget, QTextEdit, QTabWidget, QSpinBox,
    QCheckBox, QMessageBox, QFileDialog, QProgressBar,
    QScrollArea, QFrame, QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from src.core.project import Project
from src.generators.descriptive_stl import (
    Primitive, PrimType, BoolOp, HoleSpec, CutoutSpec,
    build_scene, build_from_description, export_all_stl,
    make_enclosure, make_panel, make_bracket, make_standoff,
    make_din_clip, make_cable_clip, parse_description,
)


# ── Wątek generowania ──────────────────────────────────────────────────────────

class _BuildThread(QThread):
    done  = Signal(dict)    # {name: trimesh}
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result if isinstance(result, dict) else {"model": result})
        except Exception as e:
            self.error.emit(str(e))


# ── Podgląd 3D (wbudowany STL3DView) ──────────────────────────────────────────

def _try_load_viewer(stl_path: str, parent_widget):
    """Próbuje załadować STL3DView; zwraca widget lub None."""
    try:
        from src.ui.widgets.stl_3d_view import STL3DView
        v = STL3DView(parent_widget)
        v.load_stl(stl_path)
        return v
    except Exception:
        return None


# ── Gotowe presety obudów ──────────────────────────────────────────────────────

ENCLOSURE_PRESETS = [
    ("Własne wymiary",      {}),
    ("Arduino UNO",         dict(width=72,  depth=55,  height=28, wall=2.0, lid=True)),
    ("Arduino Nano",        dict(width=30,  depth=20,  height=20, wall=1.8, lid=True)),
    ("ESP32 Dev",           dict(width=40,  depth=30,  height=22, wall=2.0, lid=True)),
    ("ESP8266 (Wemos D1)",  dict(width=38,  depth=30,  height=20, wall=2.0, lid=True)),
    ("Raspberry Pi 4",      dict(width=90,  depth=65,  height=30, wall=2.0, lid=True)),
    ("Raspberry Pi Zero",   dict(width=67,  depth=32,  height=20, wall=2.0, lid=True)),
    ("RP2040 / Pico",       dict(width=55,  depth=25,  height=18, wall=2.0, lid=True)),
    ("STM32 Blue Pill",     dict(width=55,  depth=25,  height=18, wall=2.0, lid=True)),
    ("Ogólna mała",         dict(width=50,  depth=35,  height=20, wall=2.0, lid=True)),
    ("Ogólna średnia",      dict(width=80,  depth=60,  height=30, wall=2.5, lid=True)),
    ("Ogólna duża",         dict(width=120, depth=80,  height=40, wall=3.0, lid=True)),
    ("Montaż ścienny",      dict(width=90,  depth=60,  height=35, wall=2.5, lid=True)),
    ("Bateria 18650 x1",    dict(width=80,  depth=22,  height=22, wall=2.5, lid=True, standoffs=False)),
    ("Bateria 18650 x2",    dict(width=80,  depth=42,  height=22, wall=2.5, lid=True, standoffs=False)),
]

CUTOUT_PRESETS = [
    ("— brak —",      None),
    ("USB-C (lewo)",  CutoutSpec("left",  0, 1, 9.0, 3.5,  "USB-C")),
    ("USB-C (prawo)", CutoutSpec("right", 0, 1, 9.0, 3.5,  "USB-C")),
    ("USB-C (przód)", CutoutSpec("front", 0, 1, 9.0, 3.5,  "USB-C")),
    ("Micro USB",     CutoutSpec("left",  0, 1, 8.0, 3.0,  "Micro USB")),
    ("Mini USB",      CutoutSpec("left",  0, 1, 7.5, 4.0,  "Mini USB")),
    ("USB-A",         CutoutSpec("left",  0, 1,12.0, 5.0,  "USB-A")),
    ("DC Jack 5.5mm", CutoutSpec("back",  0, 2, 7.5, 7.5,  "DC Jack")),
    ("HDMI",          CutoutSpec("left",  0, 1,16.0, 7.0,  "HDMI")),
    ("RJ45 Ethernet", CutoutSpec("back",  0, 1,16.0,14.0,  "RJ45")),
    ("Jack 3.5mm",    CutoutSpec("front", 0, 5, 6.5, 6.5,  "Jack 3.5mm")),
    ("SD Card",       CutoutSpec("front", 0, 2,15.0, 2.5,  "SD Card")),
    ("Przycisk 12mm", CutoutSpec("top",   0, 0,13.0,13.0,  "Button")),
    ("LED 5mm",       CutoutSpec("front", 0,10, 5.5, 5.5,  "LED")),
    ("OLED 0.96\"",   CutoutSpec("top",   0, 0,28.0,12.0,  "OLED")),
    ("Wentylacja 30x30", CutoutSpec("top",0, 0,30.0,30.0,  "Vent")),
]


# ── Tabela prymitywów ──────────────────────────────────────────────────────────

P_COL_TYPE = 0; P_COL_OP = 1; P_COL_X = 2; P_COL_Y = 3; P_COL_Z = 4
P_COL_W = 5;   P_COL_D = 6;  P_COL_H = 7; P_COL_R = 8; P_COL_LBL = 9


class _PrimTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(10)
        self.setHorizontalHeaderLabels(
            ["Typ", "Op", "X", "Y", "Z", "Szer.", "Gł.", "Wys.", "R", "Opis"])
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for i in range(2, 9):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(9, QHeaderView.Stretch)
        self.setEditTriggers(QTableWidget.AllEditTriggers)

    def add_primitive(self, p: Primitive) -> None:
        row = self.rowCount()
        self.insertRow(row)
        type_cb = QComboBox()
        type_cb.addItems([t.value for t in PrimType])
        type_cb.setCurrentText(p.ptype.value)
        self.setCellWidget(row, P_COL_TYPE, type_cb)
        op_cb = QComboBox()
        op_cb.addItems(["add", "sub"])
        op_cb.setCurrentText(p.op.value)
        self.setCellWidget(row, P_COL_OP, op_cb)
        for col, val in [(P_COL_X, p.x), (P_COL_Y, p.y), (P_COL_Z, p.z),
                         (P_COL_W, p.width), (P_COL_D, p.depth),
                         (P_COL_H, p.height), (P_COL_R, p.radius)]:
            self.setItem(row, col, QTableWidgetItem(f"{val:.2f}"))
        self.setItem(row, P_COL_LBL, QTableWidgetItem(p.label))

    def get_primitives(self) -> list[Primitive]:
        result = []
        for row in range(self.rowCount()):
            try:
                type_w = self.cellWidget(row, P_COL_TYPE)
                op_w   = self.cellWidget(row, P_COL_OP)
                ptype  = PrimType(type_w.currentText() if type_w else "box")
                op     = BoolOp(op_w.currentText() if op_w else "add")
                def _f(col): return float(self.item(row, col).text() if self.item(row, col) else 0)
                lbl_item = self.item(row, P_COL_LBL)
                result.append(Primitive(
                    ptype=ptype, op=op,
                    x=_f(P_COL_X), y=_f(P_COL_Y), z=_f(P_COL_Z),
                    width=_f(P_COL_W), depth=_f(P_COL_D),
                    height=_f(P_COL_H), radius=_f(P_COL_R),
                    label=lbl_item.text() if lbl_item else "",
                ))
            except Exception:
                pass
        return result


# ── Dialog główny ──────────────────────────────────────────────────────────────

class DescriptiveSTLDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._meshes: dict = {}
        self._last_paths: list[str] = []
        self._thread: _BuildThread | None = None
        self.setWindowTitle("Opisowe tworzenie obiektów 3D — eksport STL")
        self.resize(1150, 720)
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        spl = QSplitter(Qt.Horizontal)

        # ── Lewa: kreator ─────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()

        # ─ Tab 1: Opis tekstowy ───────────────────────────────────────────────
        t1 = QWidget()
        t1l = QVBoxLayout(t1)

        t1l.addWidget(QLabel(
            "Opisz obiekt naturalnym językiem (PL / EN).\n"
            "Przykłady poniżej — możesz mieszać język i wymiary:"
        ))

        self._desc_edit = QTextEdit()
        self._desc_edit.setFont(QFont("Consolas", 10))
        self._desc_edit.setPlaceholderText(
            "obudowa 60x40x25 mm, ścianka 2 mm, z wiekiem, standoffy M3, USB-C na lewej ścianie\n\n"
            "enclosure 80x60x30, wall 2.5mm, HDMI right, DC jack back, lid\n\n"
            "panel 100x60, grubość 3mm, 4 otwory M3\n\n"
            "kątownik 40x30x20, grubość 2.5mm\n\n"
            "standoff 10mm, OD 6mm, M3"
        )
        self._desc_edit.setMinimumHeight(130)
        t1l.addWidget(self._desc_edit, 1)

        # Przyciski przykładów
        ex_lbl = QLabel("Szybkie przykłady:")
        ex_lbl.setStyleSheet("color:#888; font-size:10px; margin-top:4px;")
        t1l.addWidget(ex_lbl)
        ex_grid = QHBoxLayout()
        for example in [
            "obudowa ESP32 40x30x22 USB-C",
            "panel 100x80 4 otwory M3",
            "obudowa raspberry pi 4 z HDMI",
            "kątownik 50x40x25",
            "standoff 10mm M3",
        ]:
            btn = QPushButton(example)
            btn.setStyleSheet("font-size:9px; padding:2px 4px;")
            btn.clicked.connect(lambda _, t=example: self._desc_edit.setPlainText(t))
            ex_grid.addWidget(btn)
        t1l.addLayout(ex_grid)

        # Parsed preview
        self._parsed_lbl = QLabel()
        self._parsed_lbl.setStyleSheet("color:#6ad; font-size:10px; margin-top:4px;")
        self._parsed_lbl.setWordWrap(True)
        t1l.addWidget(self._parsed_lbl)

        btn_parse = QPushButton("🔍 Analizuj opis")
        btn_parse.clicked.connect(self._preview_parse)
        t1l.addWidget(btn_parse)

        btn_build_desc = QPushButton("⚙ Generuj 3D z opisu")
        btn_build_desc.setStyleSheet("background:#1a4a1a; color:#5f5; font-weight:bold; padding:6px;")
        btn_build_desc.clicked.connect(self._build_from_desc)
        t1l.addWidget(btn_build_desc)

        self._tabs.addTab(t1, "📝 Opis tekstowy")

        # ─ Tab 2: Obudowa (formularz) ─────────────────────────────────────────
        t2 = QScrollArea()
        t2.setWidgetResizable(True)
        t2w = QWidget()
        t2l = QVBoxLayout(t2w)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self._enc_preset = QComboBox()
        self._enc_preset.addItems([n for n, _ in ENCLOSURE_PRESETS])
        self._enc_preset.currentIndexChanged.connect(self._apply_enc_preset)
        preset_row.addWidget(self._enc_preset, 1)
        t2l.addLayout(preset_row)

        enc_form = QGroupBox("Wymiary obudowy")
        ef = QFormLayout(enc_form)

        self._enc_w = self._dspin(60, 1, 500); ef.addRow("Szerokość (X):", self._enc_w)
        self._enc_d = self._dspin(40, 1, 500); ef.addRow("Głębokość (Y):", self._enc_d)
        self._enc_h = self._dspin(25, 1, 500); ef.addRow("Wysokość (Z):",  self._enc_h)
        self._enc_wall = self._dspin(2.0, 0.5, 10, step=0.5)
        ef.addRow("Grubość ścianki:", self._enc_wall)
        self._enc_r = self._dspin(2.0, 0, 20, step=0.5)
        ef.addRow("Zaokrąglenie naroży:", self._enc_r)
        t2l.addWidget(enc_form)

        feat_box = QGroupBox("Cechy")
        ffl = QVBoxLayout(feat_box)
        self._enc_lid = QCheckBox("Wieko (osobny plik STL)"); self._enc_lid.setChecked(True)
        self._enc_std = QCheckBox("Standoffy M3 w narożnikach"); self._enc_std.setChecked(True)
        ffl.addWidget(self._enc_lid); ffl.addWidget(self._enc_std)

        std_row = QFormLayout()
        self._enc_std_h = self._dspin(3.0, 1, 20)
        std_row.addRow("Wys. standoffów:", self._enc_std_h)
        ffl.addLayout(std_row)
        t2l.addWidget(feat_box)

        # Wycięcia
        cut_box = QGroupBox("Wycięcia w ściankach")
        cl = QVBoxLayout(cut_box)
        cl.addWidget(QLabel("Dodaj wycięcia na złącza (do 4):"))
        self._cut_combos: list[QComboBox] = []
        for _ in range(4):
            row = QHBoxLayout()
            cb = QComboBox()
            cb.addItems([n for n, _ in CUTOUT_PRESETS])
            self._cut_combos.append(cb)
            row.addWidget(cb)
            cl.addLayout(row)
        t2l.addWidget(cut_box)

        btn_build_enc = QPushButton("⚙ Generuj obudowę")
        btn_build_enc.setStyleSheet("background:#1a3a6a; color:#88f; font-weight:bold; padding:6px;")
        btn_build_enc.clicked.connect(self._build_enclosure)
        t2l.addWidget(btn_build_enc)
        t2l.addStretch()
        t2.setWidget(t2w)
        self._tabs.addTab(t2, "📦 Obudowa")

        # ─ Tab 3: Inne gotowe obiekty ─────────────────────────────────────────
        t3 = QWidget()
        t3l = QVBoxLayout(t3)

        obj_sel = QGroupBox("Typ obiektu")
        os_l = QFormLayout(obj_sel)
        self._obj_type = QComboBox()
        self._obj_type.addItems(["Panel", "Kątownik (Bracket)", "Standoff / Dystans",
                                  "Klips DIN 35mm", "Klips na kabel"])
        self._obj_type.currentIndexChanged.connect(self._on_obj_type_changed)
        os_l.addRow("Obiekt:", self._obj_type)
        t3l.addWidget(obj_sel)

        # Panel params
        self._panel_group = QGroupBox("Parametry panelu")
        pg = QFormLayout(self._panel_group)
        self._pan_w = self._dspin(100, 10, 500); pg.addRow("Szerokość:", self._pan_w)
        self._pan_h = self._dspin(60,  10, 500); pg.addRow("Wysokość:",  self._pan_h)
        self._pan_t = self._dspin(3.0, 0.5, 20); pg.addRow("Grubość:",  self._pan_t)
        self._pan_holes_n  = QSpinBox(); self._pan_holes_n.setRange(0, 20); self._pan_holes_n.setValue(4)
        pg.addRow("Otwory M3 (narożniki):", self._pan_holes_n)
        t3l.addWidget(self._panel_group)

        # Bracket params
        self._bracket_group = QGroupBox("Parametry kątownika")
        bg = QFormLayout(self._bracket_group)
        self._brk_w = self._dspin(40, 5, 200); bg.addRow("Szerokość:",  self._brk_w)
        self._brk_h = self._dspin(30, 5, 200); bg.addRow("Wysokość:",   self._brk_h)
        self._brk_d = self._dspin(20, 5, 200); bg.addRow("Głębokość:",  self._brk_d)
        self._brk_t = self._dspin(3.0, 1, 10); bg.addRow("Grubość:",    self._brk_t)
        self._brk_dia = self._dspin(3.2, 1, 10); bg.addRow("Śr. otworów:", self._brk_dia)
        t3l.addWidget(self._bracket_group)
        self._bracket_group.setVisible(False)

        # Standoff params
        self._std_group = QGroupBox("Parametry standoffa")
        sg = QFormLayout(self._std_group)
        self._std_h   = self._dspin(10, 1, 100); sg.addRow("Wysokość:", self._std_h)
        self._std_od  = self._dspin(6,  2, 30);  sg.addRow("Śr. zewn. (OD):", self._std_od)
        self._std_id  = self._dspin(3.2, 0.5, 20); sg.addRow("Śr. otworu:", self._std_id)
        t3l.addWidget(self._std_group)
        self._std_group.setVisible(False)

        # DIN / Cable params (uproszczone)
        self._din_group = QGroupBox("Parametry DIN / Klips")
        dg = QFormLayout(self._din_group)
        self._din_w = self._dspin(35, 10, 100); dg.addRow("Szerokość klipsa:", self._din_w)
        t3l.addWidget(self._din_group)
        self._din_group.setVisible(False)

        btn_build_obj = QPushButton("⚙ Generuj obiekt")
        btn_build_obj.setStyleSheet("background:#3a1a5a; color:#c8f; font-weight:bold; padding:6px;")
        btn_build_obj.clicked.connect(self._build_object)
        t3l.addWidget(btn_build_obj)
        t3l.addStretch()
        self._tabs.addTab(t3, "🔧 Inne obiekty")

        # ─ Tab 4: Prymitywy ───────────────────────────────────────────────────
        t4 = QWidget()
        t4l = QVBoxLayout(t4)
        t4l.addWidget(QLabel("Składaj obiekt z prymitywów (CSG: add = dodaj, sub = odejmij):"))
        self._prim_table = _PrimTable()
        t4l.addWidget(self._prim_table, 1)

        pbtns = QHBoxLayout()
        for lbl, ptype, op in [
            ("+ Box",    PrimType.BOX,      BoolOp.ADD),
            ("+ Cyl",    PrimType.CYLINDER,  BoolOp.ADD),
            ("+ Sphere", PrimType.SPHERE,    BoolOp.ADD),
            ("− Box",    PrimType.BOX,      BoolOp.SUB),
            ("− Cyl",    PrimType.CYLINDER,  BoolOp.SUB),
        ]:
            btn = QPushButton(lbl)
            btn.clicked.connect(lambda _, pt=ptype, bo=op: self._add_prim(pt, bo))
            pbtns.addWidget(btn)
        btn_del_prim = QPushButton("Usuń")
        btn_del_prim.clicked.connect(self._del_prim)
        pbtns.addWidget(btn_del_prim)
        t4l.addLayout(pbtns)

        btn_build_prim = QPushButton("⚙ Generuj z prymitywów")
        btn_build_prim.setStyleSheet("background:#3a2a1a; color:#fa8; font-weight:bold; padding:6px;")
        btn_build_prim.clicked.connect(self._build_primitives)
        t4l.addWidget(btn_build_prim)
        self._tabs.addTab(t4, "🧩 Prymitywy CSG")

        ll.addWidget(self._tabs, 1)

        spl.addWidget(left)

        # ── Prawa: podgląd + log ───────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        viewer_box = QGroupBox("Podgląd 3D")
        vbl = QVBoxLayout(viewer_box)
        self._viewer_placeholder = QLabel(
            "Wygeneruj obiekt aby zobaczyć podgląd 3D.\n\n"
            "🖱  Obróć: lewy przycisk myszy\n"
            "🖱  Zoom: scroll\n"
            "🖱  Przesuń: prawy przycisk"
        )
        self._viewer_placeholder.setAlignment(Qt.AlignCenter)
        self._viewer_placeholder.setStyleSheet("color:#555; font-size:12px; background:#0e0e18;")
        self._viewer_placeholder.setMinimumHeight(300)
        vbl.addWidget(self._viewer_placeholder)
        self._viewer_widget = None
        rl.addWidget(viewer_box, 2)

        # Info
        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color:#8be; font-size:10px; padding:4px;")
        self._info_lbl.setWordWrap(True)
        rl.addWidget(self._info_lbl)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        rl.addWidget(self._progress)

        # Log
        log_box = QGroupBox("Log")
        lbl = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMaximumHeight(120)
        lbl.addWidget(self._log)
        rl.addWidget(log_box)

        spl.addWidget(right)
        spl.setSizes([440, 610])
        root.addWidget(spl, 1)

        # ── Bottom ─────────────────────────────────────────────────────────────
        bot = QHBoxLayout()
        self._btn_export = QPushButton("💾 Eksportuj STL…")
        self._btn_export.setStyleSheet("background:#1a4a8f; color:white; padding:5px 14px; font-weight:bold;")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_stl)
        bot.addWidget(self._btn_export)

        self._btn_open = QPushButton("📂 Otwórz folder")
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_folder)
        bot.addWidget(self._btn_open)

        bot.addStretch()

        self._mesh_lbl = QLabel("Brak modelu")
        self._mesh_lbl.setStyleSheet("color:#666; font-size:10px;")
        bot.addWidget(self._mesh_lbl)
        bot.addStretch()

        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bot.addWidget(btn_close)
        root.addLayout(bot)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _dspin(self, val=10.0, mn=0.0, mx=999.0, step=1.0) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(mn, mx)
        sp.setValue(val)
        sp.setSuffix(" mm")
        sp.setSingleStep(step)
        return sp

    def _on_obj_type_changed(self, idx: int) -> None:
        self._panel_group.setVisible(idx == 0)
        self._bracket_group.setVisible(idx == 1)
        self._std_group.setVisible(idx == 2)
        self._din_group.setVisible(idx in (3, 4))

    def _apply_enc_preset(self, idx: int) -> None:
        _, params = ENCLOSURE_PRESETS[idx]
        if not params:
            return
        if "width"  in params: self._enc_w.setValue(params["width"])
        if "depth"  in params: self._enc_d.setValue(params["depth"])
        if "height" in params: self._enc_h.setValue(params["height"])
        if "wall"   in params: self._enc_wall.setValue(params["wall"])
        if "lid"    in params: self._enc_lid.setChecked(params["lid"])
        if "standoffs" in params: self._enc_std.setChecked(params.get("standoffs", True))

    # ── Build functions ─────────────────────────────────────────────────────────

    def _start_build(self, fn, *args, **kwargs) -> None:
        self._progress.setVisible(True)
        self._log.append("⚙ Generowanie…")
        self._thread = _BuildThread(fn, *args, **kwargs)
        self._thread.done.connect(self._on_build_done)
        self._thread.error.connect(self._on_build_error)
        self._thread.start()

    def _on_build_done(self, meshes: dict) -> None:
        self._progress.setVisible(False)
        self._meshes = meshes
        total_verts = sum(len(m.vertices) for m in meshes.values())
        total_faces = sum(len(m.faces)    for m in meshes.values())
        parts = list(meshes.keys())
        self._mesh_lbl.setText(
            f"Części: {', '.join(parts)}  |  Wierzchołki: {total_verts:,}  |  Trójkąty: {total_faces:,}"
        )
        self._log.append(f"✓ Wygenerowano: {', '.join(parts)}")
        self._btn_export.setEnabled(True)
        self._info_lbl.setText(
            f"Model gotowy: {len(parts)} część(i) — {total_faces:,} trójkątów. "
            "Kliknij 'Eksportuj STL' aby zapisać."
        )
        self._show_preview(meshes)

    def _on_build_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._log.append(f"✗ Błąd: {msg}")
        QMessageBox.critical(self, "Błąd generowania 3D", msg)

    def _show_preview(self, meshes: dict) -> None:
        """Zapisuje tymczasowy STL i ładuje w widoku 3D."""
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".stl"))
        try:
            import trimesh
            combined = trimesh.util.concatenate(list(meshes.values())) \
                       if len(meshes) > 1 else list(meshes.values())[0]
            combined.export(str(tmp))
        except Exception as e:
            self._log.append(f"Podgląd: nie można połączyć meshów: {e}")
            return

        try:
            from src.ui.widgets.stl_3d_view import STL3DView
            viewer_box = None
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                if item and hasattr(item, "widget"):
                    w = item.widget()
                    if isinstance(w, QSplitter):
                        right_w = w.widget(1)
                        for j in range(right_w.layout().count()):
                            child = right_w.layout().itemAt(j)
                            if child and isinstance(child.widget(), QGroupBox):
                                if child.widget().title() == "Podgląd 3D":
                                    viewer_box = child.widget()
                                    break

            if viewer_box:
                vbl = viewer_box.layout()
                if self._viewer_widget:
                    vbl.removeWidget(self._viewer_widget)
                    self._viewer_widget.deleteLater()
                    self._viewer_widget = None
                vbl.removeWidget(self._viewer_placeholder)
                self._viewer_placeholder.setVisible(False)

                self._viewer_widget = STL3DView(viewer_box)
                self._viewer_widget.load_stl(str(tmp))
                vbl.addWidget(self._viewer_widget)
        except Exception as e:
            self._log.append(f"Podgląd 3D: {e}")

    def _build_from_desc(self) -> None:
        text = self._desc_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Brak opisu", "Wpisz opis obiektu.")
            return
        self._start_build(build_from_description, text)

    def _preview_parse(self) -> None:
        text = self._desc_edit.toPlainText().strip()
        if not text:
            return
        p = parse_description(text)
        lines = [
            f"Typ: {p['object_type']}",
            f"Wymiary: {p['width']:.1f} × {p['depth']:.1f} × {p['height']:.1f} mm",
            f"Ścianka: {p['wall']:.1f} mm  |  Wieko: {'tak' if p['lid'] else 'nie'}  |  "
            f"Standoffy: {'tak' if p['standoffs'] else 'nie'}",
        ]
        if p["cutouts"]:
            lines.append("Wycięcia: " + ", ".join(c.label or c.wall for c in p["cutouts"]))
        self._parsed_lbl.setText("  →  ".join(lines))

    def _get_selected_cutouts(self) -> list[CutoutSpec]:
        cuts = []
        for cb in self._cut_combos:
            idx = cb.currentIndex()
            _, spec = CUTOUT_PRESETS[idx]
            if spec:
                import copy
                cuts.append(copy.deepcopy(spec))
        return cuts

    def _build_enclosure(self) -> None:
        cutouts = self._get_selected_cutouts()
        self._start_build(
            make_enclosure,
            width=self._enc_w.value(),
            depth=self._enc_d.value(),
            height=self._enc_h.value(),
            wall=self._enc_wall.value(),
            lid=self._enc_lid.isChecked(),
            standoffs=self._enc_std.isChecked(),
            standoff_h=self._enc_std_h.value(),
            corner_r=self._enc_r.value(),
            cutouts=cutouts,
            separate_lid=True,
        )

    def _build_object(self) -> None:
        idx = self._obj_type.currentIndex()
        if idx == 0:   # Panel
            holes = []
            n = self._pan_holes_n.value()
            w, h = self._pan_w.value(), self._pan_h.value()
            if n >= 4:
                m = 8
                for hx, hy in [(m, m), (w-m, m), (w-m, h-m), (m, h-m)]:
                    holes.append(HoleSpec(hx, hy, 3.2))
            self._start_build(make_panel, w, h, self._pan_t.value(), holes=holes)
        elif idx == 1: # Bracket
            self._start_build(make_bracket,
                              self._brk_w.value(), self._brk_h.value(),
                              self._brk_d.value(), self._brk_t.value(),
                              self._brk_dia.value())
        elif idx == 2: # Standoff
            self._start_build(make_standoff,
                              self._std_h.value(), self._std_od.value(),
                              self._std_id.value())
        elif idx == 3: # DIN clip
            self._start_build(make_din_clip, self._din_w.value())
        elif idx == 4: # Cable clip
            self._start_build(make_cable_clip, 5.0)

    def _add_prim(self, ptype: PrimType, op: BoolOp) -> None:
        self._prim_table.add_primitive(Primitive(ptype=ptype, op=op,
                                                  width=20, depth=20, height=20, radius=10))

    def _del_prim(self) -> None:
        row = self._prim_table.currentRow()
        if row >= 0:
            self._prim_table.removeRow(row)

    def _build_primitives(self) -> None:
        prims = self._prim_table.get_primitives()
        if not prims:
            QMessageBox.warning(self, "Brak prymitywów", "Dodaj co najmniej jeden prymityw.")
            return
        self._start_build(lambda p: {"model": build_scene(p)}, prims)

    # ── Eksport ────────────────────────────────────────────────────────────────

    def _export_stl(self) -> None:
        if not self._meshes:
            return
        base, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj STL", "model.stl", "STL (*.stl)"
        )
        if not base:
            return
        try:
            paths = export_all_stl(self._meshes, base)
            self._last_paths = paths
            self._btn_open.setEnabled(True)
            self._log.append("✓ Zapisano:")
            for p in paths:
                self._log.append(f"   {p}")
            QMessageBox.information(
                self, "Eksport STL",
                f"Zapisano {len(paths)} plik(i) STL:\n\n" +
                "\n".join(Path(p).name for p in paths) +
                "\n\nOtwórz w PrusaSlicer / Cura / Fusion 360."
            )
        except Exception as e:
            QMessageBox.critical(self, "Błąd eksportu", str(e))

    def _open_folder(self) -> None:
        if not self._last_paths:
            return
        folder = str(Path(self._last_paths[0]).parent)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass
