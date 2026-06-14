"""Gerber RS-274X + Excellon drill file generator.

Generates production-ready PCB files from a PCBBoard model:
  - F.Cu.gbr, B.Cu.gbr  — copper layers
  - F.SilkS.gbr, B.SilkS.gbr
  - F.Mask.gbr, B.Mask.gbr
  - Edge.Cuts.gbr        — board outline
  - drill.drl            — Excellon drill file (vias + through-hole pads)
"""
from __future__ import annotations
import math
import os
from pathlib import Path
from datetime import datetime

from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine, CopperZone
from src.core.models.component import Component, Pad


_LAYERS = {
    "F.Cu":    "GTL",   # Top copper
    "B.Cu":    "GBL",   # Bottom copper
    "F.SilkS": "GTO",   # Top silkscreen
    "B.SilkS": "GBO",
    "F.Mask":  "GTS",   # Top soldermask
    "B.Mask":  "GBS",
    "Edge.Cuts": "GKO", # Board outline
}


def _mm2int(mm: float) -> int:
    """Convert mm to Gerber integer (6 decimal places = 1nm resolution)."""
    return int(round(mm * 1_000_000))


def _gerber_header(title: str, layer: str) -> list[str]:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return [
        "G04 ElectroVision Gerber output *",
        f"G04 Layer: {layer} *",
        f"G04 Generated: {ts} *",
        "%FSLAX46Y46*%",   # Format spec: absolute, 4.6 (6 decimal places)
        "%MOMM*%",          # Mode: millimeters
        f"%TF.GenerationSoftware,ElectroVision,1.0*%",
        f"%TF.CreationDate,{ts}*%",
        f"%TF.ProjectId,{title},00000000-0000-0000-0000-000000000000,*%",
        f"%TF.SameCoordinates,Original*%",
        f"%TF.FileFunction,{layer}*%",
    ]


def _gerber_footer() -> list[str]:
    return ["M02*"]


def _aperture_circle(idx: int, diam_mm: float) -> str:
    return f"%ADD{idx}C,{diam_mm:.6f}*%"


def _aperture_rect(idx: int, w: float, h: float) -> str:
    return f"%ADD{idx}R,{w:.6f}X{h:.6f}*%"


def _aperture_oblong(idx: int, w: float, h: float) -> str:
    return f"%ADD{idx}O,{w:.6f}X{h:.6f}*%"


