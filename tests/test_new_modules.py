"""Tests for new v0.4 modules: power analysis, DFM, annotation, netlist, stackup."""
import math
import pytest

from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer, LayerType
from src.core.models.net import Net


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_board(n_comp=3, n_trace=5, add_edge=True):
    board = PCBBoard(title="Test")
    # Components: use references whose prefix maps to the expected type
    all_comps = [
        Component("U1", "ESP32",   "Module",    20, 20),
        Component("R1", "10k",     "R_0402",     5,  5),
        Component("C1", "100nF",   "C_0402",    10,  5),
        Component("U2", "AMS1117", "SOT-223",   30, 10),
        Component("D1", "1N4148",  "D_SOD-123", 40, 15),
    ][:n_comp]
    # Give each pad a net so 'unconnected pads' check doesn't fire
    for i, comp in enumerate(all_comps):
        comp.pads = [
            Pad(str(k), "smd", "rect", float(k), 0.0, 0.5, 0.5,
                net_name=f"VCC" if k == 1 else f"NET{i}_{k}")
            for k in range(1, 4)
        ]
    board.components = all_comps

    for i in range(n_trace):
        board.traces.append(Trace(i + 1, 1, i + 10, 10, 0.25, "F.Cu", "VCC"))

    # Via large enough to pass Hobbyist profile (min_via_drill=0.4)
    board.vias = [Via(15, 15, 0.5, 1.0, "GND")]

    if add_edge:
        board.graphic_lines = [
            GraphicLine(0, 0, 80, 0,  0.05, "Edge.Cuts"),
            GraphicLine(80, 0, 80, 60, 0.05, "Edge.Cuts"),
            GraphicLine(80, 60, 0, 60, 0.05, "Edge.Cuts"),
            GraphicLine(0, 60, 0, 0,  0.05, "Edge.Cuts"),
        ]
    else:
        board.graphic_lines = []

    board.graphic_arcs = []
    board.nets   = [Net(1, "VCC"), Net(2, "GND"), Net(3, "NET0")]
    board.zones  = []
    board.layers = [Layer(0, "F.Cu", LayerType.COPPER), Layer(31, "B.Cu", LayerType.COPPER)]
    return board


# ── Power analysis ─────────────────────────────────────────────────────────────

class TestPowerAnalysis:
    def test_estimate_current_ic(self):
        from src.ui.dialogs.power_analysis_dialog import _estimate_current_ma
        comp = Component("U1", "ESP32", "Module", 0, 0)
        ma = _estimate_current_ma(comp)
        assert ma >= 100, "ESP32 should draw >= 100 mA"

    def test_estimate_current_resistor(self):
        from src.ui.dialogs.power_analysis_dialog import _estimate_current_ma
        comp = Component("R1", "10k", "R_0402", 0, 0)
        ma = _estimate_current_ma(comp)
        assert ma == 0.0

    def test_is_power_net(self):
        from src.ui.dialogs.power_analysis_dialog import _is_power_net, _is_gnd_net
        assert _is_power_net("VCC")
        assert _is_power_net("3.3V")
        assert _is_power_net("VBUS")
        assert not _is_power_net("SCL")
        assert _is_gnd_net("GND")
        assert _is_gnd_net("AGND")
        assert not _is_gnd_net("MOSI")

    def test_net_voltage(self):
        from src.ui.dialogs.power_analysis_dialog import _net_voltage
        assert _net_voltage("3.3V") == pytest.approx(3.3)
        assert _net_voltage("5V")   == pytest.approx(5.0)
        assert _net_voltage("12V")  == pytest.approx(12.0)
        assert _net_voltage("SCL")  is None

    def test_parse_capacitance(self):
        from src.ui.dialogs.power_analysis_dialog import _parse_capacitance_uf
        assert _parse_capacitance_uf("100nF") == pytest.approx(0.1)
        assert _parse_capacitance_uf("10uF")  == pytest.approx(10.0)
        assert _parse_capacitance_uf("1mF")   == pytest.approx(1000.0)
        assert _parse_capacitance_uf("22pF")  == pytest.approx(22e-6)

    def test_analyze_power_returns_list(self):
        from src.ui.dialogs.power_analysis_dialog import analyze_power
        board = _make_board()
        rails, warnings = analyze_power(board)
        assert isinstance(rails, list)
        assert isinstance(warnings, list)

    def test_vcc_rail_detected(self):
        from src.ui.dialogs.power_analysis_dialog import analyze_power
        board = _make_board()
        rails, _ = analyze_power(board)
        rail_names = [r.name for r in rails]
        assert "VCC" in rail_names


# ── DFM checker ────────────────────────────────────────────────────────────────

