from dataclasses import dataclass, field
from enum import Enum


class LayerType(Enum):
    COPPER = "copper"
    SILKSCREEN = "silkscreen"
    MASK = "mask"
    PASTE = "paste"
    COURTYARD = "courtyard"
    FAB = "fab"
    EDGE_CUTS = "edge_cuts"
    USER = "user"


@dataclass
class Layer:
    number: int
    name: str
    layer_type: LayerType
    visible: bool = True

    @staticmethod
    def kicad_layers() -> list["Layer"]:
        return [
            Layer(0,  "F.Cu",        LayerType.COPPER),
            Layer(1,  "In1.Cu",      LayerType.COPPER),
            Layer(2,  "In2.Cu",      LayerType.COPPER),
            Layer(31, "B.Cu",        LayerType.COPPER),
            Layer(32, "B.Adhes",     LayerType.USER),
            Layer(33, "F.Adhes",     LayerType.USER),
            Layer(34, "B.Paste",     LayerType.PASTE),
            Layer(35, "F.Paste",     LayerType.PASTE),
            Layer(36, "B.SilkS",     LayerType.SILKSCREEN),
            Layer(37, "F.SilkS",     LayerType.SILKSCREEN),
            Layer(38, "B.Mask",      LayerType.MASK),
            Layer(39, "F.Mask",      LayerType.MASK),
            Layer(44, "Edge.Cuts",   LayerType.EDGE_CUTS),
            Layer(49, "B.Fab",       LayerType.FAB),
            Layer(50, "F.Fab",       LayerType.FAB),
            Layer(52, "B.CrtYd",     LayerType.COURTYARD),
            Layer(53, "F.CrtYd",     LayerType.COURTYARD),
        ]
