from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Pad:
    number: str
    pad_type: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    net_name: str = ""
    drill: float = 0.0


@dataclass
class Component:
    reference: str
    value: str
    footprint: str
    x: float
    y: float
    rotation: float = 0.0
    layer: str = "F.Cu"
    description: str = ""
    datasheet: str = ""
    manufacturer: str = ""
    manufacturer_pn: str = ""
    pads: list[Pad] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def component_type(self) -> str:
        ref = self.reference.upper()
        if ref.startswith("R"):
            return "resistor"
        if ref.startswith("C"):
            return "capacitor"
        if ref.startswith("LED"):
            return "led"
        if ref.startswith("L"):
            return "inductor"
        if ref.startswith("D"):
            return "diode"
        if ref.startswith("Q"):
            return "transistor"
        if ref.startswith("U"):
            return "ic"
        if ref.startswith("J") or ref.startswith("P"):
            return "connector"
        if ref.startswith("SW") or ref.startswith("S"):
            return "switch"
        if ref.startswith("X") or ref.startswith("Y"):
            return "crystal"
        if ref.startswith("F"):
            return "fuse"
        return "generic"

    @property
    def quantity(self) -> int:
        return 1
