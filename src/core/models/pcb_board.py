from dataclasses import dataclass, field
from .component import Component
from .layer import Layer
from .net import Net


@dataclass
class Trace:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str
    net_name: str = ""


@dataclass
class Via:
    x: float
    y: float
    drill: float
    size: float
    net_name: str = ""


@dataclass
class GraphicLine:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str


@dataclass
class GraphicArc:
    x: float
    y: float
    start_x: float
    start_y: float
    angle: float
    width: float
    layer: str


@dataclass
class PCBBoard:
    title: str = ""
    company: str = ""
    revision: str = ""
    kicad_version: str = ""
    components: list[Component] = field(default_factory=list)
    traces: list[Trace] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    graphic_lines: list[GraphicLine] = field(default_factory=list)
    graphic_arcs: list[GraphicArc] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    layers: list[Layer] = field(default_factory=list)

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        """Returns (min_x, min_y, max_x, max_y) from Edge.Cuts lines."""
        edge_lines = [l for l in self.graphic_lines if l.layer == "Edge.Cuts"]
        if not edge_lines:
            return (0.0, 0.0, 100.0, 100.0)
        xs = [l.x1 for l in edge_lines] + [l.x2 for l in edge_lines]
        ys = [l.y1 for l in edge_lines] + [l.y2 for l in edge_lines]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def width_mm(self) -> float:
        bb = self.bounding_box
        return bb[2] - bb[0]

    @property
    def height_mm(self) -> float:
        bb = self.bounding_box
        return bb[3] - bb[1]

    def component_by_ref(self, ref: str) -> Component | None:
        for c in self.components:
            if c.reference == ref:
                return c
        return None