class TestDFM:
    def test_no_edge_cuts(self):
        from src.ui.dialogs.dfm_dialog import run_dfm, PROFILES
        board = _make_board(add_edge=False)
        profile = PROFILES["JLCPCB — Standard (2-layer)"]
        issues = run_dfm(board, profile)
        errors = [i for i in issues if i.severity == "error" and "kontur" in i.message.lower()]
        assert errors, "Should flag missing Edge.Cuts"

    def test_narrow_trace(self):
        from src.ui.dialogs.dfm_dialog import run_dfm, PROFILES
        board = _make_board()
        board.traces.append(Trace(0, 0, 5, 5, 0.05, "F.Cu"))  # 0.05 < 0.127mm min
        profile = PROFILES["JLCPCB — Standard (2-layer)"]
        issues = run_dfm(board, profile)
        narrow = [i for i in issues if "wąskich" in i.message]
        assert narrow

    def test_small_via(self):
        from src.ui.dialogs.dfm_dialog import run_dfm, PROFILES
        board = _make_board()
        board.vias.append(Via(5, 5, 0.15, 0.5))  # 0.15 < 0.3mm min for JLCPCB
        profile = PROFILES["JLCPCB — Standard (2-layer)"]
        issues = run_dfm(board, profile)
        via_issues = [i for i in issues if "wierceniem" in i.message]
        assert via_issues

    def test_duplicate_refs(self):
        from src.ui.dialogs.dfm_dialog import run_dfm, PROFILES
        board = _make_board(2)
        board.components[0].reference = "R1"
        board.components[1].reference = "R1"   # duplicate
        profile = PROFILES["Hobbyist (relaxed)"]
        issues = run_dfm(board, profile)
        dup = [i for i in issues if "zduplikowana" in i.message.lower()]
        assert dup

    def test_clean_board_has_no_errors(self):
        from src.ui.dialogs.dfm_dialog import run_dfm, PROFILES
        board = _make_board()
        profile = PROFILES["Hobbyist (relaxed)"]
        issues = run_dfm(board, profile)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


# ── Auto-annotation ────────────────────────────────────────────────────────────

class TestAnnotation:
    def test_basic_annotation(self):
        from src.ui.dialogs.annotation_dialog import annotate
        # Use refs whose prefix drives the correct component_type
        comps = [
            Component("R99", "10k",   "R_0402", 5,  5),   # resistor
            Component("C99", "100nF", "C_0402", 10, 5),   # capacitor
            Component("U99", "ESP32", "Module", 20, 20),  # ic
        ]
        for c in comps:
            c.pads = []
        result = annotate(comps, lambda c: (c.x, c.y))
        assert any(new.startswith("R") for _, _, new in result)
        assert any(new.startswith("C") for _, _, new in result)
        assert any(new.startswith("U") for _, _, new in result)

    def test_numbering_starts_at_1(self):
        from src.ui.dialogs.annotation_dialog import annotate
        comp = Component("R99", "10k", "R_0402", 0, 0)
        comp.pads = []
        result = annotate([comp], lambda c: c.reference, start_num=1)
        _, _, new_ref = result[0]
        assert new_ref == "R1"

    def test_step(self):
        from src.ui.dialogs.annotation_dialog import annotate
        comps = [Component(f"R{i+99}", "10k", "R_0402", i, 0) for i in range(3)]
        for c in comps:
            c.pads = []
        result = annotate(comps, lambda c: c.x, start_num=10, step=10)
        nums = [int(new[1:]) for _, _, new in result]
        assert nums == [10, 20, 30]

    def test_old_refs_preserved_in_result(self):
        from src.ui.dialogs.annotation_dialog import annotate
        comp = Component("R42", "10k", "R_0402", 0, 0)
        comp.pads = []
        result = annotate([comp], lambda c: c.x)
        comp_out, old, new = result[0]
        assert old == "R42"
        assert new == "R1"


# ── Netlist generator ──────────────────────────────────────────────────────────

class TestNetlistGenerator:
    def test_csv_has_header(self):
        from src.generators.netlist_generator import generate_netlist_csv
        board = _make_board()
        csv = generate_netlist_csv(board)
        assert csv.startswith("Net,Component,Reference,Pin")

    def test_csv_contains_references(self):
        from src.generators.netlist_generator import generate_netlist_csv
        board = _make_board(2)
        csv = generate_netlist_csv(board)
        assert "U1" in csv

    def test_kicad_netlist_format(self):
        from src.generators.netlist_generator import generate_kicad_netlist
        board = _make_board(2)
        nl = generate_kicad_netlist(board, "TestProject")
        assert "(export" in nl
        assert "(components" in nl
        assert "(nets" in nl

    def test_net_summary(self):
        from src.generators.netlist_generator import generate_net_summary_csv
        board = _make_board(2)
        csv = generate_net_summary_csv(board)
        assert "Net,Pins,Members" in csv

    def test_csv_row_per_pad(self):
        from src.generators.netlist_generator import generate_netlist_csv
        board = _make_board(1)  # 1 component with 3 pads
        csv = generate_netlist_csv(board)
        data_rows = [l for l in csv.splitlines() if l and not l.startswith("Net")]
        assert len(data_rows) == 3


