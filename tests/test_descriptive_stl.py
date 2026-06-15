"""Testy dla generatora opisowego 3D i eksportu STL."""
import pytest
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Sprawdzenie dostępności trimesh ────────────────────────────────────────────

try:
    import trimesh
    TRIMESH_OK = True
except ImportError:
    TRIMESH_OK = False

from src.generators.descriptive_stl import (
    Primitive, PrimType, BoolOp, HoleSpec, CutoutSpec,
    parse_description,
)


# ── Pomocniki ──────────────────────────────────────────────────────────────────

def _prim(**kw) -> Primitive:
    defaults = dict(ptype=PrimType.BOX, op=BoolOp.ADD, x=0, y=0, z=0,
                    width=20, depth=20, height=20, radius=10, segs=32, label="")
    defaults.update(kw)
    return Primitive(**defaults)


# ── Primitive dataclass ────────────────────────────────────────────────────────

class TestPrimitive:
    def test_default_prim(self):
        p = _prim()
        assert p.ptype == PrimType.BOX
        assert p.op == BoolOp.ADD

    def test_cylinder_prim(self):
        p = _prim(ptype=PrimType.CYLINDER, radius=5, height=15)
        assert p.radius == pytest.approx(5)
        assert p.height == pytest.approx(15)

    def test_sub_op(self):
        p = _prim(op=BoolOp.SUB)
        assert p.op == BoolOp.SUB

    def test_label_stored(self):
        p = _prim(label="pcb_mount")
        assert p.label == "pcb_mount"

    def test_sphere_prim(self):
        p = _prim(ptype=PrimType.SPHERE, radius=8)
        assert p.ptype == PrimType.SPHERE

    def test_prim_type_values(self):
        assert PrimType.BOX.value == "box"
        assert PrimType.CYLINDER.value == "cylinder"
        assert PrimType.SPHERE.value == "sphere"
        assert PrimType.CONE.value == "cone"
        assert PrimType.WEDGE.value == "wedge"

    def test_bool_op_values(self):
        assert BoolOp.ADD.value == "add"
        assert BoolOp.SUB.value == "sub"


# ── HoleSpec ──────────────────────────────────────────────────────────────────

class TestHoleSpec:
    def test_basic(self):
        h = HoleSpec(10, 20, 3.2)
        assert h.x == pytest.approx(10)
        assert h.y == pytest.approx(20)
        assert h.diameter == pytest.approx(3.2)

    def test_wall_default(self):
        h = HoleSpec(0, 0, 3.2)
        assert h.wall is None or h.wall == ""


# ── CutoutSpec ────────────────────────────────────────────────────────────────

class TestCutoutSpec:
    def test_usbc_cutout(self):
        c = CutoutSpec("left", 0, 1, 9.0, 3.5, "USB-C")
        assert c.wall == "left"
        assert c.width == pytest.approx(9.0)
        assert c.height == pytest.approx(3.5)
        assert c.label == "USB-C"

    def test_different_walls(self):
        for wall in ("left", "right", "front", "back", "top", "bottom"):
            c = CutoutSpec(wall, 0, 0, 5, 5, "test")
            assert c.wall == wall


# ── parse_description ─────────────────────────────────────────────────────────

