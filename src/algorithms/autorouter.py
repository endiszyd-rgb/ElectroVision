"""Autorouter PCB — algorytm Lee (wave-propagation maze routing) na siatce 2-warstwowej.

Łączy niepołączone pady tej samej sieci ścieżkami na F.Cu/B.Cu, wstawiając
przelotki (Via) przy zmianie warstwy. Wykorzystuje Dijkstrę na grafie komórek
siatki (8 kierunków na warstwie + przejście międzywarstwowe), z istniejącymi
padami/ścieżkami/przelotkami jako przeszkodami.

Nie jest to router produkcyjnej jakości (brak pełnej obsługi DRC, stref miedzi,
łuków) — to praktyczny silnik do szybkiego automatycznego trasowania prostych
i średnio złożonych płytek, z możliwością ręcznej korekty w edytorze PCB.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from src.core.models.pcb_board import PCBBoard, Trace, Via
from src.core.models.component import Component, Pad

ROUTING_LAYERS = ["F.Cu", "B.Cu"]

# Koszt względny ruchu na siatce
_COST_STRAIGHT = 1.0
_COST_DIAGONAL = math.sqrt(2)
_COST_VIA       = 8.0   # "kara" za zmianę warstwy (zachęca do trasowania na jednej warstwie)

# 8 kierunków ruchu na warstwie: (dcol, drow, koszt)
_MOVES = [
    (1, 0, _COST_STRAIGHT), (-1, 0, _COST_STRAIGHT),
    (0, 1, _COST_STRAIGHT), (0, -1, _COST_STRAIGHT),
    (1, 1, _COST_DIAGONAL), (1, -1, _COST_DIAGONAL),
    (-1, 1, _COST_DIAGONAL), (-1, -1, _COST_DIAGONAL),
]


# ── Wyniki ─────────────────────────────────────────────────────────────────────

@dataclass
class AutorouteResult:
    traces_added: list[Trace] = field(default_factory=list)
    vias_added:   list[Via]   = field(default_factory=list)
    nets_routed:  list[str]   = field(default_factory=list)
    nets_failed:  list[str]   = field(default_factory=list)
    total_length_mm: float = 0.0

    @property
    def success_rate(self) -> float:
        total = len(self.nets_routed) + len(self.nets_failed)
        return (len(self.nets_routed) / total * 100.0) if total else 0.0

    @property
    def summary(self) -> str:
        return (f"Trasowano {len(self.nets_routed)}/{len(self.nets_routed)+len(self.nets_failed)} "
                f"sieci ({self.success_rate:.0f}%), {len(self.traces_added)} segmentów, "
                f"{len(self.vias_added)} przelotek, {self.total_length_mm:.1f} mm ścieżek.")


# ── Pozycje padów ────────────────────────────────────────────────────────────

def pad_world_pos(comp: Component, pad: Pad) -> tuple[float, float]:
    """Pozycja pada w układzie świata płytki, z uwzględnieniem obrotu komponentu."""
    if not comp.rotation:
        return (comp.x + pad.x, comp.y + pad.y)
    rad = math.radians(comp.rotation)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    rx = pad.x * cos_a - pad.y * sin_a
    ry = pad.x * sin_a + pad.y * cos_a
    return (comp.x + rx, comp.y + ry)


def collect_unrouted_nets(board: PCBBoard) -> dict[str, list[tuple[float, float]]]:
    """Zwraca {nazwa_sieci: [pozycje padów]} dla sieci niepołączonych w pełni.

    Heurystyka: sieć z N padami uznajemy za połączoną, gdy ma >= N-1 segmentów
    ścieżek przypisanych do tej sieci (drzewo rozpinające). To uproszczenie —
    nie weryfikuje topologii połączeń, tylko liczność.
    """
    net_positions: dict[str, list[tuple[float, float]]] = {}
    for comp in board.components:
        for pad in comp.pads:
            if not pad.net_name:
                continue
            net_positions.setdefault(pad.net_name, []).append(pad_world_pos(comp, pad))

    trace_count: dict[str, int] = {}
    for t in board.traces:
        if t.net_name:
            trace_count[t.net_name] = trace_count.get(t.net_name, 0) + 1

    unrouted: dict[str, list[tuple[float, float]]] = {}
    for net, positions in net_positions.items():
        if len(positions) < 2:
            continue
        needed = len(positions) - 1
        if trace_count.get(net, 0) < needed:
            unrouted[net] = positions
    return unrouted


# ── Siatka ────────────────────────────────────────────────────────────────────

class RouteGrid:
    """Siatka komórek (col, row) x warstwa, z maskami przeszkód."""

    def __init__(self, min_x: float, min_y: float, max_x: float, max_y: float,
                 cell_mm: float = 0.5, layers: list[str] | None = None,
                 margin_cells: int = 4) -> None:
        self.cell_mm = max(0.05, cell_mm)
        self.layers = layers or list(ROUTING_LAYERS)
        self.min_x = min_x - margin_cells * self.cell_mm
        self.min_y = min_y - margin_cells * self.cell_mm
        span_x = (max_x - min_x) + 2 * margin_cells * self.cell_mm
        span_y = (max_y - min_y) + 2 * margin_cells * self.cell_mm
        self.cols = max(2, int(math.ceil(span_x / self.cell_mm)) + 1)
        self.rows = max(2, int(math.ceil(span_y / self.cell_mm)) + 1)
        # blocked[layer_idx] = set of (col, row)
        self.blocked: dict[int, set[tuple[int, int]]] = {
            i: set() for i in range(len(self.layers))
        }

    def layer_idx(self, layer_name: str) -> int:
        try:
            return self.layers.index(layer_name)
        except ValueError:
            return 0

    def to_cell(self, x: float, y: float) -> tuple[int, int]:
        col = int(round((x - self.min_x) / self.cell_mm))
        row = int(round((y - self.min_y) / self.cell_mm))
        return (max(0, min(self.cols - 1, col)), max(0, min(self.rows - 1, row)))

    def to_world(self, col: int, row: int) -> tuple[float, float]:
        return (self.min_x + col * self.cell_mm, self.min_y + row * self.cell_mm)

    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def is_blocked(self, col: int, row: int, layer_idx: int) -> bool:
        return (col, row) in self.blocked.get(layer_idx, ())

    def block_disc(self, x: float, y: float, radius_mm: float,
                    layer_idx: int | None = None) -> None:
        """Blokuje komórki w okręgu o danym promieniu wokół (x,y).
        layer_idx=None blokuje na wszystkich warstwach (np. via przewlekana)."""
        cx, cy = self.to_cell(x, y)
        r_cells = max(1, int(math.ceil(radius_mm / self.cell_mm)))
        layer_indices = range(len(self.layers)) if layer_idx is None else [layer_idx]
        for dc in range(-r_cells, r_cells + 1):
            for dr in range(-r_cells, r_cells + 1):
                if dc * dc + dr * dr > r_cells * r_cells:
                    continue
                c, r = cx + dc, cy + dr
                if self.in_bounds(c, r):
                    for li in layer_indices:
                        self.blocked[li].add((c, r))

    def block_segment(self, x1: float, y1: float, x2: float, y2: float,
                       radius_mm: float, layer_idx: int) -> None:
        """Blokuje komórki wzdłuż odcinka (np. istniejąca ścieżka)."""
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(math.ceil(dist / (self.cell_mm * 0.5))))
        for i in range(steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            self.block_disc(x, y, radius_mm, layer_idx)

    def unblock_at(self, x: float, y: float, layer_idx: int | None = None) -> None:
        """Odblokowuje pojedynczą komórkę (np. pad startowy/celowy)."""
        cell = self.to_cell(x, y)
        layer_indices = range(len(self.layers)) if layer_idx is None else [layer_idx]
        for li in layer_indices:
            self.blocked[li].discard(cell)


def build_grid_from_board(board: PCBBoard, cell_mm: float = 0.5,
                           clearance_mm: float = 0.25,
                           layers: list[str] | None = None) -> RouteGrid:
    """Tworzy siatkę z przeszkodami z istniejących padów, ścieżek i przelotek."""
    bb = board.bounding_box
    grid = RouteGrid(bb[0], bb[1], bb[2], bb[3], cell_mm=cell_mm, layers=layers)

    for comp in board.components:
        for pad in comp.pads:
            wx, wy = pad_world_pos(comp, pad)
            pad_r = max(pad.width, pad.height) / 2.0 + clearance_mm
            if pad.pad_type == "thru_hole" or pad.drill > 0:
                grid.block_disc(wx, wy, pad_r, layer_idx=None)
            else:
                layer_idx = grid.layer_idx(comp.layer if comp.layer in grid.layers else grid.layers[0])
                grid.block_disc(wx, wy, pad_r, layer_idx=layer_idx)

    for t in board.traces:
        if t.layer not in grid.layers:
            continue
        li = grid.layer_idx(t.layer)
        grid.block_segment(t.x1, t.y1, t.x2, t.y2, t.width / 2.0 + clearance_mm, li)

    for v in board.vias:
        grid.block_disc(v.x, v.y, v.size / 2.0 + clearance_mm, layer_idx=None)

    return grid


# ── Routing dwóch punktów (Dijkstra) ────────────────────────────────────────────

def _heuristic(col: int, row: int, goal_col: int, goal_row: int) -> float:
    return math.hypot(col - goal_col, row - goal_row)


def route_two_points(grid: RouteGrid, start: tuple[float, float], end: tuple[float, float],
                      start_layer: str = "F.Cu", end_layer: str | None = None,
                      max_iterations: int = 200_000
                      ) -> list[tuple[float, float, str]] | None:
    """Znajduje trasę (A*) między dwoma punktami świata.

    Zwraca listę punktów świata (x, y, layer) wzdłuż trasy, włącznie z punktami
    startowym i końcowym, lub None jeśli nie znaleziono trasy.
    """
    end_layer = end_layer or start_layer
    s_col, s_row = grid.to_cell(*start)
    e_col, e_row = grid.to_cell(*end)
    s_li = grid.layer_idx(start_layer)
    e_li = grid.layer_idx(end_layer)

    # Tymczasowo odblokuj komórki start/end (to są legalne punkty, nie przeszkody)
    grid.unblock_at(*start)
    grid.unblock_at(*end)

    start_state = (s_col, s_row, s_li)
    goal_state  = (e_col, e_row, e_li)

    if start_state == goal_state:
        return [(*start, start_layer)]

    # (f_score, g_score, state)
    open_heap: list[tuple[float, float, tuple[int, int, int]]] = []
    heapq.heappush(open_heap, (0.0, 0.0, start_state))
    g_score: dict[tuple[int, int, int], float] = {start_state: 0.0}
    came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    visited: set[tuple[int, int, int]] = set()

    iterations = 0
    found = False

    while open_heap and iterations < max_iterations:
        iterations += 1
        _, g, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        if current == goal_state:
            found = True
            break

        ccol, crow, cli = current

        # Ruchy na tej samej warstwie
        for dc, dr, cost in _MOVES:
            nc, nr = ccol + dc, crow + dr
            if not grid.in_bounds(nc, nr):
                continue
            if grid.is_blocked(nc, nr, cli):
                continue
            nstate = (nc, nr, cli)
            ng = g + cost
            if ng < g_score.get(nstate, math.inf):
                g_score[nstate] = ng
                came_from[nstate] = current
                f = ng + _heuristic(nc, nr, e_col, e_row)
                heapq.heappush(open_heap, (f, ng, nstate))

        # Zmiana warstwy (via) w tym samym miejscu
        for other_li in range(len(grid.layers)):
            if other_li == cli:
                continue
            if grid.is_blocked(ccol, crow, other_li):
                continue
            nstate = (ccol, crow, other_li)
            ng = g + _COST_VIA
            if ng < g_score.get(nstate, math.inf):
                g_score[nstate] = ng
                came_from[nstate] = current
                f = ng + _heuristic(ccol, crow, e_col, e_row)
                heapq.heappush(open_heap, (f, ng, nstate))

    if not found:
        return None

    # Rekonstrukcja trasy
    path_states = [goal_state]
    cur = goal_state
    while cur != start_state:
        cur = came_from[cur]
        path_states.append(cur)
    path_states.reverse()

    result = []
    for col, row, li in path_states:
        wx, wy = grid.to_world(col, row)
        result.append((wx, wy, grid.layers[li]))
    # Zastąp pierwszy/ostatni punkt dokładną pozycją pada (nie zaokrągloną do siatki)
    if result:
        result[0] = (start[0], start[1], result[0][2])
        result[-1] = (end[0], end[1], result[-1][2])
    return result


def _simplify_path(path: list[tuple[float, float, str]]
                    ) -> list[tuple[float, float, str]]:
    """Usuwa kolinearne punkty pośrednie tego samego segmentu/warstwy."""
    if len(path) <= 2:
        return path
    simplified = [path[0]]
    for i in range(1, len(path) - 1):
        px, py, pl = simplified[-1]
        cx, cy, cl = path[i]
        nx, ny, nl = path[i + 1]
        if pl != cl or cl != nl:
            simplified.append(path[i])
            continue
        # Wektory: czy (prev->cur) i (cur->next) są współliniowe?
        v1 = (cx - px, cy - py)
        v2 = (nx - cx, ny - cy)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) > 1e-6:
            simplified.append(path[i])
    simplified.append(path[-1])
    return simplified


def _path_to_traces_vias(path: list[tuple[float, float, str]], trace_width: float,
                          via_drill: float, via_size: float, net_name: str
                          ) -> tuple[list[Trace], list[Via]]:
    traces: list[Trace] = []
    vias: list[Via] = []
    simplified = _simplify_path(path)
    for i in range(len(simplified) - 1):
        x1, y1, l1 = simplified[i]
        x2, y2, l2 = simplified[i + 1]
        if l1 != l2:
            vias.append(Via(x=x1, y=y1, drill=via_drill, size=via_size, net_name=net_name))
            continue
        if math.hypot(x2 - x1, y2 - y1) < 1e-6:
            continue
        traces.append(Trace(x1=x1, y1=y1, x2=x2, y2=y2, width=trace_width,
                            layer=l1, net_name=net_name))
    return traces, vias


def _path_length(path: list[tuple[float, float, str]]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        x1, y1, _ = path[i]
        x2, y2, _ = path[i + 1]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


# ── Trasowanie pojedynczej sieci (wielo-padowej) ─────────────────────────────

def route_net(grid: RouteGrid, positions: list[tuple[float, float]],
              trace_width: float = 0.25, via_drill: float = 0.3,
              via_size: float = 0.6, net_name: str = "",
              preferred_layer: str = "F.Cu") -> tuple[list[Trace], list[Via]] | None:
    """Trasuje sieć z N pozycji padów metodą Prima (MST): zaczyna od pierwszego
    pada, dołącza najbliższy niepołączony pad jeden po drugim."""
    if len(positions) < 2:
        return None

    connected = [positions[0]]
    remaining = list(positions[1:])
    all_traces: list[Trace] = []
    all_vias: list[Via] = []

    while remaining:
        best_path = None
        best_idx = -1
        best_len = math.inf
        for idx, target in enumerate(remaining):
            # Spróbuj połączyć z każdym już podłączonym punktem; weź najlepszy
            for src in connected:
                path = route_two_points(grid, src, target, start_layer=preferred_layer)
                if path is None:
                    continue
                plen = _path_length(path)
                if plen < best_len:
                    best_len = plen
                    best_path = path
                    best_idx = idx
        if best_path is None:
            return None  # nie udało się podłączyć reszty padów

        traces, vias = _path_to_traces_vias(best_path, trace_width, via_drill,
                                            via_size, net_name)
        all_traces.extend(traces)
        all_vias.extend(vias)

        # Zablokuj nowo dodaną trasę jako przeszkodę dla kolejnych segmentów
        for tr in traces:
            li = grid.layer_idx(tr.layer)
            grid.block_segment(tr.x1, tr.y1, tr.x2, tr.y2, tr.width / 2.0, li)
        for v in vias:
            grid.block_disc(v.x, v.y, v.size / 2.0, layer_idx=None)

        connected.append(remaining.pop(best_idx))

    return all_traces, all_vias


# ── Główna funkcja: autoroutuj całą płytkę ───────────────────────────────────

def autoroute_board(board: PCBBoard, cell_mm: float = 0.5, trace_width: float = 0.25,
                    clearance_mm: float = 0.25, via_drill: float = 0.3,
                    via_size: float = 0.6, layers: list[str] | None = None,
                    max_nets: int | None = None,
                    apply_to_board: bool = True) -> AutorouteResult:
    """Autoroutuje wszystkie niepołączone sieci na płytce.

    Sieci sortowane są po liczbie padów (najprostsze najpierw), żeby zmaksymalizować
    szansę powodzenia zanim siatka zapełni się przeszkodami. Gdy `apply_to_board`
    jest True, nowe Trace/Via są dopisywane do `board.traces` / `board.vias`.
    """
    result = AutorouteResult()
    unrouted = collect_unrouted_nets(board)
    if not unrouted:
        return result

    nets_sorted = sorted(unrouted.items(), key=lambda kv: len(kv[1]))
    if max_nets is not None:
        nets_sorted = nets_sorted[:max_nets]

    grid = build_grid_from_board(board, cell_mm=cell_mm, clearance_mm=clearance_mm,
                                 layers=layers)

    for net_name, positions in nets_sorted:
        routed = route_net(grid, positions, trace_width=trace_width,
                           via_drill=via_drill, via_size=via_size,
                           net_name=net_name)
        if routed is None:
            result.nets_failed.append(net_name)
            continue
        traces, vias = routed
        result.traces_added.extend(traces)
        result.vias_added.extend(vias)
        result.nets_routed.append(net_name)
        result.total_length_mm += sum(
            math.hypot(t.x2 - t.x1, t.y2 - t.y1) for t in traces
        )

    if apply_to_board:
        board.traces.extend(result.traces_added)
        board.vias.extend(result.vias_added)

    return result
