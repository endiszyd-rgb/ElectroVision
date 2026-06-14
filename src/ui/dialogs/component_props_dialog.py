"""Component Properties Dialog — edit reference, value, footprint, position, rotation, layer."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QDoubleSpinBox, QComboBox, QPushButton, QLabel,
    QDialogButtonBox, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from src.core.models.component import Component


_LAYERS = ["F.Cu", "B.Cu"]


class ComponentPropsDialog(QDialog):
    """Modal dialog for editing a component's properties."""

    props_changed = Signal(object, dict)   # (component, new_props_dict)

    def __init__(self, comp: Component, parent=None) -> None:
        super().__init__(parent)
        self._comp = comp
        self.setWindowTitle(f"Właściwości — {comp.reference}")
        self.setMinimumWidth(420)
        self._build_ui()
        self._populate(comp)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Identity ──────────────────────────────────────────────────────────
        id_group = QGroupBox("Identyfikacja")
        id_form  = QFormLayout(id_group)
        id_form.setSpacing(6)

        self._ref  = QLineEdit()
        self._val  = QLineEdit()
        self._fp   = QLineEdit()
        self._fp.setPlaceholderText("np. Resistor_SMD:R_0402_1005Metric")

        id_form.addRow("Oznaczenie (Ref):", self._ref)
        id_form.addRow("Wartość:", self._val)
        id_form.addRow("Footprint:", self._fp)
        root.addWidget(id_group)

        # ── Position ──────────────────────────────────────────────────────────
        pos_group = QGroupBox("Położenie")
        pos_form  = QFormLayout(pos_group)
        pos_form.setSpacing(6)

        self._x   = self._spin(-9999, 9999, 3, "mm")
        self._y   = self._spin(-9999, 9999, 3, "mm")
        self._rot = self._spin(0, 359.999, 2, "°")
        self._rot.setWrapping(True)

        self._layer = QComboBox()
        self._layer.addItems(_LAYERS)

        pos_form.addRow("X:", self._x)
        pos_form.addRow("Y:", self._y)
        pos_form.addRow("Rotacja:", self._rot)
        pos_form.addRow("Warstwa:", self._layer)
        root.addWidget(pos_group)

        # ── Quick actions ─────────────────────────────────────────────────────
        act_row = QHBoxLayout()
        for label, slot in [
            ("Obróć +90°", self._rotate_90),
            ("Obróć -90°", self._rotate_m90),
            ("Lustro (F↔B)", self._mirror_layer),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            act_row.addWidget(btn)
        root.addLayout(act_row)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _spin(self, lo: float, hi: float, dec: int, suffix: str) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(dec)
        sb.setSuffix(f" {suffix}")
        sb.setSingleStep(0.1)
        return sb

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self, c: Component) -> None:
        self._ref.setText(c.reference or "")
        self._val.setText(c.value or "")
        self._fp.setText(getattr(c, "footprint", "") or "")
        self._x.setValue(c.x or 0.0)
        self._y.setValue(c.y or 0.0)
        self._rot.setValue(getattr(c, "rotation", 0.0) or 0.0)
        layer = getattr(c, "layer", "F.Cu") or "F.Cu"
        idx = self._layer.findText(layer)
        if idx >= 0:
            self._layer.setCurrentIndex(idx)

    # ── Quick actions ─────────────────────────────────────────────────────────

    def _rotate_90(self) -> None:
        self._rot.setValue((self._rot.value() + 90.0) % 360.0)

    def _rotate_m90(self) -> None:
        self._rot.setValue((self._rot.value() - 90.0) % 360.0)

    def _mirror_layer(self) -> None:
        cur = self._layer.currentText()
        self._layer.setCurrentText("B.Cu" if cur == "F.Cu" else "F.Cu")

    # ── Accept ────────────────────────────────────────────────────────────────

    def _on_ok(self) -> None:
        new_props = {
            "reference": self._ref.text().strip() or self._comp.reference,
            "value":     self._val.text().strip(),
            "footprint": self._fp.text().strip(),
            "x":         self._x.value(),
            "y":         self._y.value(),
            "rotation":  self._rot.value(),
            "layer":     self._layer.currentText(),
        }
        self.props_changed.emit(self._comp, new_props)
        self.accept()

    # ── Result helpers ────────────────────────────────────────────────────────

    def result_props(self) -> dict | None:
        """Returns the last accepted props dict, or None if cancelled."""
        return self._last_props if hasattr(self, "_last_props") else None