# ── Stackup impedance calculator ──────────────────────────────────────────────

class TestStackupImpedance:
    def test_microstrip_50_ohm(self):
        from src.ui.dialogs.stackup_editor_dialog import calc_microstrip_z0
        z0 = calc_microstrip_z0(2.8, 1.6, 0.035, 4.5)
        assert 45 < z0 < 65, f"Expected ~50Ω, got {z0:.1f}Ω"

    def test_microstrip_narrow_higher_impedance(self):
        from src.ui.dialogs.stackup_editor_dialog import calc_microstrip_z0
        z0_narrow = calc_microstrip_z0(0.2, 1.6, 0.035, 4.5)
        z0_wide   = calc_microstrip_z0(4.0, 1.6, 0.035, 4.5)
        assert z0_narrow > z0_wide

    def test_stripline_z0_positive(self):
        from src.ui.dialogs.stackup_editor_dialog import calc_stripline_z0
        z0 = calc_stripline_z0(0.5, 1.0, 0.035, 4.5)
        assert z0 > 0

    def test_microstrip_monotone_decreasing(self):
        from src.ui.dialogs.stackup_editor_dialog import calc_microstrip_z0
        widths = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        z0s = [calc_microstrip_z0(w, 1.6, 0.035, 4.5) for w in widths]
        for i in range(len(z0s) - 1):
            assert z0s[i] > z0s[i + 1]


# ── Signal analysis ────────────────────────────────────────────────────────────

class TestSignalAnalysis:
    def test_propagation_delay_range(self):
        from src.ui.dialogs.signal_analysis_dialog import calc_propagation_delay_ns_per_mm
        tpd = calc_propagation_delay_ns_per_mm(4.5)
        # FR4 ~5-10 ps/mm
        assert 0.005 < tpd < 0.010, f"Got {tpd * 1000:.3f} ps/mm"

    def test_critical_length_at_100mhz(self):
        from src.ui.dialogs.signal_analysis_dialog import calc_critical_length_mm
        length = calc_critical_length_mm(100, 4.5)
        assert 100 < length < 600  # FR4 λ/4 at 100 MHz ≈ 417 mm

    def test_via_inductance_typical(self):
        from src.ui.dialogs.signal_analysis_dialog import calc_via_inductance_nh
        L = calc_via_inductance_nh(1.6, 0.3)
        assert 0.5 < L < 2.0, f"Got {L:.3f} nH"

    def test_crosstalk_increases_with_length(self):
        from src.ui.dialogs.signal_analysis_dialog import calc_crosstalk_db
        ct_short = calc_crosstalk_db(0.2, 0.2, 10, 100)
        ct_long  = calc_crosstalk_db(0.2, 0.2, 100, 100)
        assert ct_long > ct_short


# ── Board outline generator ────────────────────────────────────────────────────

class TestBoardOutline:
    def test_rectangle_4_sides(self):
        from src.ui.dialogs.board_outline_dialog import make_rectangle
        lines, arcs = make_rectangle(80, 60, 0)
        assert len(lines) == 4
        assert len(arcs) == 0

    def test_rounded_rect_more_segments(self):
        from src.ui.dialogs.board_outline_dialog import make_rectangle
        lines_sharp, _ = make_rectangle(80, 60, 0)
        lines_round, _ = make_rectangle(80, 60, 3.0)
        assert len(lines_round) > len(lines_sharp)

    def test_circle_segments(self):
        from src.ui.dialogs.board_outline_dialog import make_circle
        lines, arcs = make_circle(40, 40, 40, segments=32)
        assert len(lines) == 32

    def test_mounting_holes_line_count(self):
        from src.ui.dialogs.board_outline_dialog import make_mounting_holes
        holes = make_mounting_holes([(4, 4), (76, 4), (76, 56), (4, 56)], 3.2)
        assert len(holes) == 4 * 32  # 4 corners × 32 segments each

    def test_rectangle_perimeter(self):
        from src.ui.dialogs.board_outline_dialog import make_rectangle
        lines, _ = make_rectangle(80, 60, 0)
        total = sum(math.hypot(l.x2 - l.x1, l.y2 - l.y1) for l in lines)
        assert abs(total - 280) < 0.01  # 2*(80+60) = 280

    def test_all_lines_on_edge_cuts(self):
        from src.ui.dialogs.board_outline_dialog import make_rectangle
        lines, _ = make_rectangle(80, 60, 0)
        assert all(l.layer == "Edge.Cuts" for l in lines)
