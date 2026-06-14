"""Netlist export — convert PCBBoard nets to CSV / KiCad netlist format."""
from __future__ import annotations
import csv
import io
from collections import defaultdict

from src.core.models.pcb_board import PCBBoard
from src.core.models.component import Component


def generate_netlist_csv(board: PCBBoard) -> str:
    """Return CSV with columns: Net, Component, Pin, X_mm, Y_mm."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["Net", "Component", "Reference", "Pin", "X_mm", "Y_mm"])
    for comp in sorted(board.components, key=lambda c: c.reference):
        for pad in comp.pads:
            net = pad.net_name or ""
            writer.writerow([
                net,
                comp.value,
                comp.reference,
                pad.number,
                f"{comp.x + pad.x:.4f}",
                f"{comp.y + pad.y:.4f}",
            ])
    return buf.getvalue()


def generate_net_summary_csv(board: PCBBoard) -> str:
    """Return CSV with per-net component/pin count and member list."""
    nets: dict[str, list[str]] = defaultdict(list)
    for comp in board.components:
        for pad in comp.pads:
            if pad.net_name:
                nets[pad.net_name].append(f"{comp.reference}.{pad.number}")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["Net", "Pins", "Members"])
    for net_name in sorted(nets):
        members = nets[net_name]
        writer.writerow([net_name, len(members), "  ".join(members)])
    return buf.getvalue()


def generate_kicad_netlist(board: PCBBoard, project_name: str = "PCB") -> str:
    """Return a simple KiCad-compatible netlist in bracket notation."""
    lines = [
        f"(export (version D)",
        f"  (design",
        f"    (source \"{project_name}\")",
        f"    (tool \"ElectroVision\"))",
        f"  (components",
    ]
    for comp in sorted(board.components, key=lambda c: c.reference):
        lines.append(f"    (comp (ref \"{comp.reference}\")")
        lines.append(f"      (value \"{comp.value}\")")
        lines.append(f"      (footprint \"{comp.footprint}\"))")

    lines.append("  )")
    lines.append("  (nets")
    nets: dict[str, list[str]] = defaultdict(list)
    for comp in board.components:
        for pad in comp.pads:
            if pad.net_name:
                nets[pad.net_name].append(f"{comp.reference}.{pad.number}")
    for net_name in sorted(nets):
        members = nets[net_name]
        lines.append(f"    (net (name \"{net_name}\")")
        for m in members:
            ref, pin = (m.split(".", 1) + ["1"])[:2]
            lines.append(f"      (node (ref \"{ref}\") (pin \"{pin}\"))")
        lines.append("    )")
    lines.append("  ))")
    return "\n".join(lines)
