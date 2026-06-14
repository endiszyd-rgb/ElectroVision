"""Tests for KiCad .kicad_pcb parser."""
import pytest
from pathlib import Path
import tempfile

from src.core.parsers.kicad_parser import parse_kicad_pcb
from src.core.models.pcb_board import PCBBoard


SAMPLE_KICAD_PCB = """\
(kicad_pcb
  (version 20221018)
  (generator pcbnew)
  (title_block
    (title "Test Board")
    (company "ElectroVision Test")
  )
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )
  (net 0 "")
  (net 1 "VCC")
  (net 2 "GND")
  (footprint "Resistor_SMD:R_0402_1005Metric"
    (at 50 50 0)
    (layer "F.Cu")
    (property "Reference" "R1")
    (property "Value" "10k")
    (pad "1" smd rect (at -0.5 0) (size 0.9 0.9) (net 1 "VCC"))
    (pad "2" smd rect (at 0.5 0)  (size 0.9 0.9) (net 2 "GND"))
  )
  (footprint "LED_SMD:LED_0402_1005Metric"
    (at 60 50 90)
    (layer "F.Cu")
    (property "Reference" "LED1")
    (property "Value" "RED")
    (pad "A" smd rect (at -0.5 0) (size 0.9 0.9) (net 1 "VCC"))
    (pad "K" smd rect (at 0.5 0)  (size 0.9 0.9) (net 2 "GND"))
  )
  (segment (start 50 50) (end 60 50) (width 0.25) (layer "F.Cu") (net 1))
  (via (at 55 55) (size 0.8) (drill 0.4) (net 2))
  (gr_line (start 40 40) (end 80 40) (width 0.05) (layer "Edge.Cuts"))
  (gr_line (start 80 40) (end 80 70) (width 0.05) (layer "Edge.Cuts"))
  (gr_line (start 80 70) (end 40 70) (width 0.05) (layer "Edge.Cuts"))
  (gr_line (start 40 70) (end 40 40) (width 0.05) (layer "Edge.Cuts"))
)
"""


@pytest.fixture
def sample_kicad_file(tmp_path):
    f = tmp_path / "test.kicad_pcb"
    f.write_text(SAMPLE_KICAD_PCB, encoding="utf-8")
    return f


def test_parse_returns_pcb_board(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    assert isinstance(board, PCBBoard)


def test_parse_components(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    assert len(board.components) == 2
    refs = {c.reference for c in board.components}
    assert "R1" in refs
    assert "LED1" in refs


def test_parse_traces(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    assert len(board.traces) == 1
    tr = board.traces[0]
    assert tr.layer == "F.Cu"
    assert abs(tr.width - 0.25) < 1e-6


def test_parse_vias(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    assert len(board.vias) == 1
    assert abs(board.vias[0].drill - 0.4) < 1e-6


def test_parse_nets(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    net_names = {n.name for n in board.nets}
    assert "VCC" in net_names
    assert "GND" in net_names


def test_parse_graphic_lines(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    edge = [l for l in board.graphic_lines if l.layer == "Edge.Cuts"]
    assert len(edge) == 4


def test_bounding_box(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    bb = board.bounding_box
    assert abs(bb[0] - 40) < 1e-3
    assert abs(bb[1] - 40) < 1e-3
    assert abs(board.width_mm  - 40) < 1e-3
    assert abs(board.height_mm - 30) < 1e-3


def test_component_type_detection(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    r1 = board.component_by_ref("R1")
    assert r1 is not None
    assert r1.component_type == "resistor"
    led = board.component_by_ref("LED1")
    assert led is not None
    assert led.component_type == "led"


def test_pads_parsed(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    r1 = board.component_by_ref("R1")
    assert len(r1.pads) == 2
    net_names = {p.net_name for p in r1.pads}
    assert "VCC" in net_names
    assert "GND" in net_names


def test_invalid_file_raises(tmp_path):
    bad = tmp_path / "bad.kicad_pcb"
    bad.write_text("(not_kicad_pcb)", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_kicad_pcb(bad)


def test_title_parsed(sample_kicad_file):
    board = parse_kicad_pcb(sample_kicad_file)
    assert board.title == "Test Board"
    assert board.company == "ElectroVision Test"
