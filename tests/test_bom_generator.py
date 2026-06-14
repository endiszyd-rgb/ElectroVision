"""Tests for BOM generator."""
import pytest
from pathlib import Path
from src.generators.bom_generator import BOMGenerator
from src.core.models.component import Component


def _make_comp(ref, value, fp="Resistor_SMD:R_0402", mfr="", pn="", desc=""):
    c = Component(reference=ref, value=value, footprint=fp, x=0, y=0)
    c.manufacturer = mfr
    c.manufacturer_pn = pn
    c.description = desc
    return c


@pytest.fixture
def components():
    return [
        _make_comp("R1", "10k", mfr="Yageo", pn="RC0402FR-0710KL"),
        _make_comp("R2", "10k", mfr="Yageo", pn="RC0402FR-0710KL"),
        _make_comp("R3", "100k"),
        _make_comp("C1", "100nF", fp="Capacitor_SMD:C_0402"),
        _make_comp("U1", "ESP32-WROOM", fp="RF_Module:ESP32-WROOM-32"),
    ]


def test_group_components_merges_same_value(components):
    groups = BOMGenerator.group_components(components)
    r10k = next((g for g in groups if "10k" in g["Wartość"] and g["Footprint"] == "R_0402"), None)
    assert r10k is not None
    assert r10k["Ilość"] == 2
    assert "R1" in r10k["Reference"]
    assert "R2" in r10k["Reference"]


def test_group_components_keeps_unique(components):
    groups = BOMGenerator.group_components(components)
    assert len(groups) == 4


def test_export_csv(components, tmp_path):
    path = str(tmp_path / "bom.csv")
    BOMGenerator.to_csv(components, path)
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8-sig")
    assert "Reference" in content
    assert "10k" in content
    assert "ESP32-WROOM" in content


def test_export_excel(components, tmp_path):
    pytest.importorskip("openpyxl")
    path = str(tmp_path / "bom.xlsx")
    BOMGenerator.to_excel(components, path)
    assert Path(path).exists()
    assert Path(path).stat().st_size > 1000


def test_empty_components():
    rows = BOMGenerator.group_components([])
    assert rows == []
