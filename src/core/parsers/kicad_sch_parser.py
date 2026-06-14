"""Parser for .kicad_sch files (KiCad 6+ S-expression format)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SchComponent:
    reference: str
    value: str
    lib_id: str
    x: float
    y: float
    unit: int = 1
    in_bom: bool = True
    on_board: bool = True
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class SchWire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class SchLabel:
    text: str
    x: float
    y: float
    kind: str = "label"  # label | global_label | power_port


@dataclass
class SchNoConnect:
    x: float
    y: float


@dataclass
class SchJunction:
    x: float
    y: float


@dataclass
class Schematic:
    title: str = ""
    components: list[SchComponent] = field(default_factory=list)
    wires: list[SchWire] = field(default_factory=list)
    labels: list[SchLabel] = field(default_factory=list)
    no_connects: list[SchNoConnect] = field(default_factory=list)
    junctions: list[SchJunction] = field(default_factory=list)

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for c in self.components:
            xs.append(c.x); ys.append(c.y)
        for w in self.wires:
            xs += [w.x1, w.x2]; ys += [w.y1, w.y2]
        if not xs:
            return (0.0, 0.0, 200.0, 200.0)
        return (min(xs), min(ys), max(xs), max(ys))


def _tok(text: str) -> list:
    """Minimal S-expression tokenizer."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ' \t\n\r':
            i += 1
        elif ch == '(':
            tokens.append('('); i += 1
        elif ch == ')':
            tokens.append(')'); i += 1
        elif ch == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    j += 1
            tokens.append(text[i+1:j].replace('\\"', '"'))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\n\r()':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_tree(tokens: list, pos: int = 0) -> tuple[list, int]:
    """Parse S-expression into nested list tree."""
    result = []
    while pos < len(tokens):
        t = tokens[pos]
        if t == '(':
            pos += 1
            node, pos = _parse_tree(tokens, pos)
            result.append(node)
        elif t == ')':
            return result, pos + 1
        else:
            result.append(t)
            pos += 1
    return result, pos


def _find_all(tree, tag: str):
    """Yield all sub-lists whose first element == tag."""
    if isinstance(tree, list):
        if tree and tree[0] == tag:
            yield tree
        else:
            for child in tree:
                yield from _find_all(child, tag)


def _find_first(tree, tag: str) -> Optional[list]:
    for node in _find_all(tree, tag):
        return node
    return None


def _xy(node, idx_x=1, idx_y=2) -> tuple[float, float]:
    try:
        return float(node[idx_x]), float(node[idx_y])
    except Exception:
        return 0.0, 0.0


def parse_kicad_sch(path: str) -> Schematic:
    """Parse a .kicad_sch file and return a Schematic object."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    tokens = _tok(text)
    tree, _ = _parse_tree(tokens)

    sch = Schematic(title=Path(path).stem)

    for node in tree:
        if not isinstance(node, list) or not node:
            continue

        tag = node[0]

        # ── Symbols (components) ─────────────────────────────────────────────
        if tag == "symbol":
            lib_id_node = _find_first(node, "lib_id")
            at_node     = _find_first(node, "at")
            props: dict[str, str] = {}
            for p in _find_all(node, "property"):
                if len(p) >= 3:
                    props[str(p[1])] = str(p[2])

            reference = props.get("Reference", "?")
            value     = props.get("Value", "")
            lib_id    = lib_id_node[1] if lib_id_node and len(lib_id_node) > 1 else ""
            x, y = _xy(at_node) if at_node else (0.0, 0.0)

            in_bom_node    = _find_first(node, "in_bom")
            on_board_node  = _find_first(node, "on_board")
            in_bom    = (in_bom_node[1] if in_bom_node and len(in_bom_node) > 1 else "yes") == "yes"
            on_board  = (on_board_node[1] if on_board_node and len(on_board_node) > 1 else "yes") == "yes"

            sch.components.append(SchComponent(
                reference=reference, value=value, lib_id=lib_id,
                x=x, y=y, in_bom=in_bom, on_board=on_board, properties=props,
            ))

        # ── Wires ────────────────────────────────────────────────────────────
        elif tag == "wire":
            pts_node = _find_first(node, "pts")
            if pts_node:
                xy_nodes = [n for n in pts_node if isinstance(n, list) and n and n[0] == "xy"]
                if len(xy_nodes) >= 2:
                    x1, y1 = _xy(xy_nodes[0])
                    x2, y2 = _xy(xy_nodes[1])
                    sch.wires.append(SchWire(x1, y1, x2, y2))

        # ── Labels ───────────────────────────────────────────────────────────
        elif tag in ("label", "global_label", "power_port"):
            at_node = _find_first(node, "at")
            text_val = node[1] if len(node) > 1 and isinstance(node[1], str) else ""
            x, y = _xy(at_node) if at_node else (0.0, 0.0)
            sch.labels.append(SchLabel(text=text_val, x=x, y=y, kind=tag))

        # ── No-connect markers ───────────────────────────────────────────────
        elif tag == "no_connect":
            at_node = _find_first(node, "at")
            x, y = _xy(at_node) if at_node else (0.0, 0.0)
            sch.no_connects.append(SchNoConnect(x, y))

        # ── Junctions ────────────────────────────────────────────────────────
        elif tag == "junction":
            at_node = _find_first(node, "at")
            x, y = _xy(at_node) if at_node else (0.0, 0.0)
            sch.junctions.append(SchJunction(x, y))

    return sch
