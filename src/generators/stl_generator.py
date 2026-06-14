"""STL and STEP generator for PCB enclosures using CadQuery (or trimesh fallback).

New in v2:
- Component height database (realistic 3D heights per type/footprint)
- Automatic connector cutouts on enclosure walls (USB, DC jack, JST, headers)
- Standoff diameter/thread configurable
- Rounded-corner boxes via CadQuery .fillet()
"""
from __future__ import annotations
import math
from pathlib import Path
from src.core.models.pcb_board import PCBBoard
from src.core.models.component import Component


# ── Component height database (mm above PCB surface) ─────────────────────────

_COMP_HEIGHTS: list[tuple[list[str], float]] = [
    # keywords in (value + footprint).lower() → height_mm
    (["usb_c", "usb-c"],              3.5),
    (["usb_micro", "usb_b_micro"],    3.0),
    (["usb_mini"],                    3.2),
    (["dc_jack", "barrelj", "pwrconn"],10.0),
    (["jst_ph", "jst_xh", "jst_zh"], 4.5),
    (["pinheader", "pinhead", "conn_1x", "conn_2x", "pinhdr"], 8.5),
    (["esp32", "esp8266"],            4.0),
    (["rp2040", "stm32", "atm"],      2.5),
    (["ams1117", "lm1117", "lm78", "lm79", "sot-223"], 1.8),
    (["to-220", "to220"],             9.0),
    (["to-92", "to92"],               5.5),
    (["soic", "dip-8", "dip8"],       4.0),
    (["qfn", "lga", "dfn"],           1.2),
    (["bme280", "mpu6050", "imu"],    1.2),
    (["ssd1306"],                     3.2),
    (["sw_push", "sw_tact", "tactile", "sw_slide"], 5.0),
    (["crystal", "hc49", "y_"],       3.5),
    (["cp_radial", "elco", "electrolytic"], 10.0),
    (["c_1206", "c_0805"],            1.5),
    (["c_0603", "c_0402"],            0.8),
    (["r_0603", "r_0402", "r_0201"], 0.5),
    (["led_0402", "led_0603"],        0.8),
    (["led_th", "led_3mm", "led_5mm"], 6.0),
    (["d_sod", "d_smb", "d_sma"],    2.5),
    (["d_do-41", "d_do41"],          4.0),
    (["tb_", "term_block", "termblock"], 10.0),
]


def _comp_height(comp: Component) -> float:
    key = (comp.value + " " + comp.footprint).lower()
    for keywords, h in _COMP_HEIGHTS:
        if any(k in key for k in keywords):
            return h
    # fallback by type
    ct = comp.component_type.lower()
    if ct == "connector": return 8.0
    if ct == "ic":        return 3.0
    if ct in ("capacitor", "inductor"): return 2.0
    if ct == "transistor": return 4.0
    return 1.5   # generic SMD


def _max_component_height(board: PCBBoard) -> float:
    if not board.components:
        return 10.0
    return max(_comp_height(c) for c in board.components)


# ── Connector cutout positions ────────────────────────────────────────────────

_CONNECTOR_KEYWORDS = {
    "usb_c":    {"w": 9.0,  "h": 3.5},
    "usb-c":    {"w": 9.0,  "h": 3.5},
    "usb_micro":{"w": 8.0,  "h": 3.0},
    "usb_mini": {"w": 7.4,  "h": 4.0},
    "dc_jack":  {"w": 9.5,  "h": 9.5},
    "barrelj":  {"w": 9.5,  "h": 9.5},
    "jst_ph":   {"w": 4.5,  "h": 5.0},
    "jst_xh":   {"w": 5.0,  "h": 5.5},
}


def _connector_cutout(comp: Component):
    """Return (width_mm, height_mm) cutout for connector, or None."""
    key = (comp.value + " " + comp.footprint).lower()
    for kw, dims in _CONNECTOR_KEYWORDS.items():
        if kw in key:
            return dims
    if comp.component_type == "connector":
        return {"w": 6.0, "h": 4.0}
    return None


