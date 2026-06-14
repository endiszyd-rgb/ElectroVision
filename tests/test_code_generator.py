"""Tests for code generator."""
import pytest
from src.generators.code_generator import CodeGenerator
from src.core.models.component import Component


def _comp(ref, value):
    return Component(reference=ref, value=value, footprint="", x=0, y=0)


@pytest.fixture
def components():
    return [
        _comp("R1", "10k"),
        _comp("LED1", "RED"),
        _comp("U1", "ESP32"),
        _comp("SW1", "BUTTON"),
    ]


def test_generate_arduino(components):
    code = CodeGenerator.generate(components, platform="arduino", mcu="ESP32")
    assert "void setup()" in code
    assert "void loop()" in code
    assert "LED1" in code or "LED" in code


def test_generate_micropython(components):
    code = CodeGenerator.generate(components, platform="micropython", mcu="ESP32")
    assert "def main()" in code
    assert "from machine import" in code


def test_generate_cpp(components):
    code = CodeGenerator.generate(components, platform="esp_idf", mcu="ESP32")
    assert "#include <Arduino.h>" in code
    assert "void setup()" in code


def test_project_name_in_output(components):
    code = CodeGenerator.generate(components, project_name="TestBoard")
    assert "TestBoard" in code


def test_mcu_in_output(components):
    code = CodeGenerator.generate(components, mcu="Arduino Mega")
    assert "Arduino Mega" in code


def test_led_gets_pinmode(components):
    code = CodeGenerator.generate([_comp("LED1", "RED_LED")], platform="arduino")
    assert "pinMode" in code


def test_empty_components():
    code = CodeGenerator.generate([])
    assert len(code) > 0
