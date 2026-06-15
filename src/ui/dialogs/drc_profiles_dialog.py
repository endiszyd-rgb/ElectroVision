"""Profile reguł DRC — gotowe presety wymagań popularnych fabrykatów PCB."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QDoubleSpinBox, QComboBox, QLineEdit,
    QSplitter, QWidget, QTextEdit, QMessageBox, QFileDialog,
    QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont

from src.core.project import Project


# ── Model reguł ────────────────────────────────────────────────────────────────

@dataclass
class DRCProfile:
    name: str
    fab: str                    # np. "JLCPCB", "PCBWay", "Custom"
    tier: str                   # np. "Standard", "Advanced", "Prototype"
    url: str = ""
    min_trace_mm: float   = 0.2
    min_clearance_mm: float = 0.2
    min_via_drill_mm: float = 0.3
    min_via_annular_mm: float = 0.13
    min_edge_clearance_mm: float = 0.3
    min_silkscreen_mm: float = 0.15
    min_drill_mm: float = 0.2
    min_copper_weight_oz: float = 1.0
    max_board_size_mm: tuple = (400.0, 400.0)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name":                 self.name,
            "fab":                  self.fab,
            "tier":                 self.tier,
            "url":                  self.url,
            "min_trace_mm":         self.min_trace_mm,
            "min_clearance_mm":     self.min_clearance_mm,
            "min_via_drill_mm":     self.min_via_drill_mm,
            "min_via_annular_mm":   self.min_via_annular_mm,
            "min_edge_clearance_mm":self.min_edge_clearance_mm,
            "min_silkscreen_mm":    self.min_silkscreen_mm,
            "min_drill_mm":         self.min_drill_mm,
            "min_copper_weight_oz": self.min_copper_weight_oz,
            "max_board_size_mm":    list(self.max_board_size_mm),
            "notes":                self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "DRCProfile":
        p = DRCProfile(
            name=d.get("name", "Custom"),
            fab=d.get("fab", "Custom"),
            tier=d.get("tier", "Standard"),
        )
        p.url                  = d.get("url", "")
        p.min_trace_mm         = d.get("min_trace_mm", 0.2)
        p.min_clearance_mm     = d.get("min_clearance_mm", 0.2)
        p.min_via_drill_mm     = d.get("min_via_drill_mm", 0.3)
        p.min_via_annular_mm   = d.get("min_via_annular_mm", 0.13)
        p.min_edge_clearance_mm= d.get("min_edge_clearance_mm", 0.3)
        p.min_silkscreen_mm    = d.get("min_silkscreen_mm", 0.15)
        p.min_drill_mm         = d.get("min_drill_mm", 0.2)
        p.min_copper_weight_oz = d.get("min_copper_weight_oz", 1.0)
        sz                     = d.get("max_board_size_mm", [400, 400])
        p.max_board_size_mm    = (sz[0], sz[1])
        p.notes                = d.get("notes", "")
        return p

    def check_vs_profile(self, other: "DRCProfile") -> list[str]:
        """Zwraca listę reguł ostrzejszych niż profil docelowy."""
        issues = []
        if other.min_trace_mm < self.min_trace_mm:
            issues.append(
                f"Ścieżka: {other.min_trace_mm} mm < wymagane {self.min_trace_mm} mm"
            )
        if other.min_clearance_mm < self.min_clearance_mm:
            issues.append(
                f"Prześwit: {other.min_clearance_mm} mm < wymagane {self.min_clearance_mm} mm"
            )
        if other.min_via_drill_mm < self.min_via_drill_mm:
            issues.append(
                f"Wiercenie przelotki: {other.min_via_drill_mm} mm < wymagane {self.min_via_drill_mm} mm"
            )
        if other.min_via_annular_mm < self.min_via_annular_mm:
            issues.append(
                f"Pierścień przelotki: {other.min_via_annular_mm} mm < wymagane {self.min_via_annular_mm} mm"
            )
        return issues


# ── Wbudowane presety fabrykatów ───────────────────────────────────────────────

BUILTIN_PROFILES: list[DRCProfile] = [
    DRCProfile(
        name="JLCPCB Standard",
        fab="JLCPCB", tier="Standard",
        url="https://jlcpcb.com/capabilities/pcb-capabilities",
        min_trace_mm=0.127, min_clearance_mm=0.127,
        min_via_drill_mm=0.3, min_via_annular_mm=0.13,
        min_edge_clearance_mm=0.3, min_silkscreen_mm=0.15,
        min_drill_mm=0.3, min_copper_weight_oz=1.0,
        max_board_size_mm=(510.0, 510.0),
        notes="Najtańsza opcja, 2-warstwy, 5 szt. za $2. "
              "Min trace/space 5/5 mil (0.127 mm). Przelotki min 0.3 mm.",
    ),
    DRCProfile(
        name="JLCPCB Advanced",
        fab="JLCPCB", tier="Advanced",
        url="https://jlcpcb.com/capabilities/pcb-capabilities",
        min_trace_mm=0.075, min_clearance_mm=0.075,
        min_via_drill_mm=0.2, min_via_annular_mm=0.1,
        min_edge_clearance_mm=0.2, min_silkscreen_mm=0.1,
        min_drill_mm=0.15, min_copper_weight_oz=1.0,
        max_board_size_mm=(500.0, 500.0),
        notes="HDI, impedancja kontrolowana, BGA. "
              "Min trace/space 3/3 mil (0.075 mm). Laser vias 0.1 mm.",
    ),
    DRCProfile(
        name="PCBWay Standard",
        fab="PCBWay", tier="Standard",
        url="https://www.pcbway.com/capabilities.html",
        min_trace_mm=0.1, min_clearance_mm=0.1,
        min_via_drill_mm=0.3, min_via_annular_mm=0.13,
        min_edge_clearance_mm=0.3, min_silkscreen_mm=0.15,
        min_drill_mm=0.2, min_copper_weight_oz=1.0,
        max_board_size_mm=(500.0, 500.0),
        notes="Standard 2/4-warstwy. Min trace 4 mil (0.1 mm). "
              "Dobra obsługa zamówień specjalnych i małych serii.",
    ),
    DRCProfile(
        name="PCBWay Advanced (HDI)",
        fab="PCBWay", tier="Advanced",
        url="https://www.pcbway.com/capabilities.html",
        min_trace_mm=0.05, min_clearance_mm=0.05,
        min_via_drill_mm=0.1, min_via_annular_mm=0.075,
        min_edge_clearance_mm=0.15, min_silkscreen_mm=0.08,
        min_drill_mm=0.1, min_copper_weight_oz=0.5,
        max_board_size_mm=(500.0, 500.0),
        notes="HDI, 2 mil trace/space, laser microvia 0.1 mm. "
              "Do zastosowań SiP i chipscale BGA.",
    ),
    DRCProfile(
        name="OSH Park",
        fab="OSH Park", tier="Standard",
        url="https://docs.oshpark.com/design-tools/design-rules/",
        min_trace_mm=0.127, min_clearance_mm=0.127,
        min_via_drill_mm=0.254, min_via_annular_mm=0.127,
        min_edge_clearance_mm=0.381, min_silkscreen_mm=0.2,
        min_drill_mm=0.254, min_copper_weight_oz=1.0,
        max_board_size_mm=(122.0, 152.0),
        notes="USA, fioletowy PCB. 5 mil trace/space, 10 mil drill. "
              "Dobre jakość, droższy od Azji. Min via drill 0.254 mm.",
    ),
    DRCProfile(
        name="Eurocircuits Standard",
        fab="Eurocircuits", tier="Standard",
        url="https://www.eurocircuits.com/pcb-design-guidelines/",
        min_trace_mm=0.1, min_clearance_mm=0.1,
        min_via_drill_mm=0.3, min_via_annular_mm=0.15,
        min_edge_clearance_mm=0.3, min_silkscreen_mm=0.15,
        min_drill_mm=0.3, min_copper_weight_oz=1.0,
        max_board_size_mm=(460.0, 610.0),
        notes="Europejski fabrykat. Certyfikat UL/REACH/RoHS. "
              "Dobry dla prototypów i małych serii z dokumentacją.",
    ),
    DRCProfile(
        name="ITead (Seeed) Standard",
        fab="ITead/Seeed", tier="Standard",
        url="https://www.seeedstudio.com/fusion_pcb.html",
        min_trace_mm=0.152, min_clearance_mm=0.152,
        min_via_drill_mm=0.3, min_via_annular_mm=0.15,
        min_edge_clearance_mm=0.4, min_silkscreen_mm=0.2,
        min_drill_mm=0.3, min_copper_weight_oz=1.0,
        max_board_size_mm=(500.0, 500.0),
        notes="Tania opcja dla hobbystów. 6 mil trace/space. "
              "Dobre opcje kolorów laminatu (10 kolorów soldermask).",
    ),
    DRCProfile(
        name="Hobbyist (liberalne)",
        fab="Ogólny", tier="Hobbyist",
        url="",
        min_trace_mm=0.2, min_clearance_mm=0.2,
        min_via_drill_mm=0.4, min_via_annular_mm=0.15,
        min_edge_clearance_mm=0.5, min_silkscreen_mm=0.2,
        min_drill_mm=0.4, min_copper_weight_oz=1.0,
        max_board_size_mm=(400.0, 400.0),
        notes="Liberalne reguły dla projektów hobbystycznych. "
              "Bezpieczny margines dla większości tanich fabrykatów.",
    ),
    DRCProfile(
        name="Profesjonalny (restrykcyjne)",
        fab="Ogólny", tier="Professional",
        url="",
        min_trace_mm=0.1, min_clearance_mm=0.1,
        min_via_drill_mm=0.2, min_via_annular_mm=0.1,
        min_edge_clearance_mm=0.2, min_silkscreen_mm=0.1,
        min_drill_mm=0.15, min_copper_weight_oz=1.0,
        max_board_size_mm=(500.0, 500.0),
        notes="Restrykcyjne reguły dla projektów wysokiej gęstości. "
              "Wymaga fabrykata klasy II lub wyżej.",
    ),
]


# ── Dialog ──────────────────────────────────────────────────────────────────────

_FIELDS = [
    ("min_trace_mm",          "Min. szerokość ścieżki",    "mm"),
    ("min_clearance_mm",      "Min. prześwit",             "mm"),
    ("min_via_drill_mm",      "Min. wiercenie przelotki",  "mm"),
    ("min_via_annular_mm",    "Min. pierścień przelotki",  "mm"),
    ("min_edge_clearance_mm", "Min. odległość od krawędzi","mm"),
    ("min_silkscreen_mm",     "Min. szerokość sitodruku",  "mm"),
    ("min_drill_mm",          "Min. wiercenie PTH",        "mm"),
    ("min_copper_weight_oz",  "Min. grubość miedzi",       "oz"),
]

COL_NAME = 0
COL_FAB  = 1
COL_TIER = 2
COL_TRACE = 3
COL_CLR  = 4
COL_VIA  = 5


class DRCProfilesDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._profiles = list(BUILTIN_PROFILES)
        self._sel: int = 0
        self.setWindowTitle("Profile reguł DRC — wymagania fabrykatów PCB")
        self.resize(1080, 660)
        self._build_ui()
        self._populate()
        self._prof_table.selectRow(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        spl = QSplitter(Qt.Horizontal)

        # ── Lewa: lista profili ───────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Dostępne profile fabrykatów:"))

        self._prof_table = QTableWidget()
        self._prof_table.setColumnCount(6)
        self._prof_table.setHorizontalHeaderLabels(
            ["Nazwa", "Fabrykant", "Klasa", "Ścieżka", "Prześwit", "Via drill"])
        hdr = self._prof_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._prof_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._prof_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._prof_table.itemSelectionChanged.connect(self._on_sel)
        ll.addWidget(self._prof_table, 1)

        p_btns = QHBoxLayout()
        btn_add_p  = QPushButton("+ Nowy profil")
        btn_add_p.clicked.connect(self._add_profile)
        btn_dup_p  = QPushButton("⧉ Duplikuj")
        btn_dup_p.clicked.connect(self._dup_profile)
        btn_del_p  = QPushButton("− Usuń")
        btn_del_p.clicked.connect(self._del_profile)
        p_btns.addWidget(btn_add_p); p_btns.addWidget(btn_dup_p); p_btns.addWidget(btn_del_p)
        ll.addLayout(p_btns)

        io_btns = QHBoxLayout()
        btn_exp = QPushButton("💾 Eksportuj JSON")
        btn_exp.clicked.connect(self._export_json)
        btn_imp = QPushButton("📂 Importuj JSON")
        btn_imp.clicked.connect(self._import_json)
        io_btns.addWidget(btn_exp); io_btns.addWidget(btn_imp)
        ll.addLayout(io_btns)

        spl.addWidget(left)

        # ── Prawa: szczegóły + edytor ─────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        meta_box = QGroupBox("Dane profilu")
        mf = QFormLayout(meta_box)
        self._e_name  = QLineEdit(); self._e_name.textChanged.connect(self._save)
        mf.addRow("Nazwa:", self._e_name)
        self._e_fab   = QLineEdit(); self._e_fab.textChanged.connect(self._save)
        mf.addRow("Fabrykant:", self._e_fab)
        self._e_tier  = QLineEdit(); self._e_tier.textChanged.connect(self._save)
        mf.addRow("Klasa / tier:", self._e_tier)
        self._e_url   = QLineEdit(); self._e_url.setPlaceholderText("URL strony możliwości")
        self._e_url.textChanged.connect(self._save)
        mf.addRow("URL:", self._e_url)
        rl.addWidget(meta_box)

        rules_box = QGroupBox("Reguły")
        rf = QFormLayout(rules_box)
        self._spins: dict[str, QDoubleSpinBox] = {}
        for attr, label, unit in _FIELDS:
            sp = QDoubleSpinBox()
            sp.setRange(0.01, 10.0)
            sp.setSingleStep(0.025)
            sp.setSuffix(f" {unit}")
            sp.valueChanged.connect(self._save)
            self._spins[attr] = sp
            rf.addRow(f"{label}:", sp)
        rl.addWidget(rules_box)

        notes_box = QGroupBox("Uwagi / ograniczenia")
        nf = QVBoxLayout(notes_box)
        self._e_notes = QTextEdit()
        self._e_notes.setMaximumHeight(80)
        self._e_notes.textChanged.connect(self._save)
        nf.addWidget(self._e_notes)
        rl.addWidget(notes_box)

        # Porównanie z bieżącymi ustawieniami
        cmp_box = QGroupBox("Porównanie z bieżącymi ustawieniami DRC projektu")
        cmp_l = QVBoxLayout(cmp_box)
        self._cmp_lbl = QLabel()
        self._cmp_lbl.setWordWrap(True)
        self._cmp_lbl.setStyleSheet("color:#e0c060; font-size:10px;")
        cmp_l.addWidget(self._cmp_lbl)
        rl.addWidget(cmp_box)

        spl.addWidget(right)
        spl.setSizes([360, 620])
        root.addWidget(spl, 1)

        # Bottom
        bot = QHBoxLayout()
        btn_apply = QPushButton("✔ Zastosuj wybrany profil do projektu")
        btn_apply.setStyleSheet("background:#1a4a8f;color:white;padding:4px 12px;")
        btn_apply.clicked.connect(self._apply_profile)
        bot.addWidget(btn_apply)
        bot.addStretch()
        self._applied_lbl = QLabel()
        self._applied_lbl.setStyleSheet("color:#40b060; font-size:10px;")
        bot.addWidget(self._applied_lbl)
        bot.addStretch()
        btn_close = QPushButton("Zamknij")
        btn_close.clicked.connect(self.reject)
        bot.addWidget(btn_close)
        root.addLayout(bot)

        self._loading = False

    # ── Data ─────────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        self._prof_table.setRowCount(0)
        _TIER_CLR = {
            "Standard":     "#1a3a1a",
            "Advanced":     "#1a2a3a",
            "HDI":          "#2a1a3a",
            "Hobbyist":     "#2a2a1a",
            "Professional": "#3a1a1a",
            "Prototype":    "#1a2a2a",
        }
        for p in self._profiles:
            row = self._prof_table.rowCount()
            self._prof_table.insertRow(row)
            self._prof_table.setItem(row, COL_NAME,  QTableWidgetItem(p.name))
            self._prof_table.setItem(row, COL_FAB,   QTableWidgetItem(p.fab))
            self._prof_table.setItem(row, COL_TIER,  QTableWidgetItem(p.tier))
            self._prof_table.setItem(row, COL_TRACE, QTableWidgetItem(f"{p.min_trace_mm:.3f}"))
            self._prof_table.setItem(row, COL_CLR,   QTableWidgetItem(f"{p.min_clearance_mm:.3f}"))
            self._prof_table.setItem(row, COL_VIA,   QTableWidgetItem(f"{p.min_via_drill_mm:.3f}"))
            bg = QBrush(QColor(_TIER_CLR.get(p.tier, "#1a1a1a")))
            for c in range(6):
                it = self._prof_table.item(row, c)
                if it:
                    it.setBackground(bg)

    def _on_sel(self) -> None:
        idx = self._prof_table.currentRow()
        if idx < 0 or idx >= len(self._profiles):
            return
        self._sel = idx
        self._load_profile(self._profiles[idx])

    def _load_profile(self, p: DRCProfile) -> None:
        self._loading = True
        self._e_name.setText(p.name)
        self._e_fab.setText(p.fab)
        self._e_tier.setText(p.tier)
        self._e_url.setText(p.url)
        self._e_notes.setPlainText(p.notes)
        for attr, _, _ in _FIELDS:
            self._spins[attr].setValue(getattr(p, attr))
        self._loading = False
        self._update_comparison(p)

    def _save(self) -> None:
        if self._loading or self._sel < 0 or self._sel >= len(self._profiles):
            return
        p = self._profiles[self._sel]
        p.name  = self._e_name.text()
        p.fab   = self._e_fab.text()
        p.tier  = self._e_tier.text()
        p.url   = self._e_url.text()
        p.notes = self._e_notes.toPlainText()
        for attr, _, _ in _FIELDS:
            setattr(p, attr, self._spins[attr].value())
        self._populate()
        self._update_comparison(p)

    def _update_comparison(self, p: DRCProfile) -> None:
        try:
            from src.validators.pcb_drc import PCBValidator
            cur = DRCProfile(
                name="current", fab="", tier="",
                min_trace_mm=PCBValidator.MIN_TRACE_WIDTH_MM,
                min_clearance_mm=PCBValidator.MIN_CLEARANCE_MM,
                min_via_drill_mm=PCBValidator.MIN_VIA_DRILL_MM,
                min_via_annular_mm=PCBValidator.MIN_VIA_ANNULAR_MM,
                min_edge_clearance_mm=PCBValidator.MIN_EDGE_CLEARANCE,
            )
            issues = p.check_vs_profile(cur)
            if issues:
                self._cmp_lbl.setText(
                    "⚠ Bieżące ustawienia DRC są mniej restrykcyjne od profilu:\n"
                    + "\n".join(f"  • {i}" for i in issues)
                )
            else:
                self._cmp_lbl.setText(
                    "✔ Bieżące ustawienia DRC spełniają wymagania tego profilu."
                )
        except Exception:
            self._cmp_lbl.setText("(Nie można odczytać bieżących ustawień DRC)")

    def _add_profile(self) -> None:
        p = DRCProfile(name="Nowy profil", fab="Custom", tier="Standard")
        self._profiles.append(p)
        self._populate()
        self._prof_table.selectRow(len(self._profiles) - 1)

    def _dup_profile(self) -> None:
        if self._sel < 0:
            return
        import copy
        np_ = copy.deepcopy(self._profiles[self._sel])
        np_.name += " (kopia)"
        self._profiles.append(np_)
        self._populate()
        self._prof_table.selectRow(len(self._profiles) - 1)

    def _del_profile(self) -> None:
        if len(self._profiles) <= 1:
            QMessageBox.warning(self, "Błąd", "Musi istnieć co najmniej jeden profil.")
            return
        self._profiles.pop(self._sel)
        self._sel = max(0, self._sel - 1)
        self._populate()
        self._prof_table.selectRow(self._sel)

    def _apply_profile(self) -> None:
        if self._sel < 0 or self._sel >= len(self._profiles):
            return
        p = self._profiles[self._sel]
        try:
            from src.validators.pcb_drc import PCBValidator
            PCBValidator.MIN_TRACE_WIDTH_MM  = p.min_trace_mm
            PCBValidator.MIN_CLEARANCE_MM    = p.min_clearance_mm
            PCBValidator.MIN_VIA_DRILL_MM    = p.min_via_drill_mm
            PCBValidator.MIN_VIA_ANNULAR_MM  = p.min_via_annular_mm
            PCBValidator.MIN_EDGE_CLEARANCE  = p.min_edge_clearance_mm
        except Exception:
            pass
        self._applied_lbl.setText(f"✔ Zastosowano: {p.name}")
        QMessageBox.information(
            self, "Profil zastosowany",
            f"Reguły DRC zaktualizowane dla profilu:\n{p.name} ({p.fab})\n\n"
            f"Min. ścieżka:   {p.min_trace_mm:.3f} mm\n"
            f"Min. prześwit:  {p.min_clearance_mm:.3f} mm\n"
            f"Min. via drill: {p.min_via_drill_mm:.3f} mm\n"
            f"Min. pierścień: {p.min_via_annular_mm:.3f} mm\n"
            f"Min. od krawędzi: {p.min_edge_clearance_mm:.3f} mm"
        )

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj profile DRC", "", "JSON (*.json)")
        if path:
            data = [p.to_dict() for p in self._profiles]
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importuj profile DRC", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._profiles = [DRCProfile.from_dict(d) for d in data]
            self._populate()
            self._prof_table.selectRow(0)
        except Exception as e:
            QMessageBox.warning(self, "Błąd", str(e))
