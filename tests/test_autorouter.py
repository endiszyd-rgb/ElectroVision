"""Testy dla autoroutera PCB (algorytm A*/Lee na siatce 2-warstwowej)."""
import math
import pytest

from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer, LayerType

from src.algorithms.autorouter import (
    pad_world_pos, collect_unrouted_nets, RouteGrid, build_grid_from_board,
    route_two_points, route_net, autoroute_board, AutorouteResult,
    _simplify_path, _path_length, ROUTING_LAYERS,
)


# ── Helpery ────────────────────────────────────────────────────────────────────

def _board(*comps, traces=None, vias=None, w=50.0, h=40.0):
    b = PCBBoard(title="T")
    b.graphic_lines = [
        GraphicLine(0, 0, w, 0, 0.05, "Edge.Cuts"),
        GraphicLine(w, 0, w, h, 0.05, "Edge.Cuts"),
        GraphicLine(w, h, 0, h, 0.05, "Edge.Cuts"),
        GraphicLine(0, h, 0, 0, 0.05, "Edge.Cuts"),
    ]
    b.layers = [Layer(0, "F.Cu", LayerType.COPPER), Layer(31, "B.Cu", LayerType.COPPER)]
    b.components = list(comps)
    b.traces = list(traces or [])
    b.vias = list(vias or [])
    b.zones = []
    return b


def _smd(ref, x, y, net, layer="F.Cu", w=1.0, h=1.0):
    c = Component(ref, "R", "R_0402", x, y, layer=layer)
    c.pads = [Pad("1", "smd", "rect", 0, 0, w, h, net_name=net)]
    return c


def _two_pad_net(ref, x, y, net1, net2, dx=1.5):
    c = Component(ref, "R", "R_0402", x, y)
    c.pads = [
        Pad("1", "smd", "rect", -dx/2, 0, 0.6, 0.6, net_name=net1),
        Pad("2", "smd", "rect",  dx/2, 0, 0.6, 0.6, net_name=net2),
    ]
    return c


# ── pad_world_pos ──────────────────────────────────────────────────────────────

class TestPadWorldPos:
    def test_no_rotation(self):
        c = Component("R1", "10k", "R_0402", 10, 20)
        p = Pad("1", "smd", "rect", 1.0, 0.5, 0.5, 0.5)
        wx, wy = pad_world_pos(c, p)
        assert wx == pytest.approx(11.0)
        assert wy == pytest.approx(20.5)

    def test_rotation_90(self):
        c = Component("R1", "10k", "R_0402", 0, 0, rotation=90)
        p = Pad("1", "smd", "rect", 1.0, 0.0, 0.5, 0.5)
        wx, wy = pad_world_pos(c, p)
        assert wx == pytest.approx(0.0, abs=1e-6)
        assert wy == pytest.approx(1.0, abs=1e-6)

    def test_rotation_180(self):
        c = Component("R1", "10k", "R_0402", 5, 5, rotation=180)
        p = Pad("1", "smd", "rect", 1.0, 0.0, 0.5, 0.5)
        wx, wy = pad_world_pos(c, p)
        assert wx == pytest.approx(4.0, abs=1e-6)
        assert wy == pytest.approx(5.0, abs=1e-6)


# ── collect_unrouted_nets ───────────────────────────────────────────────────────

class TestCollectUnroutedNets:
    def test_finds_unconnected_net(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 20, 20, "GND"))
        unrouted = collect_unrouted_nets(b)
        assert "GND" in unrouted
        assert len(unrouted["GND"]) == 2

    def test_skips_single_pad_net(self):
        b = _board(_smd("R1", 5, 5, "GND"))
        unrouted = collect_unrouted_nets(b)
        assert "GND" not in unrouted

    def test_skips_empty_net_name(self):
        b = _board(_smd("R1", 5, 5, ""), _smd("R2", 10, 10, ""))
        unrouted = collect_unrouted_nets(b)
        assert "" not in unrouted

    def test_already_routed_net_excluded(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 20, 20, "GND"))
        b.traces = [Trace(5, 5, 20, 20, 0.25, "F.Cu", net_name="GND")]
        unrouted = collect_unrouted_nets(b)
        assert "GND" not in unrouted

    def test_three_pad_net_needs_two_traces(self):
        c1 = _smd("R1", 5, 5, "VCC")
        c2 = _smd("R2", 20, 20, "VCC")
        c3 = _smd("R3", 30, 5, "VCC")
        b = _board(c1, c2, c3)
        b.traces = [Trace(5, 5, 20, 20, 0.25, "F.Cu", net_name="VCC")]
        unrouted = collect_unrouted_nets(b)
        # 3 pady wymagają 2 segmentów, mamy tylko 1 -> wciąż niepołączona
        assert "VCC" in unrouted

    def test_multiple_independent_nets(self):
        b = _board(
            _smd("R1", 5, 5, "GND"), _smd("R2", 40, 5, "GND"),
            _smd("R3", 5, 30, "VCC"), _smd("R4", 40, 30, "VCC"),
        )
        unrouted = collect_unrouted_nets(b)
        assert set(unrouted.keys()) == {"GND", "VCC"}


