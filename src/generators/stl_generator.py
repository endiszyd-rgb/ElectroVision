"""STL and STEP generator for PCB enclosures using CadQuery."""
from pathlib import Path
from src.core.models.pcb_board import PCBBoard


class STLGenerator:
    """
    Generates 3D models for a PCB and its enclosure.

    Uses CadQuery to produce parametric STEP files (best for Fusion 360)
    and exports STL for 3D printing slicers.

    Parameters
    ----------
    board : PCBBoard
    params : dict
        pcb_thickness    – FR4 thickness in mm (default 1.6)
        enclosure_margin – wall offset from PCB edge in mm (default 3.0)
        enclosure_height – total inside height of enclosure in mm (default 25.0)
        wall_thickness   – enclosure wall thickness in mm (default 2.0)
        corner_radius    – rounded corner radius in mm (default 2.0)
        gen_enclosure    – generate enclosure body (default True)
        gen_lid          – generate lid (default True)
        gen_pcb_3d       – generate PCB body (default True)
    """

    def __init__(self, board: PCBBoard, params: dict | None = None) -> None:
        self._board = board
        self._params = params or {}

    def _p(self, key: str, default):
        return self._params.get(key, default)

    def _make_pcb_body(self, cq):
        bb = self._board.bounding_box
        w  = max(bb[2] - bb[0], 5.0)
        h  = max(bb[3] - bb[1], 5.0)
        th = self._p("pcb_thickness", 1.6)
        pcb = (
            cq.Workplane("XY")
            .box(w, h, th)
            .translate((0, 0, th / 2))
        )
        return pcb

    def _make_enclosure(self, cq):
        bb  = self._board.bounding_box
        w   = max(bb[2] - bb[0], 5.0)
        h   = max(bb[3] - bb[1], 5.0)
        mar = self._p("enclosure_margin", 3.0)
        ht  = self._p("enclosure_height", 25.0)
        wt  = self._p("wall_thickness", 2.0)
        r   = self._p("corner_radius", 2.0)
        th  = self._p("pcb_thickness", 1.6)

        outer_w = w + 2 * (mar + wt)
        outer_h = h + 2 * (mar + wt)

        outer = (
            cq.Workplane("XY")
            .rect(outer_w, outer_h)
            .extrude(ht)
        )
        inner = (
            cq.Workplane("XY")
            .rect(outer_w - 2 * wt, outer_h - 2 * wt)
            .extrude(ht - wt)
        )
        enclosure = outer.cut(inner)

        # PCB standoffs (4 corners)
        standoff_h = 3.0
        standoff_r = 1.5
        screw_r    = 0.75
        off_x = w / 2 - 3.0
        off_y = h / 2 - 3.0
        for sx, sy in [(off_x, off_y), (-off_x, off_y), (off_x, -off_y), (-off_x, -off_y)]:
            standoff = (
                cq.Workplane("XY")
                .circle(standoff_r)
                .extrude(standoff_h)
                .translate((sx, sy, wt))
            )
            hole = (
                cq.Workplane("XY")
                .circle(screw_r)
                .extrude(standoff_h)
                .translate((sx, sy, wt))
            )
            enclosure = enclosure.union(standoff).cut(hole)

        return enclosure

    def _make_lid(self, cq):
        bb  = self._board.bounding_box
        w   = max(bb[2] - bb[0], 5.0)
        h   = max(bb[3] - bb[1], 5.0)
        mar = self._p("enclosure_margin", 3.0)
        wt  = self._p("wall_thickness", 2.0)

        outer_w = w + 2 * (mar + wt)
        outer_h = h + 2 * (mar + wt)
        lid_h   = wt + 2.0
        snap_h  = 3.0
        snap_t  = 0.8

        lid = (
            cq.Workplane("XY")
            .rect(outer_w, outer_h)
            .extrude(lid_h)
        )
        inner_rect = (
            cq.Workplane("XY")
            .rect(outer_w - 2 * wt, outer_h - 2 * wt)
            .extrude(lid_h - wt)
        )
        lid = lid.cut(inner_rect)

        snap = (
            cq.Workplane("XY")
            .rect(outer_w - snap_t * 2, outer_h - snap_t * 2)
            .extrude(snap_h)
            .translate((0, 0, lid_h))
        )
        snap_inner = (
            cq.Workplane("XY")
            .rect(outer_w - snap_t * 4, outer_h - snap_t * 4)
            .extrude(snap_h)
            .translate((0, 0, lid_h))
        )
        lid = lid.union(snap.cut(snap_inner))
        return lid

    def _build_assembly(self):
        try:
            import cadquery as cq
        except ImportError as exc:
            raise ImportError(
                "Wymagane: pip install cadquery\n"
                "Jeśli CadQuery nie jest dostępne, użyj trimesh jako fallback."
            ) from exc

        assembly = cq.Assembly()

        if self._p("gen_pcb_3d", True):
            pcb = self._make_pcb_body(cq)
            assembly.add(pcb, name="pcb", color=cq.Color("green"))

        if self._p("gen_enclosure", True):
            enc = self._make_enclosure(cq)
            th  = self._p("pcb_thickness", 1.6)
            assembly.add(enc, name="enclosure",
                         color=cq.Color(0.3, 0.3, 0.3, 0.9),
                         loc=cq.Location(cq.Vector(0, 0, -3.0)))

        if self._p("gen_lid", True):
            lid = self._make_lid(cq)
            ht  = self._p("enclosure_height", 25.0)
            wt  = self._p("wall_thickness", 2.0)
            assembly.add(lid, name="lid",
                         color=cq.Color(0.4, 0.4, 0.4, 0.9),
                         loc=cq.Location(cq.Vector(0, 0, ht - wt)))

        return assembly

    def export_step(self, path: str) -> None:
        assembly = self._build_assembly()
        assembly.save(path)

    def export_stl(self, path: str) -> None:
        try:
            import cadquery as cq
            shape = self._build_assembly().toCompound()
            cq.exporters.export(shape, path, cq.exporters.ExportTypes.STL)
        except ImportError:
            self._export_stl_trimesh(path)

    def _export_stl_trimesh(self, path: str) -> None:
        """Fallback STL export using trimesh when CadQuery is unavailable."""
        import trimesh
        import numpy as np

        bb  = self._board.bounding_box
        w   = max(bb[2] - bb[0], 5.0)
        h   = max(bb[3] - bb[1], 5.0)
        th  = self._p("pcb_thickness", 1.6)
        mar = self._p("enclosure_margin", 3.0)
        ht  = self._p("enclosure_height", 25.0)
        wt  = self._p("wall_thickness", 2.0)

        meshes = []
        if self._p("gen_pcb_3d", True):
            pcb = trimesh.creation.box(extents=[w, h, th])
            pcb.apply_translation([0, 0, th / 2])
            meshes.append(pcb)

        if self._p("gen_enclosure", True):
            outer_w = w + 2 * (mar + wt)
            outer_h = h + 2 * (mar + wt)
            outer   = trimesh.creation.box(extents=[outer_w, outer_h, ht])
            inner   = trimesh.creation.box(extents=[outer_w - 2*wt, outer_h - 2*wt, ht - wt])
            inner.apply_translation([0, 0, wt / 2])
            try:
                enc = outer.difference(inner)
            except Exception:
                enc = outer
            enc.apply_translation([0, 0, -3.0])
            meshes.append(enc)

        if not meshes:
            return

        combined = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        combined.export(path)
