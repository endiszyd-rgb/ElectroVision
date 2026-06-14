"""Parser dla plików .kicad_pcb (format S-expression KiCad 6/7/8)."""
from pathlib import Path
from typing import Any
import sexpdata

from ..models.pcb_board import PCBBoard, Trace, Via, GraphicLine, GraphicArc
from ..models.component import Component, Pad
from ..models.layer import Layer
from ..models.net import Net


def _sym(val: Any) -> str:
    if isinstance(val, sexpdata.Symbol):
        return str(val)
    return str(val)


def _find(node: list, key: str) -> list | None:
    for item in node:
        if isinstance(item, list) and item and _sym(item[0]) == key:
            return item
    return None


def _find_all(node: list, key: str) -> list[list]:
    return [item for item in node if isinstance(item, list) and item and _sym(item[0]) == key]


def _val(node: list, key: str, default=None):
    sub = _find(node, key)
    if sub and len(sub) > 1:
        return sub[1]
    return default


def _at(node: list) -> tuple[float, float, float]:
    at = _find(node, "at")
    if at:
        x = float(at[1]) if len(at) > 1 else 0.0
        y = float(at[2]) if len(at) > 2 else 0.0
        r = float(at[3]) if len(at) > 3 else 0.0
        return x, y, r
    return 0.0, 0.0, 0.0


def _parse_nets(board_node: list) -> list[Net]:
    nets = []
    for item in _find_all(board_node, "net"):
        if len(item) >= 3:
            try:
                nets.append(Net(number=int(item[1]), name=str(item[2])))
            except (ValueError, IndexError):
                pass
    return nets


def _parse_layers(board_node: list) -> list[Layer]:
    layers_node = _find(board_node, "layers")
    if not layers_node:
        return Layer.kicad_layers()
    result = []
    for item in layers_node[1:]:
        if isinstance(item, list) and len(item) >= 3:
            try:
                num = int(item[0])
                name = str(item[1])
                ltype_str = str(item[2]) if len(item) > 2 else "user"
                from ..models.layer import LayerType
                try:
                    ltype = LayerType(ltype_str.lower())
                except ValueError:
                    ltype = LayerType.USER
                result.append(Layer(num, name, ltype))
            except (ValueError, TypeError):
                pass
    return result or Layer.kicad_layers()


def _parse_pad(pad_node: list) -> Pad:
    number = str(pad_node[1]) if len(pad_node) > 1 else ""
    pad_type = str(pad_node[2]) if len(pad_node) > 2 else ""
    shape = str(pad_node[3]) if len(pad_node) > 3 else ""
    at = _find(pad_node, "at")
    x, y = (float(at[1]), float(at[2])) if at and len(at) > 2 else (0.0, 0.0)
    size_node = _find(pad_node, "size")
    w = float(size_node[1]) if size_node and len(size_node) > 1 else 0.0
    h = float(size_node[2]) if size_node and len(size_node) > 2 else w
    net_node = _find(pad_node, "net")
    net_name = str(net_node[2]) if net_node and len(net_node) > 2 else ""
    drill_node = _find(pad_node, "drill")
    drill = float(drill_node[1]) if drill_node and len(drill_node) > 1 else 0.0
    return Pad(number=number, pad_type=pad_type, shape=shape,
               x=x, y=y, width=w, height=h, net_name=net_name, drill=drill)


def _parse_footprints(board_node: list) -> list[Component]:
    components = []
    for fp in _find_all(board_node, "footprint"):
        if len(fp) < 2:
            continue
        footprint_name = str(fp[1])
        x, y, rot = _at(fp)
        layer_node = _find(fp, "layer")
        layer = str(layer_node[1]) if layer_node and len(layer_node) > 1 else "F.Cu"

        ref = ""
        value = ""
        description = ""
        datasheet = ""
        properties: dict[str, str] = {}

        for prop in _find_all(fp, "property"):
            if len(prop) < 3:
                continue
            key = str(prop[1])
            val = str(prop[2])
            properties[key] = val
            if key == "Reference":
                ref = val
            elif key == "Value":
                value = val
            elif key == "Description":
                description = val
            elif key == "Datasheet":
                datasheet = val

        pads = [_parse_pad(p) for p in _find_all(fp, "pad")]

        comp = Component(
            reference=ref,
            value=value,
            footprint=footprint_name,
            x=x, y=y,
            rotation=rot,
            layer=layer,
            description=description,
            datasheet=datasheet,
            pads=pads,
            properties=properties,
        )
        components.append(comp)
    return components


