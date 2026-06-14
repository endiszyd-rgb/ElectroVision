"""Project save / load — .evproj JSON format."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard, Trace, Via, GraphicLine, GraphicArc, CopperZone
from src.core.models.component import Component, Pad
from src.core.models.layer import Layer
from src.core.models.net import Net

_VERSION = 1


# ── Save ─────────────────────────────────────────────────────────────────────

def save_project(project: Project, path: str) -> None:
    board = project.board
    data: dict = {
        "evproj_version": _VERSION,
        "saved_at": datetime.now().isoformat(),
        "name": project.name,
        "board": None,
    }
    if board:
        data["board"] = {
            "title":         board.title,
            "company":       board.company,
            "revision":      board.revision,
            "kicad_version": board.kicad_version,
            "layers": [
                {"name": l.name, "number": l.number, "layer_type": l.layer_type}
                for l in board.layers
            ],
            "nets": [
                {"name": n.name, "number": n.number}
                for n in board.nets
            ],
            "components": [
                {
                    "reference":       c.reference,
                    "value":           c.value,
                    "footprint":       c.footprint,
                    "x":               c.x,
                    "y":               c.y,
                    "rotation":        c.rotation,
                    "layer":           c.layer,
                    "description":     c.description,
                    "datasheet":       c.datasheet,
                    "manufacturer":    c.manufacturer,
                    "manufacturer_pn": c.manufacturer_pn,
                    "properties":      c.properties,
                    "pads": [
                        {
                            "number":   p.number,
                            "pad_type": p.pad_type,
                            "shape":    p.shape,
                            "x":        p.x,
                            "y":        p.y,
                            "width":    p.width,
                            "height":   p.height,
                            "net_name": p.net_name,
                            "drill":    p.drill,
                        }
                        for p in c.pads
                    ],
                }
                for c in board.components
            ],
            "traces": [
                {
                    "x1": t.x1, "y1": t.y1,
                    "x2": t.x2, "y2": t.y2,
                    "width": t.width, "layer": t.layer,
                    "net_name": t.net_name,
                }
                for t in board.traces
            ],
            "vias": [
                {
                    "x": v.x, "y": v.y,
                    "drill": v.drill, "size": v.size,
                    "net_name": v.net_name,
                }
                for v in board.vias
            ],
            "graphic_lines": [
                {
                    "x1": g.x1, "y1": g.y1,
                    "x2": g.x2, "y2": g.y2,
                    "width": g.width, "layer": g.layer,
                }
                for g in board.graphic_lines
            ],
            "zones": [
                {
                    "points":    z.points,
                    "net_name":  z.net_name,
                    "layer":     z.layer,
                    "clearance": z.clearance,
                    "priority":  z.priority,
                }
                for z in board.zones
            ],
        }

    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Load ─────────────────────────────────────────────────────────────────────

def load_project(path: str) -> Project:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    ver = raw.get("evproj_version", 0)
    if ver > _VERSION:
        raise ValueError(f"Plik zapisany w nowszej wersji ({ver}). Zaktualizuj ElectroVision.")

    name      = raw.get("name", Path(path).stem)
    board_raw = raw.get("board")

    board: Optional[PCBBoard] = None
    if board_raw:
        layers = [
            Layer(l["name"], l.get("number", 0), l.get("layer_type", "signal"))
            for l in board_raw.get("layers", [])
        ]
        nets = [
            Net(n.get("name", ""), n.get("number", 0))
            for n in board_raw.get("nets", [])
        ]
        components = []
        for c in board_raw.get("components", []):
            pads = [
                Pad(
                    number=p.get("number", ""),
                    pad_type=p.get("pad_type", "smd"),
                    shape=p.get("shape", "rect"),
                    x=p.get("x", 0.0), y=p.get("y", 0.0),
                    width=p.get("width", 1.0), height=p.get("height", 1.0),
                    net_name=p.get("net_name", ""),
                    drill=p.get("drill", 0.0),
                )
                for p in c.get("pads", [])
            ]
            components.append(Component(
                reference=c.get("reference", "?"),
                value=c.get("value", ""),
                footprint=c.get("footprint", ""),
                x=c.get("x", 0.0), y=c.get("y", 0.0),
                rotation=c.get("rotation", 0.0),
                layer=c.get("layer", "F.Cu"),
                description=c.get("description", ""),
                datasheet=c.get("datasheet", ""),
                manufacturer=c.get("manufacturer", ""),
                manufacturer_pn=c.get("manufacturer_pn", ""),
                properties=c.get("properties", {}),
                pads=pads,
            ))
        traces = [
            Trace(
                x1=t["x1"], y1=t["y1"], x2=t["x2"], y2=t["y2"],
                width=t.get("width", 0.25), layer=t.get("layer", "F.Cu"),
                net_name=t.get("net_name", ""),
            )
            for t in board_raw.get("traces", [])
        ]
        vias = [
            Via(
                x=v["x"], y=v["y"],
                drill=v.get("drill", 0.4), size=v.get("size", 0.8),
                net_name=v.get("net_name", ""),
            )
            for v in board_raw.get("vias", [])
        ]
        graphic_lines = [
            GraphicLine(
                x1=g["x1"], y1=g["y1"], x2=g["x2"], y2=g["y2"],
                width=g.get("width", 0.05), layer=g.get("layer", "Edge.Cuts"),
            )
            for g in board_raw.get("graphic_lines", [])
        ]
        zones = [
            CopperZone(
                points=z.get("points", []),
                net_name=z.get("net_name", ""),
                layer=z.get("layer", "F.Cu"),
                clearance=z.get("clearance", 0.2),
                priority=z.get("priority", 0),
            )
            for z in board_raw.get("zones", [])
        ]
        board = PCBBoard(
            title=board_raw.get("title", name),
            company=board_raw.get("company", ""),
            revision=board_raw.get("revision", ""),
            kicad_version=board_raw.get("kicad_version", ""),
            components=components,
            traces=traces,
            vias=vias,
            graphic_lines=graphic_lines,
            nets=nets,
            layers=layers,
            zones=zones,
        )

    return Project(name=name, path=Path(path), board=board)


# ── Recent projects ───────────────────────────────────────────────────────────

_RECENT_FILE = Path.home() / ".electrovision_recent.json"
_MAX_RECENT  = 10


def add_recent(path: str) -> None:
    recent = load_recent()
    path = str(Path(path).resolve())
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:_MAX_RECENT]
    _RECENT_FILE.write_text(json.dumps(recent, indent=2), encoding="utf-8")


def load_recent() -> list[str]:
    try:
        return json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def clear_missing_recent() -> list[str]:
    recent = [p for p in load_recent() if Path(p).exists()]
    _RECENT_FILE.write_text(json.dumps(recent, indent=2), encoding="utf-8")
    return recent