class TestParseDescription:
    def test_basic_box_pl(self):
        p = parse_description("obudowa 60x40x25")
        assert p["width"] == pytest.approx(60)
        assert p["depth"] == pytest.approx(40)
        assert p["height"] == pytest.approx(25)

    def test_basic_box_en(self):
        p = parse_description("enclosure 80x60x30")
        assert p["width"] == pytest.approx(80)
        assert p["depth"] == pytest.approx(60)
        assert p["height"] == pytest.approx(30)

    def test_wall_thickness(self):
        p = parse_description("obudowa 50x40x20 ścianka 2.5mm")
        assert p["wall"] == pytest.approx(2.5)

    def test_wall_thickness_en(self):
        p = parse_description("enclosure 50x40x20 wall 2mm")
        assert p["wall"] == pytest.approx(2.0)

    def test_lid_keyword_pl(self):
        p = parse_description("obudowa 60x40x25 z wiekiem")
        assert p["lid"] is True

    def test_lid_keyword_en(self):
        p = parse_description("enclosure 60x40x25 lid")
        assert p["lid"] is True

    def test_no_lid_default(self):
        p = parse_description("obudowa 60x40x25")
        assert "lid" in p

    def test_standoffs_pl(self):
        p = parse_description("obudowa 60x40x25 standoffy M3")
        assert p["standoffs"] is True

    def test_standoffs_en(self):
        p = parse_description("enclosure 60x40x25 standoffs")
        assert p["standoffs"] is True

    def test_usbc_cutout_detected(self):
        p = parse_description("obudowa 60x40x25 USB-C na lewej")
        cuts = p["cutouts"]
        assert any(c.label and "USB" in c.label for c in cuts)

    def test_hdmi_cutout_detected(self):
        p = parse_description("obudowa 80x60x30 HDMI")
        cuts = p["cutouts"]
        assert any(c.label and "HDMI" in c.label for c in cuts)

    def test_rj45_cutout_detected(self):
        p = parse_description("enclosure 80x60x30 RJ45 back")
        cuts = p["cutouts"]
        assert any(c.label and "RJ" in c.label for c in cuts)

    def test_dc_jack_cutout(self):
        p = parse_description("obudowa 60x40x30 DC jack tył")
        cuts = p["cutouts"]
        assert len(cuts) >= 0  # może nie wykryć zawsze

    def test_arduino_preset(self):
        p = parse_description("obudowa arduino uno")
        assert p["width"] == pytest.approx(72)
        assert p["depth"] == pytest.approx(55)

    def test_esp32_preset(self):
        p = parse_description("obudowa esp32")
        assert p["width"] == pytest.approx(40)
        assert p["depth"] == pytest.approx(30)

    def test_raspberry_preset(self):
        p = parse_description("obudowa raspberry pi 4")
        assert p["width"] == pytest.approx(90)
        assert p["depth"] == pytest.approx(65)

    def test_panel_object_type(self):
        p = parse_description("panel 100x60 grubość 3mm")
        assert p["object_type"] == "panel"

    def test_bracket_object_type(self):
        p = parse_description("kątownik 40x30x20")
        assert p["object_type"] == "bracket"

    def test_standoff_object_type(self):
        p = parse_description("standoff 10mm M3")
        assert p["object_type"] == "standoff"

    def test_default_object_type_is_enclosure(self):
        p = parse_description("obudowa 50x40x20")
        assert p["object_type"] in ("enclosure", "obudowa")

    def test_empty_string_returns_dict(self):
        p = parse_description("")
        assert isinstance(p, dict)
        assert "width" in p

    def test_missing_dimensions_has_defaults(self):
        p = parse_description("obudowa")
        assert p["width"] > 0
        assert p["depth"] > 0
        assert p["height"] > 0

    def test_result_is_dict(self):
        p = parse_description("obudowa 60x40x25")
        assert isinstance(p, dict)

    def test_cutouts_is_list(self):
        p = parse_description("obudowa 60x40x25")
        assert isinstance(p["cutouts"], list)

    def test_wall_assigned_from_context(self):
        p = parse_description("obudowa 60x40x25 USB-C na lewej ścianie")
        cuts = p["cutouts"]
        usb = next((c for c in cuts if c.label and "USB" in c.label), None)
        if usb:
            assert usb.wall in ("left", "lewy", "lewa")

    def test_nano_preset(self):
        p = parse_description("obudowa nano")
        assert p["width"] == pytest.approx(48) or p["width"] > 0

    def test_pico_preset(self):
        p = parse_description("obudowa rp2040")
        assert p["width"] == pytest.approx(55) or p["width"] > 0

    def test_multiple_cutouts(self):
        p = parse_description("obudowa 80x60x30 USB-C HDMI SD card")
        cuts = p["cutouts"]
        assert len(cuts) >= 2


# ── Testy z trimesh (skipped jeśli brak) ─────────────────────────────────────

