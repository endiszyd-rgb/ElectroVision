"""Testy dla Test Points Manager i DRC Profiles."""
import json
import pytest

from src.core.models.pcb_board import PCBBoard, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer, LayerType

from src.ui.dialogs.test_points_dialog import (
    TPPoint, scan_test_points, coverage_report,
    export_flying_probe_csv, _is_test_point,
)
from src.ui.dialogs.drc_profiles_dialog import (
    DRCProfile, BUILTIN_PROFILES,
)


# ── Helpery ────────────────────────────────────────────────────────────────────

def _board(*comps):
    b = PCBBoard(title="T")
    b.graphic_lines = [
        GraphicLine(0, 0, 100, 0, 0.05, "Edge.Cuts"),
        GraphicLine(100, 0, 100, 80, 0.05, "Edge.Cuts"),
        GraphicLine(100, 80, 0, 80, 0.05, "Edge.Cuts"),
        GraphicLine(0, 80, 0, 0, 0.05, "Edge.Cuts"),
    ]
    b.layers = [Layer(0, "F.Cu", LayerType.COPPER)]
    b.components = list(comps)
    b.traces = []; b.vias = []; b.zones = []
    return b


def _tp_comp(ref, net, x=10, y=10):
    c = Component(ref, "TestPoint", "TestPoint_Pad_D1.0mm", x, y)
    c.pads = [Pad("1", "thru_hole", "circle", 0, 0, 1.0, 1.0, net_name=net)]
    c.layer = "F.Cu"
    return c


def _reg_comp(ref, nets):
    c = Component(ref, "R", "R_0402", 5, 5)
    c.pads = [Pad(str(i+1), "smd", "rect", i*1.5, 0, 0.5, 0.5, net_name=n)
              for i, n in enumerate(nets)]
    return c


# ── _is_test_point ─────────────────────────────────────────────────────────────

class TestIsTestPoint:
    def test_tp_prefix(self):
        assert _is_test_point(Component("TP1", "TP", "fp", 0, 0))

    def test_tp_upper(self):
        assert _is_test_point(Component("tp2", "TP", "fp", 0, 0))

    def test_test_prefix(self):
        assert _is_test_point(Component("TEST1", "TP", "fp", 0, 0))

    def test_regular_resistor(self):
        assert not _is_test_point(Component("R1", "10k", "R_0402", 0, 0))

    def test_regular_cap(self):
        assert not _is_test_point(Component("C1", "100nF", "C_0402", 0, 0))

    def test_u_prefix_not_tp(self):
        assert not _is_test_point(Component("U1", "MCU", "LQFP64", 0, 0))


# ── scan_test_points ────────────────────────────────────────────────────────────

class TestScanTestPoints:
    def test_finds_tp_components(self):
        b = _board(_tp_comp("TP1", "GND"), _tp_comp("TP2", "VCC"))
        tps = scan_test_points(b)
        assert len(tps) == 2

    def test_skips_non_tp(self):
        b = _board(_tp_comp("TP1", "GND"), _reg_comp("R1", ["GND", "VCC"]))
        tps = scan_test_points(b)
        assert len(tps) == 1
        assert tps[0].reference == "TP1"

    def test_tp_net_name(self):
        b = _board(_tp_comp("TP1", "SDA"))
        tps = scan_test_points(b)
        assert tps[0].net_name == "SDA"

    def test_tp_position(self):
        b = _board(_tp_comp("TP1", "GND", x=25.5, y=33.0))
        tps = scan_test_points(b)
        assert tps[0].x == pytest.approx(25.5)
        assert tps[0].y == pytest.approx(33.0)

    def test_empty_board(self):
        b = _board()
        tps = scan_test_points(b)
        assert tps == []

    def test_all_regular_no_tps(self):
        b = _board(_reg_comp("R1", ["GND"]), _reg_comp("C1", ["VCC"]))
        tps = scan_test_points(b)
        assert tps == []


# ── coverage_report ────────────────────────────────────────────────────────────

class TestCoverageReport:
    def test_full_coverage(self):
        b = _board(
            _reg_comp("R1", ["GND", "VCC"]),
            _tp_comp("TP1", "GND"),
            _tp_comp("TP2", "VCC"),
        )
        tps = scan_test_points(b)
        rep = coverage_report(b, tps)
        assert rep["covered_nets"] == 2
        assert rep["total_nets"] == 2
        assert rep["coverage_pct"] == pytest.approx(100.0)

    def test_partial_coverage(self):
        b = _board(
            _reg_comp("R1", ["GND", "VCC", "SDA"]),
            _tp_comp("TP1", "GND"),
        )
        tps = scan_test_points(b)
        rep = coverage_report(b, tps)
        assert "SDA" in rep["uncovered"]
        assert "VCC" in rep["uncovered"]
        assert rep["coverage_pct"] < 100

    def test_no_tps_zero_coverage(self):
        b = _board(_reg_comp("R1", ["GND", "VCC"]))
        tps = []
        rep = coverage_report(b, tps)
        assert rep["coverage_pct"] == pytest.approx(0.0)
        assert rep["tp_count"] == 0

    def test_uncovered_sorted(self):
        b = _board(_reg_comp("R1", ["ZZZ", "AAA", "MMM"]))
        rep = coverage_report(b, [])
        assert rep["uncovered"] == sorted(rep["uncovered"])

    def test_front_back_count(self):
        b = _board()
        b.components = []
        tps = [
            TPPoint("TP1", "GND", 0, 0, "F.Cu"),
            TPPoint("TP2", "VCC", 0, 0, "B.Cu"),
            TPPoint("TP3", "SDA", 0, 0, "F.Cu"),
        ]
        rep = coverage_report(b, tps)
        assert rep["f_count"] == 2
        assert rep["b_count"] == 1