def _parse_traces(board_node: list) -> list[Trace]:
    traces = []
    for seg in _find_all(board_node, "segment"):
        start = _find(seg, "start")
        end = _find(seg, "end")
        if not start or not end:
            continue
        width_node = _find(seg, "width")
        layer_node = _find(seg, "layer")
        net_node = _find(seg, "net")
        traces.append(Trace(
            x1=float(start[1]), y1=float(start[2]),
            x2=float(end[1]),   y2=float(end[2]),
            width=float(width_node[1]) if width_node else 0.25,
            layer=str(layer_node[1]) if layer_node else "F.Cu",
            net_name=str(net_node[1]) if net_node else "",
        ))
    return traces


def _parse_vias(board_node: list) -> list[Via]:
    vias = []
    for via in _find_all(board_node, "via"):
        at = _find(via, "at")
        drill_n = _find(via, "drill")
        size_n = _find(via, "size")
        net_n = _find(via, "net")
        vias.append(Via(
            x=float(at[1]) if at else 0.0,
            y=float(at[2]) if at else 0.0,
            drill=float(drill_n[1]) if drill_n else 0.8,
            size=float(size_n[1]) if size_n else 1.6,
            net_name=str(net_n[1]) if net_n else "",
        ))
    return vias


def _parse_graphic_lines(board_node: list) -> list[GraphicLine]:
    lines = []
    for gl in _find_all(board_node, "gr_line"):
        start = _find(gl, "start")
        end = _find(gl, "end")
        if not start or not end:
            continue
        width_n = _find(gl, "width") or _find(gl, "stroke")
        layer_n = _find(gl, "layer")
        w = 0.05
        if width_n:
            try:
                w = float(width_n[1])
            except (ValueError, IndexError):
                pass
        lines.append(GraphicLine(
            x1=float(start[1]), y1=float(start[2]),
            x2=float(end[1]),   y2=float(end[2]),
            width=w,
            layer=str(layer_n[1]) if layer_n else "Edge.Cuts",
        ))
    return lines


def _parse_graphic_arcs(board_node: list) -> list[GraphicArc]:
    arcs = []
    for ga in _find_all(board_node, "gr_arc"):
        center = _find(ga, "center") or _find(ga, "at")
        start = _find(ga, "start") or _find(ga, "end")
        angle_n = _find(ga, "angle")
        width_n = _find(ga, "width")
        layer_n = _find(ga, "layer")
        if not center or not start:
            continue
        arcs.append(GraphicArc(
            x=float(center[1]), y=float(center[2]),
            start_x=float(start[1]), start_y=float(start[2]),
            angle=float(angle_n[1]) if angle_n else 0.0,
            width=float(width_n[1]) if width_n else 0.05,
            layer=str(layer_n[1]) if layer_n else "Edge.Cuts",
        ))
    return arcs


def parse_kicad_pcb(path: str | Path) -> PCBBoard:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    tree = sexpdata.loads(text)

    if not tree or _sym(tree[0]) != "kicad_pcb":
        raise ValueError(f"Plik nie jest poprawnym .kicad_pcb: {path}")

    board_node = tree

    title_block = _find(board_node, "title_block")
    title = str(_val(title_block, "title", "")) if title_block else ""
    company = str(_val(title_block, "company", "")) if title_block else ""
    rev = str(_val(title_block, "rev", "")) if title_block else ""

    version_n = _find(board_node, "version")
    version = str(version_n[1]) if version_n else ""

    return PCBBoard(
        title=title,
        company=company,
        revision=rev,
        kicad_version=version,
        components=_parse_footprints(board_node),
        traces=_parse_traces(board_node),
        vias=_parse_vias(board_node),
        graphic_lines=_parse_graphic_lines(board_node),
        graphic_arcs=_parse_graphic_arcs(board_node),
        nets=_parse_nets(board_node),
        layers=_parse_layers(board_node),
    )