class GerberGenerator:
    def __init__(self, board: PCBBoard, project_name: str = "project"):
        self._board = board
        self._name  = project_name

    def export_all(self, output_dir: str) -> list[str]:
        """Generate all Gerber + drill files. Returns list of created file paths."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        files = []
        bb = self._board.bounding_box

        layer_map = {
            "F.Cu":    "F_Cu.gbr",
            "B.Cu":    "B_Cu.gbr",
            "F.SilkS": "F_SilkS.gbr",
            "B.SilkS": "B_SilkS.gbr",
            "F.Mask":  "F_Mask.gbr",
            "B.Mask":  "B_Mask.gbr",
            "Edge.Cuts": "Edge_Cuts.gbr",
        }

        for layer, fname in layer_map.items():
            path = out / f"{self._name}-{fname}"
            self._write_copper_layer(str(path), layer, bb)
            files.append(str(path))

        # Drill file
        drill_path = out / f"{self._name}-PTH.drl"
        self._write_drill(str(drill_path), bb)
        files.append(str(drill_path))

        # Fabrication notes
        notes_path = out / "fabrication_notes.txt"
        self._write_fab_notes(str(notes_path))
        files.append(str(notes_path))

        return files

    # ── Per-layer ─────────────────────────────────────────────────────────────

    def _write_copper_layer(self, path: str, layer: str, bb: tuple) -> None:
        lines = _gerber_header(self._name, _LAYERS.get(layer, layer))
        apertures: dict[float, int] = {}  # width → aperture id
        next_ap = 10

        def get_ap(width: float) -> int:
            nonlocal next_ap
            if width not in apertures:
                apertures[width] = next_ap
                next_ap += 1
            return apertures[width]

        # Pre-collect all widths
        widths_needed: set[float] = set()
        if layer in ("F.Cu", "B.Cu"):
            for t in self._board.traces:
                if t.layer == layer:
                    widths_needed.add(round(t.width, 6))
            # Pad widths
            for comp in self._board.components:
                if comp.layer == layer or layer == "F.Cu":
                    for p in comp.pads:
                        widths_needed.add(round(max(p.width, p.height), 6))

        if layer in ("Edge.Cuts",):
            for gl in self._board.graphic_lines:
                if gl.layer == layer:
                    widths_needed.add(round(gl.width or 0.05, 6))

        # Silkscreen component outlines
        if layer in ("F.SilkS", "B.SilkS"):
            widths_needed.add(0.12)

        widths_needed.add(0.10)  # default

        # Emit aperture definitions
        for w in sorted(widths_needed):
            idx = get_ap(w)
            lines.append(_aperture_circle(idx, w))

        lines.append("G01*")   # Linear interpolation mode

        # ── Traces ────────────────────────────────────────────────────────────
        if layer in ("F.Cu", "B.Cu"):
            cur_ap = -1
            for t in self._board.traces:
                if t.layer != layer:
                    continue
                ap = get_ap(round(t.width, 6))
                if ap != cur_ap:
                    lines.append(f"D{ap:02d}*")
                    cur_ap = ap
                x1 = _mm2int(t.x1 - bb[0])
                y1 = _mm2int(t.y1 - bb[1])
                x2 = _mm2int(t.x2 - bb[0])
                y2 = _mm2int(t.y2 - bb[1])
                lines.append(f"X{x1}Y{y1}D02*")   # move
                lines.append(f"X{x2}Y{y2}D01*")   # draw

            # Vias (both sides)
            via_ap = get_ap(0.10)
            for v in self._board.vias:
                vx = _mm2int(v.x - bb[0])
                vy = _mm2int(v.y - bb[1])
                pad_d = v.size
                # Flash via pad
                ap = get_ap(round(pad_d, 6))
                lines.append(f"D{ap:02d}*")
                lines.append(f"X{vx}Y{vy}D03*")  # flash

            # Component pads
            for comp in self._board.components:
                comp_layer = comp.layer if comp.layer else "F.Cu"
                if layer == "F.Cu" and comp_layer != "F.Cu":
                    continue
                if layer == "B.Cu" and comp_layer != "B.Cu":
                    continue
                for p in comp.pads:
                    px = _mm2int((comp.x + p.x) - bb[0])
                    py = _mm2int((comp.y + p.y) - bb[1])
                    w = round(max(p.width, 0.1), 6)
                    ap = get_ap(w)
                    lines.append(f"D{ap:02d}*")
                    lines.append(f"X{px}Y{py}D03*")

            # Copper pour zones — G36/G37 region fills
            for zone in self._board.zones:
                if zone.layer != layer or len(zone.points) < 3:
                    continue
                ap = get_ap(0.01)
                lines.append(f"D{ap:02d}*")
                lines.append("G36*")
                pts = zone.points
                x0 = _mm2int(pts[0][0] - bb[0])
                y0 = _mm2int(pts[0][1] - bb[1])
                lines.append(f"X{x0}Y{y0}D02*")
                for pt in pts[1:]:
                    xi = _mm2int(pt[0] - bb[0])
                    yi = _mm2int(pt[1] - bb[1])
                    lines.append(f"X{xi}Y{yi}D01*")
                lines.append(f"X{x0}Y{y0}D01*")  # close polygon
                lines.append("G37*")

        # ── Silkscreen: component outlines ────────────────────────────────────
        if layer in ("F.SilkS", "B.SilkS"):
            comp_layer = "F.Cu" if layer == "F.SilkS" else "B.Cu"
            silk_ap = get_ap(0.12)
            lines.append(f"D{silk_ap:02d}*")
            box = 1.5  # mm half-size
            for comp in self._board.components:
                if (comp.layer or "F.Cu") != comp_layer:
                    continue
                cx = comp.x - bb[0]
                cy = comp.y - bb[1]
                # draw box
                corners = [
                    (cx - box, cy - box), (cx + box, cy - box),
                    (cx + box, cy + box), (cx - box, cy + box),
                    (cx - box, cy - box),
                ]
                first = True
                for (x, y) in corners:
                    code = "D02" if first else "D01"
                    lines.append(f"X{_mm2int(x)}Y{_mm2int(y)}{code}*")
                    first = False

        # ── Soldermask: pads opening ──────────────────────────────────────────
        if layer in ("F.Mask", "B.Mask"):
            comp_layer = "F.Cu" if layer == "F.Mask" else "B.Cu"
            expand = 0.05  # 0.05mm mask expansion
            for comp in self._board.components:
                if (comp.layer or "F.Cu") != comp_layer:
                    continue
                for p in comp.pads:
                    px = _mm2int((comp.x + p.x) - bb[0])
                    py = _mm2int((comp.y + p.y) - bb[1])
                    w = round(p.width + 2*expand, 6)
                    ap = get_ap(w)
                    lines.append(f"D{ap:02d}*")
                    lines.append(f"X{px}Y{py}D03*")
            # Via mask openings
            for v in self._board.vias:
                vx = _mm2int(v.x - bb[0])
                vy = _mm2int(v.y - bb[1])
                ap = get_ap(round(v.size + 2*expand, 6))
                lines.append(f"D{ap:02d}*")
                lines.append(f"X{vx}Y{vy}D03*")

        # ── Edge.Cuts / Graphic Lines ─────────────────────────────────────────
        if layer == "Edge.Cuts":
            edge_lines = [l for l in self._board.graphic_lines if l.layer == "Edge.Cuts"]
            # If no explicit edge lines, draw bounding box
            if not edge_lines:
                w_mm = self._board.width_mm
                h_mm = self._board.height_mm
                outline = [
                    (0, 0, w_mm, 0), (w_mm, 0, w_mm, h_mm),
                    (w_mm, h_mm, 0, h_mm), (0, h_mm, 0, 0),
                ]
                ap = get_ap(0.05)
                lines.append(f"D{ap:02d}*")
                for (x1, y1, x2, y2) in outline:
                    lines.append(f"X{_mm2int(x1)}Y{_mm2int(y1)}D02*")
                    lines.append(f"X{_mm2int(x2)}Y{_mm2int(y2)}D01*")
            else:
                cur_ap = -1
                for gl in edge_lines:
                    ap = get_ap(round(gl.width or 0.05, 6))
                    if ap != cur_ap:
                        lines.append(f"D{ap:02d}*")
                        cur_ap = ap
                    x1 = _mm2int(gl.x1 - bb[0])
                    y1 = _mm2int(gl.y1 - bb[1])
                    x2 = _mm2int(gl.x2 - bb[0])
                    y2 = _mm2int(gl.y2 - bb[1])
                    lines.append(f"X{x1}Y{y1}D02*")
                    lines.append(f"X{x2}Y{y2}D01*")

        elif layer not in ("F.Cu", "B.Cu", "F.SilkS", "B.SilkS",
                           "F.Mask", "B.Mask", "Edge.Cuts"):
            # Other graphic lines
            cur_ap = -1
            for gl in self._board.graphic_lines:
                if gl.layer != layer:
                    continue
                ap = get_ap(round(gl.width or 0.1, 6))
                if ap != cur_ap:
                    lines.append(f"D{ap:02d}*")
                    cur_ap = ap
                lines.append(f"X{_mm2int(gl.x1-bb[0])}Y{_mm2int(gl.y1-bb[1])}D02*")
                lines.append(f"X{_mm2int(gl.x2-bb[0])}Y{_mm2int(gl.y2-bb[1])}D01*")

        lines.extend(_gerber_footer())
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    # ── Drill file ────────────────────────────────────────────────────────────

    def _write_drill(self, path: str, bb: tuple) -> None:
        """Excellon drill file for vias and through-hole pads."""
        # Collect drill sizes
        drills: dict[float, list[tuple[float, float]]] = {}

        # Vias
        for v in self._board.vias:
            d = round(v.drill, 3)
            drills.setdefault(d, []).append((v.x - bb[0], v.y - bb[1]))

        # Through-hole pads
        for comp in self._board.components:
            for p in comp.pads:
                if p.drill > 0:
                    d = round(p.drill, 3)
                    x = comp.x + p.x - bb[0]
                    y = comp.y + p.y - bb[1]
                    drills.setdefault(d, []).append((x, y))

        lines = [
            "M48",
            "; DRILL file — ElectroVision",
            f"; Generated: {datetime.now().isoformat()}",
            "METRIC,LZ",
            "FMAT,2",
        ]

        tool_map: dict[float, int] = {}
        for i, d in enumerate(sorted(drills.keys()), start=1):
            lines.append(f"T{i:02d}C{d:.3f}")
            tool_map[d] = i

        lines.append("%")

        for d, holes in sorted(drills.items()):
            tool = tool_map[d]
            lines.append(f"T{tool:02d}")
            for (x, y) in holes:
                xi = int(round(x * 1000))
                yi = int(round(y * 1000))
                lines.append(f"X{xi:06d}Y{yi:06d}")

        lines.append("T00")
        lines.append("M30")
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    # ── Fab notes ─────────────────────────────────────────────────────────────

    def _write_fab_notes(self, path: str) -> None:
        board = self._board
        Path(path).write_text(
            f"ElectroVision — Fabrication Notes\n"
            f"Project: {self._name}\n"
            f"Generated: {datetime.now().isoformat()}\n\n"
            f"BOARD SPECIFICATIONS\n"
            f"  Dimensions:   {board.width_mm:.2f} x {board.height_mm:.2f} mm\n"
            f"  Layers:       {len(board.layers)} ({', '.join(l.name for l in board.layers if 'Cu' in l.name)})\n"
            f"  Components:   {len(board.components)}\n"
            f"  Vias:         {len(board.vias)}\n"
            f"  Nets:         {len(board.nets)}\n\n"
            f"RECOMMENDED MANUFACTURING PARAMETERS\n"
            f"  Board thickness: 1.6mm (FR4)\n"
            f"  Copper weight:   1oz (35µm)\n"
            f"  Surface finish:  HASL or ENIG\n"
            f"  Min track/space: 0.1mm / 0.1mm\n"
            f"  Min via drill:   0.3mm\n"
            f"  Min annular:     0.15mm\n\n"
            f"FILES INCLUDED\n"
            f"  *-F_Cu.gbr     — Top copper\n"
            f"  *-B_Cu.gbr     — Bottom copper\n"
            f"  *-F_SilkS.gbr  — Top silkscreen\n"
            f"  *-B_SilkS.gbr  — Bottom silkscreen\n"
            f"  *-F_Mask.gbr   — Top soldermask\n"
            f"  *-B_Mask.gbr   — Bottom soldermask\n"
            f"  *-Edge_Cuts.gbr — Board outline\n"
            f"  *-PTH.drl      — Through-hole drill\n",
            encoding="utf-8",
        )
