"""Tests for PCB DRC validator."""
import pytest
from src.validators.pcb_drc import PCBValidator
from src.core.models.pcb_board import PCBBoard, Trace, GraphicLine
from src.core.models.component import Component


def _make_board_with_outline():
    board = PCBBoard()
    board.graphic_lines = [
        GraphicLine(0, 0, 100, 0, 0.05, "Edge.Cuts"),
        GraphicLine(100, 0, 100, 80, 0.05, "Edge.Cuts"),
        GraphicLine(100, 80, 0, 80, 0.05, "Edge.Cuts"),
        GraphicLine(0, 80, 0, 0, 0.05, "Edge.Cuts"),
    ]
    return board


def test_no_board_returns_error():
    issues = PCBValidator(None).run()
    assert any(i["severity"] == "error" for i in issues)


def test_missing_outline():
    board = PCBBoard()
    issues = PCBValidator(board).run()
    assert any("Edge.Cuts" in i["message"] for i in issues)


def test_clean_board_no_errors():
    board = _make_board_with_outline()
    issues = PCBValidator(board).run()
    errors = [i for i in issues if i["severity"] == "error"]
    assert len(errors) == 0


def test_narrow_trace_detected():
    board = _make_board_with_outline()
    board.traces.append(Trace(10, 10, 20, 10, width=0.05, layer="F.Cu", net_name="NET1"))
    issues = PCBValidator(board).run()
    assert any("wąska" in i["message"].lower() or "trace" in i["message"].lower() for i in issues)


def test_duplicate_reference():
    board = _make_board_with_outline()
    board.components = [
        Component("R1", "10k", "", 50, 50),
        Component("R1", "100k", "", 60, 60),
    ]
    issues = PCBValidator(board).run()
    assert any("R1" in i["message"] for i in issues)


def test_via_too_small():
    from src.core.models.pcb_board import Via
    board = _make_board_with_outline()
    board.vias.append(Via(50, 50, drill=0.1, size=0.4))
    issues = PCBValidator(board).run()
    assert any("przelotki" in i["message"].lower() or "drill" in i["message"].lower() for i in issues)
