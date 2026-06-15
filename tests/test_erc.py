"""Tests for ERC (Electrical Rules Check)."""
import pytest
from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer, LayerType
from src.core.models.net import Net


def _board(*comps, traces=None, edge=True):
    board = PCBBoard(title="ERC test")
    board.components = list(comps)
    board.traces = list(traces or [])
    board.vias = []
    board.graphic_lines = [
        GraphicLine(0, 0, 80, 0, 0.05, "Edge.Cuts"),
        GraphicLine(80, 0, 80, 60, 0.05, "Edge.Cuts"),
        GraphicLine(80, 60, 0, 60, 0.05, "Edge.Cuts"),
        GraphicLine(0, 60, 0, 0, 0.05, "Edge.Cuts"),
    ] if edge else []
    board.graphic_arcs = []
    board.nets = []
    board.zones = []
    board.layers = [Layer(0, "F.Cu", LayerType.COPPER)]
    return board


def _comp(ref, value, **kwargs):
    c = Component(ref, value, kwargs.get("footprint", "R_0402"), 0, 0)
    pads = kwargs.get("pads", [])
    c.pads = pads
    return c


def _pad(num, net):
    return Pad(str(num), "smd", "rect", 0.0, 0.0, 0.5, 0.5, net_name=net)


class TestERCBasic:
    def test_empty_board_returns_no_crash(self):
        from src.ui.dialogs.erc_dialog import run_erc
        board = _board()
        issues = run_erc(board)
        assert isinstance(issues, list)

    def test_none_board_returns_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        issues = run_erc(None)
        assert any(i.severity == "error" for i in issues)

    def test_clean_board_no_errors(self):
        from src.ui.dialogs.erc_dialog import run_erc
        r1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        c1 = _comp("C1", "100nF", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        u1 = _comp("U1", "MCU", pads=[_pad(1, "GND"), _pad(2, "VCC"), _pad(3, "SDA")])
        board = _board(r1, c1, u1)
        issues = run_erc(board)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestERCDuplicateRefs:
    def test_duplicate_ref_is_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        c2 = _comp("R1", "4k7", pads=[_pad(1, "GND"), _pad(2, "SDA")])
        board = _board(c1, c2)
        issues = run_erc(board)
        dups = [i for i in issues if i.severity == "error" and "duplikat" in i.rule.lower()]
        assert dups, "Duplicate ref should produce error"

    def test_unique_refs_no_duplicate_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        c2 = _comp("R2", "4k7", pads=[_pad(1, "GND"), _pad(2, "SDA")])
        board = _board(c1, c2)
        issues = run_erc(board)
        dups = [i for i in issues if "duplikat" in i.rule.lower()]
        assert not dups


class TestERCUnconnected:
    def test_pad_with_no_net_is_warning(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), Pad("2", "smd", "rect", 1, 0, 0.5, 0.5, net_name="")])
        board = _board(c1)
        issues = run_erc(board)
        unconn = [i for i in issues if "połączone" in i.rule.lower() or "niepolączone" in i.rule.lower()]
        assert unconn

    def test_fully_connected_no_unconnected_warning(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        board = _board(c1)
        issues = run_erc(board)
        unconn = [i for i in issues if "niepolączone" in i.rule.lower() and i.reference == "R1"]
        assert not unconn


class TestERCMissingGND:
    def test_no_gnd_is_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        # All nets are VCC — no GND
        c1 = _comp("R1", "10k", pads=[_pad(1, "VCC"), _pad(2, "VCC")])
        board = _board(c1)
        issues = run_erc(board)
        gnd_issues = [i for i in issues if i.severity == "error" and "masy" in i.message.lower()]
        assert gnd_issues

    def test_with_gnd_no_missing_gnd_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        board = _board(c1)
        issues = run_erc(board)
        gnd_errs = [i for i in issues if "brak masy" in i.message.lower()]
        assert not gnd_errs


class TestERCDanglingNets:
    def test_single_connection_net_is_warning(self):
        from src.ui.dialogs.erc_dialog import run_erc
        # SCL net only connected to one component
        c1 = _comp("R1", "pull-up", pads=[_pad(1, "GND"), _pad(2, "SCL")])
        c2 = _comp("C1", "100nF", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        board = _board(c1, c2)
        issues = run_erc(board)
        dangling = [i for i in issues if "jednym połączeniem" in i.message or "jednym" in i.rule.lower()]
        assert dangling

    def test_two_connected_not_dangling(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "SCL")])
        c2 = _comp("U1", "MCU", pads=[_pad(1, "GND"), _pad(2, "SCL")])
        board = _board(c1, c2)
        issues = run_erc(board)
        dangling = [i for i in issues if "jednym połączeniem" in i.message and "SCL" in i.net]
        assert not dangling


class TestERCFloatingComponent:
    def test_component_all_pads_no_net_is_error(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[
            Pad("1", "smd", "rect", 0, 0, 0.5, 0.5, net_name=""),
            Pad("2", "smd", "rect", 1, 0, 0.5, 0.5, net_name=""),
        ])
        board = _board(c1)
        issues = run_erc(board)
        floating = [i for i in issues if "odłączony" in i.message.lower() and i.reference == "R1"]
        assert floating

    def test_component_with_pads_connected_not_floating(self):
        from src.ui.dialogs.erc_dialog import run_erc
        c1 = _comp("R1", "10k", pads=[_pad(1, "GND"), _pad(2, "VCC")])
        board = _board(c1)
        issues = run_erc(board)
        floating = [i for i in issues if "odłączony" in i.message.lower() and "R1" in i.reference]
        assert not floating
