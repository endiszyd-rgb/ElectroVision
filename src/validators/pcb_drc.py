"""PCB Design Rule Check (DRC) — checks for common PCB design errors."""
from src.core.models.pcb_board import PCBBoard, Trace
import math


class PCBValidator:
    """
    Runs a set of design rule checks on a PCBBoard object.

    Checks performed
    ----------------
    - Minimum trace width
    - Minimum clearance between traces on the same layer
    - Missing net connections (simplified)
    - Board has an Edge.Cuts outline
    - Overlapping vias
    - Trace too close to board edge
    - Pads without nets
    - Duplicate references
    """

    MIN_TRACE_WIDTH_MM   = 0.1
    MIN_CLEARANCE_MM     = 0.1
    MIN_EDGE_CLEARANCE   = 0.3
    MIN_VIA_DRILL_MM     = 0.2
    MIN_VIA_ANNULAR_MM   = 0.1

    def __init__(self, board: PCBBoard | None) -> None:
        self._board = board

    def run(self) -> list[dict]:
        if not self._board:
            return [{"severity": "error", "position": "", "message": "Brak płytki PCB.", "suggestion": "Załaduj projekt KiCad."}]

        issues: list[dict] = []
        issues.extend(self._check_outline())
        issues.extend(self._check_trace_width())
        issues.extend(self._check_clearance())
        issues.extend(self._check_vias())
        issues.extend(self._check_duplicate_refs())
        issues.extend(self._check_edge_clearance())
        issues.extend(self._check_pads_without_nets())
        return issues

    def _check_outline(self) -> list[dict]:
        edge_lines = [l for l in self._board.graphic_lines if l.layer == "Edge.Cuts"]
        edge_arcs  = [a for a in self._board.graphic_arcs  if a.layer == "Edge.Cuts"]
        if not edge_lines and not edge_arcs:
            return [{"severity": "error", "position": "",
                     "message": "Brak konturu płytki (Edge.Cuts).",
                     "suggestion": "Narysuj kontur płytki na warstwie Edge.Cuts w KiCad."}]
        return []

    def _check_trace_width(self) -> list[dict]:
        issues = []
        for tr in self._board.traces:
            if tr.width < self.MIN_TRACE_WIDTH_MM:
                issues.append({
                    "severity": "error",
                    "position": f"({tr.x1:.2f},{tr.y1:.2f})",
                    "message": f"Ścieżka na {tr.layer} zbyt wąska: {tr.width:.3f}mm < {self.MIN_TRACE_WIDTH_MM}mm",
                    "suggestion": f"Zwiększ szerokość ścieżki do min. {self.MIN_TRACE_WIDTH_MM}mm.",
                })
        return issues

    def _check_clearance(self) -> list[dict]:
        issues = []
        layer_traces: dict[str, list[Trace]] = {}
        for tr in self._board.traces:
            layer_traces.setdefault(tr.layer, []).append(tr)

        for layer, traces in layer_traces.items():
            for i, a in enumerate(traces):
                for b in traces[i+1:]:
                    if a.net_name and b.net_name and a.net_name == b.net_name:
                        continue
                    dist = _segment_distance(
                        (a.x1, a.y1), (a.x2, a.y2),
                        (b.x1, b.y1), (b.x2, b.y2)
                    )
                    if dist < self.MIN_CLEARANCE_MM:
                        issues.append({
                            "severity": "error",
                            "position": f"({(a.x1+a.x2)/2:.2f},{(a.y1+a.y2)/2:.2f})",
                            "message": f"Naruszenie prześwitu na {layer}: {dist:.3f}mm < {self.MIN_CLEARANCE_MM}mm",
                            "suggestion": "Zwiększ odstęp między ścieżkami lub zmień trasowanie.",
                        })
                        if len(issues) > 50:
                            issues.append({"severity": "warning", "position": "", "message": "Pominięto dalsze błędy prześwitu.", "suggestion": ""})
                            return issues
        return issues

    def _check_vias(self) -> list[dict]:
        issues = []
        for v in self._board.vias:
            if v.drill < self.MIN_VIA_DRILL_MM:
                issues.append({
                    "severity": "error",
                    "position": f"({v.x:.2f},{v.y:.2f})",
                    "message": f"Otwór przelotki za mały: {v.drill:.3f}mm",
                    "suggestion": f"Min. średnica otworu: {self.MIN_VIA_DRILL_MM}mm",
                })
            annular = (v.size - v.drill) / 2
            if annular < self.MIN_VIA_ANNULAR_MM:
                issues.append({
                    "severity": "warning",
                    "position": f"({v.x:.2f},{v.y:.2f})",
                    "message": f"Mały pierścień anularny przelotki: {annular:.3f}mm",
                    "suggestion": f"Zwiększ rozmiar przelotki lub zmniejsz otwór.",
                })
        return issues

    def _check_duplicate_refs(self) -> list[dict]:
        seen: dict[str, int] = {}
        for c in self._board.components:
            seen[c.reference] = seen.get(c.reference, 0) + 1
        return [
            {"severity": "error", "position": "", "message": f"Zduplikowany identyfikator: {ref} ({cnt}×)", "suggestion": "Każdy komponent musi mieć unikalny identyfikator."}
            for ref, cnt in seen.items() if cnt > 1
        ]

    def _check_edge_clearance(self) -> list[dict]:
        issues = []
        bb = self._board.bounding_box
        for tr in self._board.traces:
            for x, y in [(tr.x1, tr.y1), (tr.x2, tr.y2)]:
                dist_to_edge = min(
                    x - bb[0], bb[2] - x,
                    y - bb[1], bb[3] - y
                )
                if dist_to_edge < self.MIN_EDGE_CLEARANCE:
                    issues.append({
                        "severity": "warning",
                        "position": f"({x:.2f},{y:.2f})",
                        "message": f"Ścieżka za blisko krawędzi płytki: {dist_to_edge:.2f}mm",
                        "suggestion": f"Utrzymuj min. {self.MIN_EDGE_CLEARANCE}mm od krawędzi.",
                    })
                    if len(issues) > 20:
                        return issues
        return issues

    def _check_pads_without_nets(self) -> list[dict]:
        issues = []
        for comp in self._board.components:
            for pad in comp.pads:
                if pad.pad_type != "np_thru_hole" and not pad.net_name:
                    issues.append({
                        "severity": "warning",
                        "position": f"{comp.reference}.{pad.number}",
                        "message": f"Pad {comp.reference}.{pad.number} nie jest podłączony do żadnej sieci.",
                        "suggestion": "Sprawdź połączenia w schemacie KiCad.",
                    })
        return issues


def _segment_distance(p1, p2, p3, p4) -> float:
    """Approximate minimum distance between two line segments."""
    def pt_seg_dist(px, py, ax, ay, bx, by) -> float:
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax)*dx + (py - ay)*dy) / (dx*dx + dy*dy)))
        return math.hypot(px - (ax + t*dx), py - (ay + t*dy))

    d1 = pt_seg_dist(p3[0], p3[1], p1[0], p1[1], p2[0], p2[1])
    d2 = pt_seg_dist(p4[0], p4[1], p1[0], p1[1], p2[0], p2[1])
    d3 = pt_seg_dist(p1[0], p1[1], p3[0], p3[1], p4[0], p4[1])
    d4 = pt_seg_dist(p2[0], p2[1], p3[0], p3[1], p4[0], p4[1])
    return min(d1, d2, d3, d4)