# ── export_flying_probe_csv ───────────────────────────────────────────────────

class TestExportCSV:
    def test_header(self):
        csv = export_flying_probe_csv([])
        assert "Reference" in csv
        assert "Net" in csv
        assert "X_mm" in csv

    def test_row_count(self):
        tps = [
            TPPoint("TP1", "GND", 10, 20, "F.Cu"),
            TPPoint("TP2", "VCC", 30, 40, "B.Cu"),
        ]
        csv = export_flying_probe_csv(tps)
        lines = [l for l in csv.splitlines() if l.strip()]
        assert len(lines) == 3  # header + 2 rows

    def test_sorted_by_ref(self):
        tps = [
            TPPoint("TP3", "C", 0, 0, "F.Cu"),
            TPPoint("TP1", "A", 0, 0, "F.Cu"),
            TPPoint("TP2", "B", 0, 0, "F.Cu"),
        ]
        csv = export_flying_probe_csv(tps)
        lines = csv.splitlines()[1:]
        refs = [l.split(",")[0].strip('"') for l in lines]
        assert refs == ["TP1", "TP2", "TP3"]


# ── DRCProfile ────────────────────────────────────────────────────────────────

class TestDRCProfile:
    def test_defaults(self):
        p = DRCProfile(name="X", fab="Y", tier="Z")
        assert p.min_trace_mm == pytest.approx(0.2)
        assert p.min_clearance_mm == pytest.approx(0.2)

    def test_roundtrip(self):
        p = DRCProfile(name="T", fab="F", tier="S",
                       min_trace_mm=0.127, min_via_drill_mm=0.3)
        p2 = DRCProfile.from_dict(p.to_dict())
        assert p2.name == "T"
        assert p2.min_trace_mm == pytest.approx(0.127)
        assert p2.min_via_drill_mm == pytest.approx(0.3)

    def test_check_vs_profile_ok(self):
        fab = DRCProfile(name="Fab", fab="F", tier="S",
                         min_trace_mm=0.127, min_clearance_mm=0.127)
        cur = DRCProfile(name="Cur", fab="C", tier="S",
                         min_trace_mm=0.127, min_clearance_mm=0.127)
        assert fab.check_vs_profile(cur) == []

    def test_check_vs_profile_violation(self):
        fab = DRCProfile(name="Fab", fab="F", tier="S", min_trace_mm=0.2)
        cur = DRCProfile(name="Cur", fab="C", tier="S", min_trace_mm=0.1)
        issues = fab.check_vs_profile(cur)
        assert any("Ścieżka" in i for i in issues)

    def test_json_list_roundtrip(self):
        data = [p.to_dict() for p in BUILTIN_PROFILES[:3]]
        text = json.dumps(data)
        loaded = [DRCProfile.from_dict(d) for d in json.loads(text)]
        assert len(loaded) == 3
        assert loaded[0].name == BUILTIN_PROFILES[0].name


class TestBuiltinProfiles:
    def test_count(self):
        assert len(BUILTIN_PROFILES) >= 7

    def test_jlcpcb_standard_exists(self):
        names = [p.name for p in BUILTIN_PROFILES]
        assert any("JLCPCB" in n and "Standard" in n for n in names)

    def test_jlcpcb_standard_trace(self):
        p = next(p for p in BUILTIN_PROFILES if "JLCPCB Standard" in p.name)
        assert p.min_trace_mm == pytest.approx(0.127)

    def test_advanced_tighter_than_standard(self):
        std = next(p for p in BUILTIN_PROFILES if "JLCPCB Standard" == p.name)
        adv = next(p for p in BUILTIN_PROFILES if "JLCPCB Advanced" == p.name)
        assert adv.min_trace_mm < std.min_trace_mm
        assert adv.min_via_drill_mm < std.min_via_drill_mm

    def test_all_have_fab(self):
        for p in BUILTIN_PROFILES:
            assert p.fab

    def test_all_have_notes(self):
        for p in BUILTIN_PROFILES:
            assert len(p.notes) > 5
