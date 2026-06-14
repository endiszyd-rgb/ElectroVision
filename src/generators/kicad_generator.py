"""KiCad PCB Generator — creates real .kicad_pcb files from Python model."""
from __future__ import annotations
import math
import time
from pathlib import Path
from typing import List, Tuple


def _ts() -> str:
    return str(int(time.time()))


class KiCadGenerator:
    """
    Generates a valid .kicad_pcb S-expression file from component and trace data.

    Input format (dict):
        board_width, board_height  — mm
        title                      — project title string
        components: list of dicts:
            ref, value, x, y, angle (°), layer ("F.Cu"/"B.Cu"), footprint
            pads: list of {number, net, x_off, y_off, w, h, type("smd"/"thru_hole")}
        traces: list of dicts:
            x1, y1, x2, y2, net, width, layer ("F.Cu"/"B.Cu")
        vias: list of dicts:
            x, y, drill, size, net
        zones: list of dicts (optional):
            layer, net, points: [(x,y), ...]
    """

    def __init__(self, data: dict) -> None:
        self._d = data
        self._net_names: dict[str, int] = {}
        self._net_counter = 1

    # ── public ──────────────────────────────────────────────────────────────────

    def generate(self, output_path: str) -> str:
        self._collect_nets()
        s = self._build_file()
        Path(output_path).write_text(s, encoding="utf-8")
        return output_path

    # ── net index ────────────────────────────────────────────────────────────────

    def _net_id(self, name: str) -> int:
        if not name or name.strip() == "":
            return 0
        if name not in self._net_names:
            self._net_names[name] = self._net_counter
            self._net_counter += 1
        return self._net_names[name]

    def _collect_nets(self) -> None:
        for comp in self._d.get("components", []):
            for pad in comp.get("pads", []):
                self._net_id(pad.get("net", ""))
        for trace in self._d.get("traces", []):
            self._net_id(trace.get("net", ""))
        for via in self._d.get("vias", []):
            self._net_id(via.get("net", ""))

    # ── file builder ─────────────────────────────────────────────────────────────

    def _build_file(self) -> str:
        d = self._d
        w = float(d.get("board_width", 100))
        h = float(d.get("board_height", 80))
        title = d.get("title", "ElectroVision Project")
        ts = _ts()

        lines: list[str] = []
        lines.append(f'(kicad_pcb (version 20231120) (generator "electrovision")')
        lines.append(f'  (general')
        lines.append(f'    (thickness 1.6)')
        lines.append(f'    (legacy_teardrops no)')
        lines.append(f'  )')
        lines.append(f'  (paper "A4")')
        lines.append(f'  (title_block')
        lines.append(f'    (title "{title}")')
        lines.append(f'    (date "{time.strftime("%Y-%m-%d")}")')
        lines.append(f'    (rev "1.0")')
        lines.append(f'    (company "ElectroVision")')
        lines.append(f'  )')
        lines.append(f'  (layers')
        for layer_id, name, ltype in _STANDARD_LAYERS:
            lines.append(f'    ({layer_id} "{name}" {ltype})')
        lines.append(f'  )')
        lines.append(f'  (setup')
        lines.append(f'    (pad_to_mask_clearance 0)')
        lines.append(f'    (pcbplotparams')
        lines.append(f'      (layerselection 0x00010fc_ffffffff)')
        lines.append(f'      (outputdirectory "gerbers/")')
        lines.append(f'      (disableapertmacros no)')
        lines.append(f'      (usegerberextensions no)')
        lines.append(f'      (usegerberattributes yes)')
        lines.append(f'      (usegerberadvancedattributes yes)')
        lines.append(f'      (creategerberjobfile yes)')
        lines.append(f'      (plotframeref no)')
        lines.append(f'      (viasonmask no)')
        lines.append(f'      (mode 1)')
        lines.append(f'      (useauxorigin no)')
        lines.append(f'      (hpglpennumber 1)')
        lines.append(f'      (hpglpenspeed 20)')
        lines.append(f'      (hpglpendiameter 15.000000)')
        lines.append(f'      (dxfpolygonmode yes)')
        lines.append(f'      (dxfimperialunits yes)')
        lines.append(f'      (dxfusepcbnewfont yes)')
        lines.append(f'      (psnegative no)')
        lines.append(f'      (psa4output no)')
        lines.append(f'      (plotreference yes)')
        lines.append(f'      (plotvalue yes)')
        lines.append(f'      (plotfptext yes)')
        lines.append(f'      (plotinvisibletext no)')
        lines.append(f'      (sketchpadsonfab no)')
        lines.append(f'      (subtractmaskfromsilk no)')
        lines.append(f'      (outputformat 1)')
        lines.append(f'      (mirror no)')
        lines.append(f'      (drillshape 1)')
        lines.append(f'      (scaleselection 1)')
        lines.append(f'      (outputdirectory "gerbers/")')
        lines.append(f'    )')
        lines.append(f'  )')

        # Nets
        lines.append(f'  (net 0 "")')
        for name, idx in sorted(self._net_names.items(), key=lambda x: x[1]):
            lines.append(f'  (net {idx} "{name}")')

        # Board outline (Edge.Cuts)
        cx = w / 2.0
        cy = h / 2.0
        lines.append(f'  (gr_rect (start 0 0) (end {w:.3f} {h:.3f})')
        lines.append(f'    (stroke (width 0.05) (type default))')
        lines.append(f'    (layer "Edge.Cuts"))')

        # Components / footprints
        for comp in d.get("components", []):
            lines.extend(self._footprint(comp))

        # Traces
        for t in d.get("traces", []):
            net_id = self._net_id(t.get("net", ""))
            x1 = float(t.get("x1", 0))
            y1 = float(t.get("y1", 0))
            x2 = float(t.get("x2", 0))
            y2 = float(t.get("y2", 0))
            lyr = t.get("layer", "F.Cu")
            wid = float(t.get("width", 0.25))
            lines.append(
                f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f})'
                f' (width {wid:.3f}) (layer "{lyr}") (net {net_id}) (tstamp {ts}))'
            )

        # Vias
        for v in d.get("vias", []):
            net_id = self._net_id(v.get("net", ""))
            x = float(v.get("x", 0))
            y = float(v.get("y", 0))
            sz = float(v.get("size", 0.8))
            dr = float(v.get("drill", 0.4))
            lines.append(
                f'  (via (at {x:.3f} {y:.3f}) (size {sz:.3f}) (drill {dr:.3f})'
                f' (layers "F.Cu" "B.Cu") (net {net_id}) (tstamp {ts}))'
            )

        lines.append(")")
        return "\n".join(lines) + "\n"

    def _footprint(self, comp: dict) -> list[str]:
        ref   = comp.get("ref", "U1")
        val   = comp.get("value", "")
        x     = float(comp.get("x", 50))
        y     = float(comp.get("y", 40))
        angle = float(comp.get("angle", 0))
        layer = comp.get("layer", "F.Cu")
        fp    = comp.get("footprint", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
        ts    = _ts()
        fab   = "F.Fab" if layer == "F.Cu" else "B.Fab"
        silk  = "F.SilkS" if layer == "F.Cu" else "B.SilkS"
        crt   = "F.CrtYd" if layer == "F.Cu" else "B.CrtYd"

        lines = [
            f'  (footprint "{fp}"',
            f'    (layer "{layer}")',
            f'    (tstamp {ts})',
            f'    (at {x:.3f} {y:.3f}{f" {angle:.1f}" if angle else ""})',
            f'    (descr "")',
            f'    (tags "")',
            f'    (property "Reference" "{ref}" (at 0 -3 0) (layer "{silk}") (uuid {ts}r)',
            f'      (effects (font (size 1 1) (thickness 0.15))))',
            f'    (property "Value" "{val}" (at 0 3 0) (layer "{fab}") (uuid {ts}v)',
            f'      (effects (font (size 1 1) (thickness 0.15))))',
        ]

        # Pads
        for pad in comp.get("pads", []):
            lines.extend(self._pad(pad, ts))

        # Courtyard
        cw = float(comp.get("crtyd_w", 4.0))
        ch = float(comp.get("crtyd_h", 4.0))
        lines.append(
            f'    (fp_rect (start {-cw/2:.2f} {-ch/2:.2f}) (end {cw/2:.2f} {ch/2:.2f})'
            f' (stroke (width 0.05) (type default)) (layer "{crt}") (uuid {ts}c))'
        )
        lines.append("  )")
        return lines

    def _pad(self, pad: dict, ts: str) -> list[str]:
        num    = pad.get("number", "1")
        net    = pad.get("net", "")
        net_id = self._net_id(net)
        xo     = float(pad.get("x_off", 0))
        yo     = float(pad.get("y_off", 0))
        pw     = float(pad.get("w", 1.6))
        ph     = float(pad.get("h", 1.6))
        ptype  = pad.get("type", "thru_hole")
        shape  = pad.get("shape", "circle" if ptype == "thru_hole" else "rect")
        drill  = pad.get("drill", 0.8) if ptype == "thru_hole" else None

        lines = [
            f'    (pad "{num}" {ptype} {shape}',
            f'      (at {xo:.3f} {yo:.3f})',
            f'      (size {pw:.3f} {ph:.3f})',
        ]
        if drill:
            lines.append(f'      (drill {float(drill):.3f})')
        layers = _pad_layers(ptype)
        lines.append(f'      (layers {layers})')
        if net_id:
            lines.append(f'      (net {net_id} "{net}")')
        lines.append(f'      (uuid {ts}p{num}))')
        return lines


def _pad_layers(ptype: str) -> str:
    if ptype == "thru_hole":
        return '"*.Cu" "*.Mask"'
    return '"F.Cu" "F.Paste" "F.Mask"'


_STANDARD_LAYERS = [
    (0,  "F.Cu",       "signal"),
    (1,  "In1.Cu",     "signal"),
    (2,  "In2.Cu",     "signal"),
    (31, "B.Cu",       "signal"),
    (32, "B.Adhes",    "user"),
    (33, "F.Adhes",    "user"),
    (34, "B.Paste",    "user"),
    (35, "F.Paste",    "user"),
    (36, "B.SilkS",    "user"),
    (37, "F.SilkS",    "user"),
    (38, "B.Mask",     "user"),
    (39, "F.Mask",     "user"),
    (40, "Dwgs.User",  "user"),
    (41, "Cmts.User",  "user"),
    (42, "Eco1.User",  "user"),
    (43, "Eco2.User",  "user"),
    (44, "Edge.Cuts",  "user"),
    (45, "Margin",     "user"),
    (46, "B.CrtYd",    "user"),
    (47, "F.CrtYd",    "user"),
    (48, "B.Fab",      "user"),
    (49, "F.Fab",      "user"),
]
