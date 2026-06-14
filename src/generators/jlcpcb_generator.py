"""JLCPCB / PCBWay production export.

Generates a ready-to-order ZIP containing:
  - All Gerber + Drill files (via GerberGenerator)
  - BOM.csv  — JLCPCB BOM format (Comment, Designator, Footprint, LCSC Part #)
  - CPL.csv  — Component Placement List (Designator, Mid X, Mid Y, Layer, Rotation)
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

from src.core.models.pcb_board import PCBBoard
from src.core.models.component import Component


def _lcsc(comp: Component) -> str:
    """Extract LCSC part number from component, if available."""
    # Check properties dict first (KiCad sometimes stores LCSC here)
    for key in ("LCSC", "LCSC Part", "lcsc", "LCSC_PN", "JLC_PN"):
        if key in comp.properties:
            return comp.properties[key]
    # manufacturer_pn starting with 'C' is likely LCSC (e.g. C14663)
    pn = comp.manufacturer_pn or ""
    if pn.upper().startswith("C") and pn[1:].isdigit():
        return pn
    return ""


def _layer_label(layer: str) -> str:
    return "Top" if layer in ("F.Cu", "F.Cu") else "Bottom"


def _group_components(board: PCBBoard) -> list[dict]:
    """Group components by (value, footprint), return sorted BOM rows."""
    groups: dict[tuple, list[Component]] = defaultdict(list)
    for comp in board.components:
        key = (comp.value or "", comp.footprint or "")
        groups[key].append(comp)

    rows = []
    for (value, footprint), comps in sorted(groups.items()):
        designators = ",".join(sorted(c.reference for c in comps))
        lcsc = _lcsc(comps[0]) if comps else ""
        rows.append({
            "Comment":     value,
            "Designator":  designators,
            "Footprint":   footprint,
            "LCSC Part #": lcsc,
            "Qty":         str(len(comps)),
        })
    return rows


def generate_bom_csv(board: PCBBoard) -> str:
    """Return JLCPCB-format BOM as CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["Comment", "Designator", "Footprint", "LCSC Part #", "Qty"],
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in _group_components(board):
        writer.writerow(row)
    return buf.getvalue()


def generate_cpl_csv(board: PCBBoard) -> str:
    """Return JLCPCB-format CPL (Component Placement List) as CSV string."""
    bb = board.bounding_box
    board_cx = (bb[0] + bb[2]) / 2
    board_cy = (bb[1] + bb[3]) / 2

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"],
        lineterminator="\r\n",
    )
    writer.writeheader()
    for comp in sorted(board.components, key=lambda c: c.reference):
        mid_x = comp.x - board_cx
        mid_y = -(comp.y - board_cy)   # JLCPCB Y axis is flipped vs KiCad
        writer.writerow({
            "Designator": comp.reference,
            "Mid X":      f"{mid_x:.4f}mm",
            "Mid Y":      f"{mid_y:.4f}mm",
            "Layer":      _layer_label(comp.layer or "F.Cu"),
            "Rotation":   f"{(comp.rotation or 0.0) % 360:.1f}",
        })
    return buf.getvalue()


class JLCPCBExporter:
    """Bundle Gerber + BOM + CPL into a single ZIP for JLCPCB/PCBWay."""

    def __init__(self, board: PCBBoard, project_name: str = "PCB"):
        self._board = board
        self._name  = project_name

    def export_zip(self, out_path: str) -> list[str]:
        """Write ZIP to out_path. Returns list of included file names."""
        from src.generators.gerber_generator import GerberGenerator

        # --- Gerber files (in-memory) ----------------------------------------
        import tempfile, shutil
        tmp_dir = tempfile.mkdtemp(prefix="ev_gerber_")
        try:
            gen = GerberGenerator(self._board, self._name)
            gerber_files = gen.export_all(tmp_dir)

            # --- BOM + CPL -------------------------------------------------------
            bom_csv = generate_bom_csv(self._board)
            cpl_csv = generate_cpl_csv(self._board)

            included: list[str] = []
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Gerber files in subfolder
                for fpath in gerber_files:
                    arcname = f"Gerber/{Path(fpath).name}"
                    zf.write(fpath, arcname)
                    included.append(arcname)

                # BOM + CPL at root
                zf.writestr(f"{self._name}_BOM.csv",  bom_csv)
                zf.writestr(f"{self._name}_CPL.csv",  cpl_csv)
                included += [f"{self._name}_BOM.csv", f"{self._name}_CPL.csv"]

                # README for JLCPCB
                zf.writestr("README.txt", _JLCPCB_README.format(name=self._name))
                included.append("README.txt")

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return included


_JLCPCB_README = """\
ElectroVision — JLCPCB/PCBWay Production Package
=================================================
Project: {name}

Contents:
  Gerber/   - All Gerber and Drill files
  *_BOM.csv - Bill of Materials (JLCPCB format with LCSC Part #)
  *_CPL.csv - Component Placement List for SMT assembly

Upload instructions (JLCPCB):
  1. Go to jlcpcb.com → Order Now
  2. Upload Gerber/ folder as a ZIP
  3. Enable SMT Assembly → upload BOM and CPL CSV files
  4. Fill in any missing LCSC Part # numbers

Generated by ElectroVision (https://github.com/endiszyd-rgb/ElectroVision)
"""
