"""Testy dla Copper Pour Analyser i Symbol Wizard."""
import pytest
from src.core.models.pcb_board import PCBBoard, CopperZone, GraphicLine, Trace
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer, LayerType
from src.ui.dialogs.copper_pour_dialog import (
    _polygon_area, _polygon_perimeter, _point_in_polygon,
    analyse_zones, board_copper_summary, ZoneStats,
)
from src.ui.dialogs.symbol_wizard_dialog import (
    SymPin, SymbolDef, export_kicad_sym, PRESETS,
    _preset_opamp, _preset_mcu8, _preset_connector4,
)


# ─── Polygon helpers ──────────────────────────────────────────────────────────

class TestPolygonArea:
    def test_square_10x10(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _polygon_area(pts) == pytest.approx(100.0)

    def test_rectangle(self):
        pts = [(0, 0), (20, 0), (20, 5), (0, 5)]
        assert _polygon_area(pts) == pytest.approx(100.0)

    def test_triangle(self):
        pts = [(0, 0), (4, 0), (0, 3)]
        assert _polygon_area(pts) == pytest.approx(6.0)

    def test_single_point_zero(self):
        assert _polygon_area([(0, 0)]) == pytest.approx(0.0)

    def test_empty_zero(self):
        assert _polygon_area([]) == pytest.approx(0.0)


class TestPolygonPerimeter:
    def test_square(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _polygon_perimeter(pts) == pytest.approx(40.0)

    def test_triangle_3_4_5(self):
        pts = [(0, 0), (3, 0), (0, 4)]
        assert _polygon_perimeter(pts) == pytest.approx(12.0)

    def test_single_point(self):
        assert _polygon_perimeter([(5, 5)]) == pytest.approx(0.0)


class TestPointInPolygon:
    def test_center_inside_square(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _point_in_polygon(5, 5, pts) is True

    def test_outside_square(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert _point_in_polygon(15, 5, pts) is False

    def test_origin_corner(self):
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        # corner behaviour can vary, just no exception
        _point_in_polygon(0, 0, pts)


# ─── Zone analysis ────────────────────────────────────────────────────────────

def _make_board_with_zones():
    b = PCBBoard(title="T")
    b.graphic_lines = [
        GraphicLine(0, 0, 100, 0, 0.05, "Edge.Cuts"),
        GraphicLine(100, 0, 100, 80, 0.05, "Edge.Cuts"),
        GraphicLine(100, 80, 0, 80, 0.05, "Edge.Cuts"),
        GraphicLine(0, 80, 0, 0, 0.05, "Edge.Cuts"),
    ]
    b.layers = [Layer(0, "F.Cu", LayerType.COPPER)]
    b.zones = [
        CopperZone(
            points=[(0, 0), (100, 0), (100, 80), (0, 80)],
            net_name="GND", layer="F.Cu", clearance=0.2,
        ),
        CopperZone(
            points=[(0, 0), (50, 0), (50, 40), (0, 40)],
            net_name="VCC", layer="B.Cu", clearance=0.2,
        ),
    ]
    b.components = []
    b.traces = []
    b.vias = []
    return b


class TestAnalyseZones:
    def test_returns_one_stat_per_zone(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        assert len(stats) == 2

    def test_first_zone_area(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        assert stats[0].area_mm2 == pytest.approx(8000.0)

    def test_second_zone_area(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        assert stats[1].area_mm2 == pytest.approx(2000.0)

    def test_zone_layer_preserved(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        assert stats[0].zone.layer == "F.Cu"
        assert stats[1].zone.layer == "B.Cu"

    def test_pad_inside_zone_counted(self):
        b = _make_board_with_zones()
        comp = Component("R1", "10k", "R_0402", 50, 40)
        comp.pads = [Pad("1", "smd", "rect", 0, 0, 0.5, 0.5, net_name="GND")]
        b.components = [comp]
        stats = analyse_zones(b)
        assert stats[0].pad_count == 1

    def test_pad_outside_zone_not_counted(self):
        b = _make_board_with_zones()
        # Only the small VCC zone (0-50, 0-40) — put pad at (60, 60)
        comp = Component("R1", "10k", "R_0402", 60, 60)
        comp.pads = [Pad("1", "smd", "rect", 0, 0, 0.5, 0.5, net_name="VCC")]
        b.components = [comp]
        stats = analyse_zones(b)
        assert stats[1].pad_count == 0  # VCC zone — pad at 60,60 is outside

    def test_empty_board_no_zones(self):
        b = PCBBoard(title="empty")
        b.zones = []
        b.components = []
        stats = analyse_zones(b)
        assert stats == []


class TestBoardCopperSummary:
    def test_total_area(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        summary = board_copper_summary(b, stats)
        assert summary["total_zone_area"] == pytest.approx(10000.0)

    def test_zone_count(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        summary = board_copper_summary(b, stats)
        assert summary["zone_count"] == 2

    def test_per_layer_keys(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        summary = board_copper_summary(b, stats)
        assert "F.Cu" in summary["layers"]
        assert "B.Cu" in summary["layers"]

    def test_board_area(self):
        b = _make_board_with_zones()
        stats = analyse_zones(b)
        summary = board_copper_summary(b, stats)
        assert summary["board_area"] == pytest.approx(8000.0)


# ─── Symbol Wizard ────────────────────────────────────────────────────────────

class TestSymPin:
    def test_defaults(self):
        p = SymPin(number="1", name="VCC")
        assert p.pin_type == "passive"
        assert p.side == "Lewy"
        assert p.length_mm == pytest.approx(2.54)

    def test_to_row(self):
        p = SymPin(number="3", name="OUT", pin_type="output", side="Prawy")
        row = p.to_row()
        assert row[0] == "3"
        assert row[1] == "OUT"
        assert row[2] == "output"
        assert row[3] == "Prawy"


class TestSymbolDef:
    def test_empty_dnp_set(self):
        s = SymbolDef(name="X")
        assert s.pins == []

    def test_auto_layout_input_goes_left(self):
        s = SymbolDef(name="U1")
        s.pins = [SymPin(number="1", name="IN", pin_type="input", side="Prawy")]
        s.auto_layout()
        assert s.pins[0].side == "Lewy"

    def test_auto_layout_output_goes_right(self):
        s = SymbolDef(name="U1")
        s.pins = [SymPin(number="1", name="OUT", pin_type="output", side="Lewy")]
        s.auto_layout()
        assert s.pins[0].side == "Prawy"

    def test_auto_layout_vcc_goes_top(self):
        s = SymbolDef(name="U1")
        s.pins = [SymPin(number="1", name="VCC", pin_type="power_in", side="Lewy")]
        s.auto_layout()
        assert s.pins[0].side == "Górny"

    def test_auto_layout_gnd_goes_bottom(self):
        s = SymbolDef(name="U1")
        s.pins = [SymPin(number="1", name="GND", pin_type="power_in", side="Lewy")]
        s.auto_layout()
        assert s.pins[0].side == "Dolny"

    def test_auto_layout_no_connect_goes_right(self):
        s = SymbolDef(name="U1")
        s.pins = [SymPin(number="1", name="NC", pin_type="no_connect", side="Lewy")]
        s.auto_layout()
        assert s.pins[0].side == "Prawy"


class TestPresets:
    def test_presets_count(self):
        assert len(PRESETS) >= 4

    def test_opamp_has_5_pins(self):
        s = _preset_opamp()
        assert len(s.pins) == 5

    def test_opamp_has_output(self):
        s = _preset_opamp()
        out_pins = [p for p in s.pins if p.pin_type == "output"]
        assert len(out_pins) == 1

    def test_mcu8_has_8_pins(self):
        s = _preset_mcu8()
        assert len(s.pins) == 8

    def test_connector_all_passive(self):
        s = _preset_connector4()
        assert all(p.pin_type == "passive" for p in s.pins)


class TestKiCadExport:
    def test_export_contains_symbol_name(self):
        s = SymbolDef(name="MY_IC")
        s.pins = [SymPin("1", "VCC", "power_in", "Górny")]
        out = export_kicad_sym(s)
        assert "MY_IC" in out

    def test_export_contains_pin_name(self):
        s = SymbolDef(name="TEST")
        s.pins = [SymPin("1", "CLK", "input", "Lewy")]
        out = export_kicad_sym(s)
        assert "CLK" in out

    def test_export_contains_pin_number(self):
        s = SymbolDef(name="TEST")
        s.pins = [SymPin("42", "DATA", "output", "Prawy")]
        out = export_kicad_sym(s)
        assert '"42"' in out

    def test_export_is_string(self):
        s = SymbolDef(name="X")
        out = export_kicad_sym(s)
        assert isinstance(out, str)
        assert len(out) > 10

    def test_export_kicad_header(self):
        s = SymbolDef(name="X")
        out = export_kicad_sym(s)
        assert "kicad_symbol_lib" in out

    def test_export_pin_type_input(self):
        s = SymbolDef(name="X")
        s.pins = [SymPin("1", "IN", "input", "Lewy")]
        out = export_kicad_sym(s)
        assert "input" in out

    def test_export_empty_pins(self):
        s = SymbolDef(name="EMPTY")
        out = export_kicad_sym(s)
        assert "EMPTY" in out

    def test_export_opamp_preset(self):
        s = _preset_opamp()
        out = export_kicad_sym(s)
        assert "OPAMP" in out
        assert "IN-" in out
        assert "OUT" in out