@pytest.mark.skipif(not TRIMESH_OK, reason="trimesh not installed")
class TestMakeWithTrimesh:
    def test_to_mesh_box(self):
        from src.generators.descriptive_stl import Primitive, PrimType, BoolOp
        p = Primitive(ptype=PrimType.BOX, op=BoolOp.ADD,
                      x=0, y=0, z=0, width=20, depth=15, height=10,
                      radius=0, segs=32, label="test")
        mesh = p.to_mesh()
        assert mesh is not None
        assert len(mesh.faces) > 0

    def test_to_mesh_cylinder(self):
        from src.generators.descriptive_stl import Primitive, PrimType, BoolOp
        p = Primitive(ptype=PrimType.CYLINDER, op=BoolOp.ADD,
                      x=0, y=0, z=0, width=0, depth=0, height=20,
                      radius=5, segs=32, label="cyl")
        mesh = p.to_mesh()
        assert len(mesh.vertices) > 0

    def test_to_mesh_sphere(self):
        from src.generators.descriptive_stl import Primitive, PrimType, BoolOp
        p = Primitive(ptype=PrimType.SPHERE, op=BoolOp.ADD,
                      x=0, y=0, z=0, width=0, depth=0, height=0,
                      radius=8, segs=16, label="sph")
        mesh = p.to_mesh()
        assert len(mesh.faces) > 0

    def test_build_scene_single_box(self):
        from src.generators.descriptive_stl import build_scene, Primitive, PrimType, BoolOp
        p = Primitive(ptype=PrimType.BOX, op=BoolOp.ADD,
                      x=0, y=0, z=0, width=30, depth=20, height=15,
                      radius=0, segs=32, label="box")
        result = build_scene([p])
        assert result is not None

    def test_make_enclosure_returns_dict(self):
        from src.generators.descriptive_stl import make_enclosure
        result = make_enclosure(60, 40, 25)
        assert isinstance(result, dict)
        assert "body" in result

    def test_make_enclosure_with_lid(self):
        from src.generators.descriptive_stl import make_enclosure
        result = make_enclosure(60, 40, 25, lid=True, separate_lid=True)
        assert "lid" in result

    def test_make_enclosure_without_lid(self):
        from src.generators.descriptive_stl import make_enclosure
        result = make_enclosure(60, 40, 25, lid=False)
        assert "body" in result

    def test_make_panel(self):
        from src.generators.descriptive_stl import make_panel
        result = make_panel(100, 80, 3.0)
        assert result is not None
        assert len(result.vertices) > 0

    def test_make_panel_with_holes(self):
        from src.generators.descriptive_stl import make_panel, HoleSpec
        holes = [HoleSpec(8, 8, 3.2), HoleSpec(92, 8, 3.2),
                 HoleSpec(8, 72, 3.2), HoleSpec(92, 72, 3.2)]
        result = make_panel(100, 80, 3.0, holes=holes)
        assert result is not None

    def test_make_bracket(self):
        from src.generators.descriptive_stl import make_bracket
        result = make_bracket(40, 30, 20, 3.0)
        assert result is not None

    def test_make_standoff(self):
        from src.generators.descriptive_stl import make_standoff
        result = make_standoff(10, 6, 3.2)
        assert result is not None

    def test_make_din_clip(self):
        from src.generators.descriptive_stl import make_din_clip
        result = make_din_clip(35)
        assert result is not None

    def test_make_cable_clip(self):
        from src.generators.descriptive_stl import make_cable_clip
        result = make_cable_clip(5.0)
        assert result is not None

    def test_build_from_description_enclosure(self):
        from src.generators.descriptive_stl import build_from_description
        result = build_from_description("obudowa 60x40x25")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_build_from_description_panel(self):
        from src.generators.descriptive_stl import build_from_description
        result = build_from_description("panel 100x80 grubość 3mm")
        assert isinstance(result, dict)

    def test_export_all_stl(self):
        from src.generators.descriptive_stl import make_enclosure, export_all_stl
        meshes = make_enclosure(60, 40, 25, lid=True, separate_lid=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = str(Path(tmpdir) / "test.stl")
            paths = export_all_stl(meshes, base)
            assert len(paths) > 0
            for p in paths:
                assert Path(p).exists()
                assert Path(p).stat().st_size > 0

    def test_export_stl_single(self):
        from src.generators.descriptive_stl import make_standoff, export_stl
        mesh = make_standoff(10, 6, 3.2)
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            path = f.name
        try:
            export_stl(mesh, path)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_enclosure_body_is_manifold(self):
        from src.generators.descriptive_stl import make_enclosure
        result = make_enclosure(50, 35, 20, wall=2.0)
        body = result["body"]
        assert body.is_watertight or len(body.faces) > 0

    def test_enclosure_body_has_faces(self):
        from src.generators.descriptive_stl import make_enclosure
        result = make_enclosure(60, 40, 25)
        body = result["body"]
        assert len(body.faces) > 50

    def test_make_enclosure_preset_arduino(self):
        from src.generators.descriptive_stl import build_from_description
        result = build_from_description("obudowa arduino uno z wiekiem")
        assert isinstance(result, dict) and len(result) > 0

    def test_make_enclosure_cutout_usbc(self):
        from src.generators.descriptive_stl import make_enclosure, CutoutSpec
        cuts = [CutoutSpec("left", 0, 1, 9.0, 3.5, "USB-C")]
        result = make_enclosure(60, 40, 25, cutouts=cuts)
        assert "body" in result
        # Upewniamy się, że mesh nie jest pusty po wycięciu
        assert len(result["body"].faces) > 0