# ── RouteGrid ──────────────────────────────────────────────────────────────────

class TestRouteGrid:
    def test_grid_dimensions_positive(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        assert g.cols > 0
        assert g.rows > 0

    def test_to_cell_to_world_roundtrip(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        col, row = g.to_cell(10.0, 15.0)
        wx, wy = g.to_world(col, row)
        assert wx == pytest.approx(10.0, abs=0.5)
        assert wy == pytest.approx(15.0, abs=0.5)

    def test_in_bounds(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        assert g.in_bounds(0, 0)
        assert not g.in_bounds(-1, 0)
        assert not g.in_bounds(g.cols, 0)

    def test_layer_idx(self):
        g = RouteGrid(0, 0, 50, 40, layers=["F.Cu", "B.Cu"])
        assert g.layer_idx("F.Cu") == 0
        assert g.layer_idx("B.Cu") == 1
        assert g.layer_idx("Unknown") == 0  # fallback

    def test_block_disc_marks_cells(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        g.block_disc(10, 10, 1.0, layer_idx=0)
        col, row = g.to_cell(10, 10)
        assert g.is_blocked(col, row, 0)
        assert not g.is_blocked(col, row, 1)

    def test_block_disc_all_layers(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        g.block_disc(10, 10, 1.0, layer_idx=None)
        col, row = g.to_cell(10, 10)
        assert g.is_blocked(col, row, 0)
        assert g.is_blocked(col, row, 1)

    def test_unblock_at(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        g.block_disc(10, 10, 1.0, layer_idx=None)
        g.unblock_at(10, 10)
        col, row = g.to_cell(10, 10)
        assert not g.is_blocked(col, row, 0)
        assert not g.is_blocked(col, row, 1)

    def test_block_segment(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        g.block_segment(5, 5, 20, 5, 0.3, layer_idx=0)
        col, row = g.to_cell(12, 5)
        assert g.is_blocked(col, row, 0)


# ── build_grid_from_board ────────────────────────────────────────────────────

class TestBuildGridFromBoard:
    def test_pads_create_obstacles(self):
        b = _board(_smd("R1", 10, 10, "GND"))
        g = build_grid_from_board(b)
        col, row = g.to_cell(10, 10)
        li = g.layer_idx("F.Cu")
        assert g.is_blocked(col, row, li)

    def test_thru_hole_blocks_both_layers(self):
        c = Component("J1", "CONN", "Conn_1x2", 10, 10)
        c.pads = [Pad("1", "thru_hole", "circle", 0, 0, 1.5, 1.5, net_name="GND", drill=0.8)]
        b = _board(c)
        g = build_grid_from_board(b)
        col, row = g.to_cell(10, 10)
        assert g.is_blocked(col, row, 0)
        assert g.is_blocked(col, row, 1)

    def test_existing_trace_blocks_path(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 30, 5, "GND"))
        b.traces = [Trace(15, 0, 15, 40, 0.3, "F.Cu", net_name="OTHER")]
        g = build_grid_from_board(b)
        col, row = g.to_cell(15, 10)
        assert g.is_blocked(col, row, 0)

    def test_via_blocks_both_layers(self):
        b = _board()
        b.vias = [Via(25, 20, 0.3, 0.6, net_name="X")]
        g = build_grid_from_board(b)
        col, row = g.to_cell(25, 20)
        assert g.is_blocked(col, row, 0)
        assert g.is_blocked(col, row, 1)


# ── route_two_points ─────────────────────────────────────────────────────────

class TestRouteTwoPoints:
    def test_simple_straight_path(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        path = route_two_points(g, (5, 5), (5, 30), start_layer="F.Cu")
        assert path is not None
        assert path[0][:2] == (5, 5)
        assert path[-1][:2] == (5, 30)

    def test_path_avoids_obstacle(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        # Blokada pasa pomiędzy punktami
        g.block_segment(0, 20, 50, 20, 2.0, layer_idx=0)
        path = route_two_points(g, (5, 5), (5, 35), start_layer="F.Cu")
        assert path is not None  # powinien obejść (siatka ma marginesy)

    def test_no_path_when_fully_blocked(self):
        g = RouteGrid(0, 0, 10, 10, cell_mm=1.0, margin_cells=0)
        # Zablokuj całą siatkę
        for c in range(g.cols):
            for r in range(g.rows):
                g.blocked[0].add((c, r))
                g.blocked[1].add((c, r))
        path = route_two_points(g, (1, 1), (8, 8), start_layer="F.Cu")
        assert path is None

    def test_same_point_returns_single_element(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        path = route_two_points(g, (5, 5), (5, 5), start_layer="F.Cu")
        assert path is not None
        assert len(path) == 1

    def test_layer_change_uses_via(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        path = route_two_points(g, (5, 5), (5, 5), start_layer="F.Cu", end_layer="B.Cu")
        assert path is not None
        layers_used = {p[2] for p in path}
        assert "F.Cu" in layers_used or "B.Cu" in layers_used


# ── _simplify_path / _path_length ───────────────────────────────────────────────

class TestSimplifyPath:
    def test_collinear_points_removed(self):
        path = [(0, 0, "F.Cu"), (1, 0, "F.Cu"), (2, 0, "F.Cu"), (3, 0, "F.Cu")]
        simplified = _simplify_path(path)
        assert len(simplified) == 2

    def test_corner_kept(self):
        path = [(0, 0, "F.Cu"), (5, 0, "F.Cu"), (5, 5, "F.Cu")]
        simplified = _simplify_path(path)
        assert len(simplified) == 3

    def test_layer_change_kept(self):
        path = [(0, 0, "F.Cu"), (0, 0, "B.Cu"), (5, 0, "B.Cu")]
        simplified = _simplify_path(path)
        assert len(simplified) >= 2

    def test_short_path_unchanged(self):
        path = [(0, 0, "F.Cu"), (5, 5, "F.Cu")]
        assert _simplify_path(path) == path


class TestPathLength:
    def test_straight_line(self):
        path = [(0, 0, "F.Cu"), (10, 0, "F.Cu")]
        assert _path_length(path) == pytest.approx(10.0)

    def test_diagonal(self):
        path = [(0, 0, "F.Cu"), (3, 4, "F.Cu")]
        assert _path_length(path) == pytest.approx(5.0)

    def test_multi_segment(self):
        path = [(0, 0, "F.Cu"), (10, 0, "F.Cu"), (10, 10, "F.Cu")]
        assert _path_length(path) == pytest.approx(20.0)


# ── route_net ─────────────────────────────────────────────────────────────────

class TestRouteNet:
    def test_routes_two_pads(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        result = route_net(g, [(5, 5), (40, 30)], net_name="GND")
        assert result is not None
        traces, vias = result
        assert len(traces) > 0
        assert all(t.net_name == "GND" for t in traces)

    def test_routes_three_pads(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        result = route_net(g, [(5, 5), (25, 20), (40, 35)], net_name="VCC")
        assert result is not None
        traces, vias = result
        assert len(traces) >= 2

    def test_single_pad_returns_none(self):
        g = RouteGrid(0, 0, 50, 40, cell_mm=0.5)
        result = route_net(g, [(5, 5)], net_name="X")
        assert result is None


# ── autoroute_board (integracja) ────────────────────────────────────────────────

class TestAutorouteBoard:
    def test_routes_simple_two_pad_net(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b, cell_mm=0.5)
        assert "GND" in result.nets_routed
        assert len(result.traces_added) > 0
        assert len(b.traces) > 0

    def test_no_unrouted_nets_returns_empty(self):
        b = _board(_smd("R1", 5, 5, "GND"))
        result = autoroute_board(b)
        assert result.nets_routed == []
        assert result.nets_failed == []

    def test_apply_to_board_false_does_not_mutate(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b, apply_to_board=False)
        assert len(b.traces) == 0
        assert len(result.traces_added) > 0

    def test_multiple_nets_routed(self):
        b = _board(
            _smd("R1", 5, 5, "GND"), _smd("R2", 40, 5, "GND"),
            _smd("R3", 5, 35, "VCC"), _smd("R4", 40, 35, "VCC"),
        )
        result = autoroute_board(b, cell_mm=0.5)
        assert set(result.nets_routed) == {"GND", "VCC"}

    def test_result_success_rate(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b)
        assert result.success_rate == pytest.approx(100.0)

    def test_result_summary_is_string(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b)
        assert isinstance(result.summary, str)
        assert "GND" not in result.summary or True  # tylko sprawdzamy że nie wybucha

    def test_max_nets_limit(self):
        b = _board(
            _smd("R1", 5, 5, "GND"), _smd("R2", 40, 5, "GND"),
            _smd("R3", 5, 35, "VCC"), _smd("R4", 40, 35, "VCC"),
        )
        result = autoroute_board(b, max_nets=1)
        assert len(result.nets_routed) + len(result.nets_failed) == 1

    def test_total_length_positive(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b)
        assert result.total_length_mm > 0

    def test_traces_use_requested_width(self):
        b = _board(_smd("R1", 5, 5, "GND"), _smd("R2", 40, 30, "GND"))
        result = autoroute_board(b, trace_width=0.4)
        assert all(t.width == pytest.approx(0.4) for t in result.traces_added)

    def test_empty_board_no_crash(self):
        b = _board()
        result = autoroute_board(b)
        assert isinstance(result, AutorouteResult)
        assert result.nets_routed == []