class STLGenerator:
    """
    Generates 3D models for a PCB and its enclosure.

    Parameters
    ----------
    board   : PCBBoard
    params  : dict
        pcb_thickness    – FR4 thickness in mm (default 1.6)
        enclosure_margin – wall offset from PCB edge in mm (default 3.0)
        enclosure_height – total inside height of enclosure in mm (default auto)
        wall_thickness   – enclosure wall thickness in mm (default 2.0)
        corner_radius    – rounded corner radius in mm (default 2.0)
        standoff_height  – PCB standoff height mm (default 3.0)
        standoff_diam    – standoff outer diameter mm (default 3.0)
        standoff_hole    – M-size hole diameter mm (default 1.5 = M3)
        gen_enclosure    – generate enclosure body (default True)
        gen_lid          – generate lid (default True)
        gen_pcb_3d       – generate PCB body (default True)
        gen_cutouts      – cut holes for edge connectors (default True)
    """

    def __init__(self, board: PCBBoard, params: dict | None = None) -> None:
        self._board  = board
        self._params = params or {}

    def _p(self, key, default):
        return self._params.get(key, default)

    # ── Geometry builders ─────────────────────────────────────────────────────

    def _board_dims(self):
        bb = self._board.bounding_box
        return max(bb[2] - bb[0], 5.0), max(bb[3] - bb[1], 5.0)

    def _auto_height(self) -> float:
        explicit = self._p("enclosure_height", None)
        if explicit:
            return float(explicit)
        pcb_th  = self._p("pcb_thickness", 1.6)
        standoff = self._p("standoff_height", 3.0)
        comp_h   = _max_component_height(self._board) + 2.0   # 2mm clearance
        return pcb_th + standoff + comp_h

    def _make_pcb_body(self, cq):
        w, h = self._board_dims()
        th = self._p("pcb_thickness", 1.6)
        return cq.Workplane("XY").box(w, h, th)

    def _make_enclosure(self, cq):
        w, h   = self._board_dims()
        mar    = self._p("enclosure_margin", 3.0)
        ht     = self._auto_height()
        wt     = self._p("wall_thickness", 2.0)
        r      = self._p("corner_radius",  2.0)
        sth    = self._p("standoff_height", 3.0)
        std_r  = self._p("standoff_diam",  3.0) / 2
        hole_r = self._p("standoff_hole",  1.5) / 2

        ow = w + 2 * (mar + wt)
        oh = h + 2 * (mar + wt)

        outer = (
            cq.Workplane("XY")
            .rect(ow, oh)
            .extrude(ht)
        )
        inner_h = max(ht - wt, 1.0)
        inner = (
            cq.Workplane("XY")
            .workplane(offset=wt)
            .rect(ow - 2 * wt, oh - 2 * wt)
            .extrude(inner_h)
        )
        enc = outer.cut(inner)

        # Apply rounded corners if requested
        try:
            if r > 0.1:
                enc = enc.edges("|Z").fillet(r)
        except Exception:
            pass

        # Standoffs (4 corners, offset from PCB edge by margin*0.5)
        off = min(w, h) * 0.45 - 1.0
        ox, oy = w / 2 - 3.5, h / 2 - 3.5
        for sx, sy in [(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)]:
            try:
                std = (
                    cq.Workplane("XY")
                    .workplane(offset=wt)
                    .center(sx, sy)
                    .circle(std_r)
                    .extrude(sth)
                )
                hle = (
                    cq.Workplane("XY")
                    .workplane(offset=wt)
                    .center(sx, sy)
                    .circle(hole_r)
                    .extrude(sth)
                )
                enc = enc.union(std).cut(hle)
            except Exception:
                pass

        # Connector cutouts on walls
        if self._p("gen_cutouts", True):
            enc = self._add_cutouts(cq, enc, w, h, ow, oh, wt, ht)

        return enc

    def _add_cutouts(self, cq, enc, w, h, ow, oh, wt, ht):
        """Add rectangular cutouts for edge connectors."""
        bb = self._board.bounding_box
        for comp in self._board.components:
            dims = _connector_cutout(comp)
            if not dims:
                continue
            # Component position relative to board centre
            cx = comp.x - (bb[0] + (bb[2] - bb[0]) / 2)
            cy = comp.y - (bb[1] + (bb[3] - bb[1]) / 2)
            cw, ch = dims["w"] + 1.0, dims["h"] + 1.0  # 0.5mm clearance each side

            # Determine which wall is closest
            dist_left  = abs(cx + w / 2)
            dist_right = abs(cx - w / 2)
            dist_front = abs(cy + h / 2)
            dist_back  = abs(cy - h / 2)
            closest    = min(dist_left, dist_right, dist_front, dist_back)

            cutout_z = ht * 0.3  # start 30% from bottom

            try:
                if closest == dist_left:
                    slot = (
                        cq.Workplane("YZ")
                        .workplane(offset=-ow / 2)
                        .center(cy, cutout_z)
                        .rect(cw, ch)
                        .extrude(wt + 1.0)
                    )
                    enc = enc.cut(slot)
                elif closest == dist_right:
                    slot = (
                        cq.Workplane("YZ")
                        .workplane(offset=ow / 2 - wt - 1.0)
                        .center(cy, cutout_z)
                        .rect(cw, ch)
                        .extrude(wt + 1.0)
                    )
                    enc = enc.cut(slot)
                elif closest == dist_front:
                    slot = (
                        cq.Workplane("XZ")
                        .workplane(offset=-oh / 2)
                        .center(cx, cutout_z)
                        .rect(cw, ch)
                        .extrude(wt + 1.0)
                    )
                    enc = enc.cut(slot)
                else:
                    slot = (
                        cq.Workplane("XZ")
                        .workplane(offset=oh / 2 - wt - 1.0)
                        .center(cx, cutout_z)
                        .rect(cw, ch)
                        .extrude(wt + 1.0)
                    )
                    enc = enc.cut(slot)
            except Exception:
                pass

        return enc

    def _make_lid(self, cq):
        w, h = self._board_dims()
        mar  = self._p("enclosure_margin", 3.0)
        wt   = self._p("wall_thickness",   2.0)
        r    = self._p("corner_radius",    2.0)

        ow = w + 2 * (mar + wt)
        oh = h + 2 * (mar + wt)
        lid_h  = wt + 1.5
        snap_h = 2.5
        snap_t = 0.8

        lid = cq.Workplane("XY").rect(ow, oh).extrude(lid_h)
        recess = (
            cq.Workplane("XY")
            .workplane(offset=wt)
            .rect(ow - 2 * wt, oh - 2 * wt)
            .extrude(lid_h - wt + 0.1)
        )
        lid = lid.cut(recess)

        snap = (
            cq.Workplane("XY")
            .workplane(offset=lid_h)
            .rect(ow - snap_t, oh - snap_t)
            .extrude(snap_h)
        )
        snap_i = (
            cq.Workplane("XY")
            .workplane(offset=lid_h)
            .rect(ow - snap_t * 3, oh - snap_t * 3)
            .extrude(snap_h)
        )
        lid = lid.union(snap.cut(snap_i))

        try:
            if r > 0.1:
                lid = lid.edges("|Z").fillet(r)
        except Exception:
            pass

        return lid

    def _build_assembly(self):
        try:
            import cadquery as cq
        except ImportError as exc:
            raise ImportError(
                "Wymagane: pip install cadquery\n"
                "CadQuery nie obsługuje Python 3.13 — użyj Python 3.11/3.12."
            ) from exc

        assembly = cq.Assembly()

        if self._p("gen_pcb_3d", True):
            assembly.add(self._make_pcb_body(cq), name="pcb",
                         color=cq.Color(0.0, 0.5, 0.1, 1.0))

        if self._p("gen_enclosure", True):
            enc = self._make_enclosure(cq)
            sth = self._p("standoff_height", 3.0)
            assembly.add(enc, name="enclosure",
                         color=cq.Color(0.3, 0.3, 0.35, 0.9),
                         loc=cq.Location(cq.Vector(0, 0, -(sth + 1.6))))

        if self._p("gen_lid", True):
            lid = self._make_lid(cq)
            ht  = self._auto_height()
            assembly.add(lid, name="lid",
                         color=cq.Color(0.4, 0.4, 0.45, 0.9),
                         loc=cq.Location(cq.Vector(0, 0, ht)))

        return assembly

    def export_step(self, path: str) -> None:
        self._build_assembly().save(path)

    def export_stl(self, path: str) -> None:
        try:
            import cadquery as cq
            shape = self._build_assembly().toCompound()
            cq.exporters.export(shape, path, cq.exporters.ExportTypes.STL)
        except ImportError:
            self._export_stl_trimesh(path)

    # ── trimesh fallback ──────────────────────────────────────────────────────

    def _export_stl_trimesh(self, path: str) -> None:
        """Fast fallback: simple box geometry via trimesh (no CadQuery needed)."""
        import trimesh
        import numpy as np

        w, h   = self._board_dims()
        th     = self._p("pcb_thickness", 1.6)
        mar    = self._p("enclosure_margin", 3.0)
        ht     = self._auto_height()
        wt     = self._p("wall_thickness", 2.0)
        sth    = self._p("standoff_height", 3.0)

        meshes = []

        if self._p("gen_pcb_3d", True):
            pcb = trimesh.creation.box(extents=[w, h, th])
            pcb.apply_translation([0, 0, th / 2])
            pcb.visual.face_colors = [30, 120, 40, 255]
            meshes.append(pcb)

        if self._p("gen_enclosure", True):
            ow = w + 2 * (mar + wt)
            oh = h + 2 * (mar + wt)
            outer = trimesh.creation.box(extents=[ow, oh, ht])
            inner = trimesh.creation.box(extents=[ow - 2 * wt, oh - 2 * wt, max(ht - wt, 1)])
            inner.apply_translation([0, 0, wt / 2])
            try:
                enc = outer.difference(inner)
            except Exception:
                enc = outer
            enc.apply_translation([0, 0, -(sth + th)])
            enc.visual.face_colors = [80, 90, 100, 230]
            meshes.append(enc)

        if self._p("gen_lid", True):
            ow  = w + 2 * (mar + wt)
            oh  = h + 2 * (mar + wt)
            lid = trimesh.creation.box(extents=[ow, oh, wt + 1.5])
            lid.apply_translation([0, 0, ht + (wt + 1.5) / 2])
            lid.visual.face_colors = [100, 110, 120, 230]
            meshes.append(lid)

        if not meshes:
            return

        combined = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        combined.export(path)
