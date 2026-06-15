"""Silnik opisowego tworzenia obiektów 3D → STL.

Obsługuje:
- Prymitywy: box, cylinder, sphere, cone, wedge
- Operacje CSG: union / difference (manifold3d)
- Obudowy, panele, uchwyty, standoffy, klipsy DIN — bez kodu
- Parser opisu tekstowego (naturalny język PL/EN)
- Eksport STL (trimesh)
"""
from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path

import numpy as np
import trimesh
import trimesh.creation as tc
import trimesh.transformations as tt


# ── Typy prymitywów i operacji ─────────────────────────────────────────────────

class PrimType(str, Enum):
    BOX      = "box"
    CYLINDER = "cylinder"
    SPHERE   = "sphere"
    CONE     = "cone"
    WEDGE    = "wedge"

class BoolOp(str, Enum):
    ADD = "add"   # union
    SUB = "sub"   # difference


@dataclass
class Primitive:
    ptype:  PrimType
    op:     BoolOp  = BoolOp.ADD
    x:      float   = 0.0   # pozycja środka (mm)
    y:      float   = 0.0
    z:      float   = 0.0
    width:  float   = 10.0  # X
    depth:  float   = 10.0  # Y
    height: float   = 10.0  # Z / wysokość
    radius: float   = 5.0   # dla cylinder/sphere/cone
    segs:   int     = 32    # segmenty cylindra
    label:  str     = ""

    def to_mesh(self) -> trimesh.Trimesh:
        if self.ptype == PrimType.BOX:
            m = tc.box([self.width, self.depth, self.height])
        elif self.ptype == PrimType.CYLINDER:
            m = tc.cylinder(self.radius, self.height, sections=self.segs)
        elif self.ptype == PrimType.SPHERE:
            m = tc.icosphere(radius=self.radius)
        elif self.ptype == PrimType.CONE:
            m = tc.cone(self.radius, self.height, sections=self.segs)
        elif self.ptype == PrimType.WEDGE:
            # trójkąt w XZ, rozciągnięty w Y
            verts = np.array([
                [0, 0, 0], [self.width, 0, 0], [0, 0, self.height],
                [0, self.depth, 0], [self.width, self.depth, 0], [0, self.depth, self.height],
            ], dtype=float)
            faces = np.array([
                [0, 2, 1], [3, 4, 5],
                [0, 1, 4], [0, 4, 3],
                [1, 2, 5], [1, 5, 4],
                [0, 3, 5], [0, 5, 2],
            ])
            m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
        else:
            m = tc.box([10, 10, 10])
        m.apply_translation([self.x, self.y, self.z])
        return m


# ── Operacje CSG ───────────────────────────────────────────────────────────────

def _csg_diff(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Odejmowanie (a - b) przez manifold3d."""
    try:
        result = trimesh.boolean.difference([a, b], engine="manifold")
        if result and len(result.faces) > 0:
            return result
    except Exception:
        pass
    return a  # fallback — zwróć oryginał

def _csg_union(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    """Suma (a + b) przez manifold3d."""
    try:
        result = trimesh.boolean.union([a, b], engine="manifold")
        if result and len(result.faces) > 0:
            return result
    except Exception:
        pass
    return trimesh.util.concatenate([a, b])


def build_scene(primitives: list[Primitive]) -> trimesh.Trimesh:
    """Buduje scenę 3D z listy prymitywów z operacjami CSG."""
    if not primitives:
        return tc.box([10, 10, 10])

    # Pierwsze ADD to baza
    base_prims = [p for p in primitives if p.op == BoolOp.ADD]
    sub_prims  = [p for p in primitives if p.op == BoolOp.SUB]

    if not base_prims:
        return tc.box([10, 10, 10])

    # Złącz wszystkie ADD w union
    result = base_prims[0].to_mesh()
    for p in base_prims[1:]:
        result = _csg_union(result, p.to_mesh())

    # Odejmij SUB
    for p in sub_prims:
        result = _csg_diff(result, p.to_mesh())

    return result


# ── Fabryki gotowych obiektów ──────────────────────────────────────────────────

@dataclass
class HoleSpec:
    x: float; y: float; diameter: float
    wall: str = ""     # "" = pionowy / "left"/"right"/"front"/"back" = poziomy

@dataclass
class CutoutSpec:
    wall: str          # "left"/"right"/"front"/"back"/"top"/"bottom"
    x_off: float = 0   # przesunięcie wzgl. centrum ściany
    z_off: float = 0   # przesunięcie wzgl. dna
    width: float = 9.0
    height: float = 4.0
    label: str = ""


def make_enclosure(
    width: float = 60.0,
    depth: float = 40.0,
    height: float = 25.0,
    wall: float = 2.0,
    lid: bool = True,
    standoffs: bool = True,
    standoff_h: float = 3.0,
    standoff_od: float = 3.0,
    standoff_id: float = 1.5,
    corner_r: float = 2.0,
    holes: list[HoleSpec] | None = None,
    cutouts: list[CutoutSpec] | None = None,
    separate_lid: bool = False,
) -> dict[str, trimesh.Trimesh]:
    """
    Obudowa: zewnętrzne pudełko minus wnętrze + standoffy + wieko.
    Zwraca dict: 'body' i opcjonalnie 'lid'.
    """
    holes   = holes   or []
    cutouts = cutouts or []

    # --- Korpus ---
    outer = tc.box([width, depth, height])
    inner_h = max(height - wall, 1.0)
    inner = tc.box([width - 2*wall, depth - 2*wall, inner_h])
    inner.apply_translation([0, 0, wall / 2])
    body = _csg_diff(outer, inner)

    # Standoffy (4 narożniki)
    if standoffs:
        ox = width  / 2 - standoff_od - wall + 0.5
        oy = depth  / 2 - standoff_od - wall + 0.5
        for sx, sy in [(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)]:
            std = tc.cylinder(standoff_od / 2, standoff_h, sections=24)
            std.apply_translation([sx, sy, wall + standoff_h / 2])
            body = _csg_union(body, std)
            if standoff_id > 0:
                hol = tc.cylinder(standoff_id / 2, standoff_h + wall, sections=24)
                hol.apply_translation([sx, sy, standoff_h / 2])
                body = _csg_diff(body, hol)

    # Pionowe otwory (np. śruby montażowe w dnie)
    for hole in holes:
        if not hole.wall:
            cyl = tc.cylinder(hole.diameter / 2, wall * 3, sections=32)
            cyl.apply_translation([hole.x - width/2, hole.y - depth/2, 0])
            body = _csg_diff(body, cyl)

    # Wycięcia w ściankach
    _wall_cut_thickness = wall + 2.0   # głębokość wycięcia (przelotowe)
    for cut in cutouts:
        cw, ch = cut.width + 0.4, cut.height + 0.4
        slot = tc.box([_wall_cut_thickness, cw, ch])
        if cut.wall == "left":
            slot.apply_translation([-width/2, cut.x_off, wall + cut.z_off + ch/2])
        elif cut.wall == "right":
            slot.apply_translation([width/2, cut.x_off, wall + cut.z_off + ch/2])
        elif cut.wall == "front":
            b = tc.box([cw, _wall_cut_thickness, ch])
            b.apply_translation([cut.x_off, -depth/2, wall + cut.z_off + ch/2])
            body = _csg_diff(body, b)
            continue
        elif cut.wall == "back":
            b = tc.box([cw, _wall_cut_thickness, ch])
            b.apply_translation([cut.x_off, depth/2, wall + cut.z_off + ch/2])
            body = _csg_diff(body, b)
            continue
        elif cut.wall == "top":
            b = tc.box([cw, ch, _wall_cut_thickness])
            b.apply_translation([cut.x_off, cut.z_off, height])
            body = _csg_diff(body, b)
            continue
        else:
            continue
        body = _csg_diff(body, slot)

    result = {"body": body}

    # --- Wieko ---
    if lid:
        lid_h    = wall + 1.5
        lip_h    = 2.0
        lip_wall = wall * 0.7
        lid_mesh = tc.box([width, depth, lid_h])
        lip = tc.box([width - 2*lip_wall, depth - 2*lip_wall, lip_h])
        lip.apply_translation([0, 0, -(lid_h + lip_h) / 2])
        lid_mesh = _csg_union(lid_mesh, lip)

        # Otwory w wieczku dla śrub
        if standoffs:
            ox = width  / 2 - standoff_od - wall + 0.5
            oy = depth  / 2 - standoff_od - wall + 0.5
            for sx, sy in [(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)]:
                h2 = tc.cylinder(standoff_id / 2, lid_h + lip_h + 1, sections=24)
                h2.apply_translation([sx, sy, 0])
                lid_mesh = _csg_diff(lid_mesh, h2)

        if separate_lid:
            result["lid"] = lid_mesh
        else:
            lid_mesh.apply_translation([width + 10, 0, lid_h / 2])
            result["lid"] = lid_mesh

    return result


def make_panel(
    width: float = 100.0,
    height: float = 60.0,
    thick: float = 3.0,
    holes: list[HoleSpec] | None = None,
    cutouts: list[CutoutSpec] | None = None,
) -> trimesh.Trimesh:
    """Płaski panel z otworami."""
    panel = tc.box([width, thick, height])
    holes = holes or []
    for hole in holes:
        cyl = tc.cylinder(hole.diameter / 2, thick + 2, sections=32)
        cyl.apply_translation([hole.x - width/2, 0, hole.y - height/2])
        # rotate to go through Y axis
        rot = tt.rotation_matrix(math.pi/2, [1, 0, 0])
        cyl.apply_transform(rot)
        cyl.apply_translation([hole.x - width/2, 0, hole.y - height/2])
        panel = _csg_diff(panel, cyl)
    return panel


def make_bracket(
    width: float = 40.0,
    height: float = 30.0,
    depth: float = 20.0,
    thick: float = 3.0,
    hole_dia: float = 3.2,
    n_holes_w: int = 2,
    n_holes_h: int = 2,
) -> trimesh.Trimesh:
    """Kątownik montażowy L (dwie płaszczyzny prostopadłe)."""
    plate_h = tc.box([width, depth, thick])
    plate_h.apply_translation([0, 0, -thick/2])
    plate_v = tc.box([thick, depth, height])
    plate_v.apply_translation([-width/2 + thick/2, 0, height/2])
    bracket = _csg_union(plate_h, plate_v)

    # Otwory w poziomej płycie
    margin_w = width / (n_holes_w + 1)
    margin_h = depth / 3
    for i in range(n_holes_w):
        cyl = tc.cylinder(hole_dia / 2, thick * 3, sections=32)
        cyl.apply_translation([-width/2 + margin_w * (i+1), 0, -thick/2])
        bracket = _csg_diff(bracket, cyl)

    # Otwory w pionowej płycie
    margin_v = height / (n_holes_h + 1)
    for i in range(n_holes_h):
        cyl = tc.cylinder(hole_dia / 2, thick * 3, sections=32)
        rot = tt.rotation_matrix(math.pi/2, [1, 0, 0])
        cyl.apply_transform(rot)
        cyl.apply_translation([-width/2 + thick/2, 0, margin_v * (i+1)])
        bracket = _csg_diff(bracket, cyl)

    return bracket


def make_standoff(
    height: float = 10.0,
    od: float = 6.0,
    hole_dia: float = 3.2,
    hexagonal: bool = False,
) -> trimesh.Trimesh:
    """Dystans / standoff z otworem osiowym."""
    if hexagonal:
        verts2d = [(od/2 * math.cos(math.pi/180*a),
                    od/2 * math.sin(math.pi/180*a)) for a in range(0, 360, 60)]
        poly = trimesh.creation.extrude_polygon(
            trimesh.path.Path2D(entities=[trimesh.path.entities.Line(list(range(6))+[0])],
                                vertices=verts2d),
            height
        )
        outer = poly
    else:
        outer = tc.cylinder(od / 2, height, sections=32)
    outer.apply_translation([0, 0, height/2])
    if hole_dia > 0:
        inner = tc.cylinder(hole_dia / 2, height + 1, sections=32)
        inner.apply_translation([0, 0, height/2])
        outer = _csg_diff(outer, inner)
    return outer


def make_din_clip(
    width: float = 35.0,
    rail_h: float = 7.5,
    thick: float = 2.5,
) -> trimesh.Trimesh:
    """Klips DIN 35mm do szyn TH35."""
    body = tc.box([width, 15, 20])
    slot_h = tc.box([width - 2*thick, rail_h + 1, thick + 1])
    slot_h.apply_translation([0, -6, -(20/2 - thick/2)])
    body = _csg_diff(body, slot_h)
    return body


def make_cable_clip(
    cable_dia: float = 5.0,
    thick: float = 2.0,
    width: float = 8.0,
) -> trimesh.Trimesh:
    """Klips na kabel z elastycznym uchwytem."""
    outer_r = cable_dia / 2 + thick
    body = tc.cylinder(outer_r, width, sections=48)
    body.apply_translation([0, 0, width/2])
    inner = tc.cylinder(cable_dia / 2, width + 1, sections=48)
    inner.apply_translation([0, 0, width/2])
    body = _csg_diff(body, inner)
    # nacięcie dla wpięcia kabla
    slot = tc.box([cable_dia * 0.6, outer_r * 2 + 1, width + 1])
    slot.apply_translation([0, outer_r / 2, width/2])
    body = _csg_diff(body, slot)
    # podstawa montażowa
    base = tc.box([outer_r * 2.5, outer_r * 1.5, width])
    base.apply_translation([0, -outer_r - thick/2, width/2])
    hole = tc.cylinder(1.5, width + 1, sections=24)
    hole.apply_translation([0, -outer_r - thick/2, width/2])
    base = _csg_diff(base, hole)
    body = _csg_union(body, base)
    return body


# ── Parser opisu tekstowego ───────────────────────────────────────────────────

# Wzorce wymiarów: "50x30x20", "50 x 30 x 20", "50×30×20"
_DIM3_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)")
_DIM2_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)")
_NUM_RE  = re.compile(r"(\d+(?:\.\d+)?)\s*mm")

def _find_dim3(text: str) -> tuple | None:
    m = _DIM3_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None

def _find_dim2(text: str) -> tuple | None:
    m = _DIM2_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None

def _find_num(text: str, default: float) -> float:
    m = _NUM_RE.search(text)
    return float(m.group(1)) if m else default

_PRESETS = {
    # klucz → kwargs dla make_enclosure
    "arduino": dict(width=72, depth=55, height=28, wall=2.0, lid=True,  standoffs=True),
    "uno":     dict(width=72, depth=55, height=28, wall=2.0, lid=True,  standoffs=True),
    "nano":    dict(width=30, depth=20, height=20, wall=1.8, lid=True,  standoffs=True),
    "esp32":   dict(width=40, depth=30, height=22, wall=2.0, lid=True,  standoffs=True),
    "rp2040":  dict(width=35, depth=25, height=18, wall=2.0, lid=True,  standoffs=True),
    "18650":   dict(width=80, depth=25, height=22, wall=2.5, lid=True,  standoffs=False),
    "raspberry":dict(width=90, depth=65, height=30, wall=2.0, lid=True, standoffs=True),
}

_CUTOUT_KEYWORDS = {
    "usb-c":    CutoutSpec("left", 0, 1,  9.0, 3.5, "USB-C"),
    "usb_c":    CutoutSpec("left", 0, 1,  9.0, 3.5, "USB-C"),
    "usbc":     CutoutSpec("left", 0, 1,  9.0, 3.5, "USB-C"),
    "micro usb":CutoutSpec("left", 0, 1,  8.0, 3.0, "Micro USB"),
    "mini usb": CutoutSpec("left", 0, 1,  7.5, 4.0, "Mini USB"),
    "usb a":    CutoutSpec("left", 0, 1, 12.0, 5.0, "USB-A"),
    "usb":      CutoutSpec("left", 0, 1,  9.0, 3.5, "USB"),
    "dc jack":  CutoutSpec("back", 0, 2,  7.5, 7.5, "DC Jack"),
    "dc zasilanie": CutoutSpec("back", 0, 2, 7.5, 7.5, "DC"),
    "hdmi":     CutoutSpec("left", 0, 1, 16.0, 7.0, "HDMI"),
    "rj45":     CutoutSpec("back", 0, 1, 16.0, 14.0,"RJ45"),
    "ethernet": CutoutSpec("back", 0, 1, 16.0, 14.0,"Ethernet"),
    "jack 3.5": CutoutSpec("front", 0, 5, 6.5, 6.5, "Jack 3.5mm"),
    "audio":    CutoutSpec("front", 0, 5, 6.5, 6.5, "Audio"),
    "sd card":  CutoutSpec("front", 0, 2, 15.0, 2.5, "SD Card"),
    "sd":       CutoutSpec("front", 0, 2, 15.0, 2.5, "SD"),
    "przycisk": CutoutSpec("top", 0, 0,  8.0, 8.0, "Button"),
    "button":   CutoutSpec("top", 0, 0,  8.0, 8.0, "Button"),
    "led":      CutoutSpec("front", 0, 5, 5.0, 5.0, "LED"),
    "oled":     CutoutSpec("top", 0, 0, 28.0, 12.0,"OLED"),
    "display":  CutoutSpec("top", 0, 0, 30.0, 20.0,"Display"),
}

_WALL_KEYWORDS = {
    "lewy": "left", "lewa": "left", "left": "left",
    "prawy": "right", "prawa": "right", "right": "right",
    "przód": "front", "front": "front", "przednia": "front",
    "tył": "back",  "back": "back",  "tylna": "back",
    "góra": "top",  "top": "top",   "górna": "top",
    "dół": "bottom","bottom": "bottom",
}


def parse_description(text: str) -> dict:
    """
    Parsuje opis tekstowy obudowy i zwraca słownik parametrów.

    Rozpoznaje:
    - wymiary: "60x40x25mm"
    - grubość ścianki: "ścianka 2mm" / "wall 2mm"
    - wieko: "z wiekiem" / "with lid" / "bez wieka"
    - standoffy M3: "standoffy M3" / "4 standoffy"
    - wycięcia złączy: "USB-C na lewej ścianie"
    - typ obiektu: "panel", "kątownik", "obudowa"
    - presety: "arduino", "esp32", "raspberry pi"
    - zaokrąglenia: "zaokrąglenie 3mm"
    """
    t = text.lower()
    result: dict = {
        "object_type": "enclosure",
        "width":   60.0, "depth": 40.0, "height": 25.0,
        "wall":    2.0,
        "lid":     True,
        "standoffs": True,
        "standoff_h": 3.0,
        "standoff_id": 1.5,
        "corner_r": 2.0,
        "cutouts": [],
        "holes":   [],
        "source_text": text,
    }

    # Typ obiektu
    if any(k in t for k in ["panel", "płyta", "plate"]):
        result["object_type"] = "panel"
    elif any(k in t for k in ["kątownik", "uchwyt", "bracket", "l-shape"]):
        result["object_type"] = "bracket"
    elif any(k in t for k in ["standoff", "dystans", "spacer"]):
        result["object_type"] = "standoff"
    elif any(k in t for k in ["din", "szyna", "rail"]):
        result["object_type"] = "din_clip"
    elif any(k in t for k in ["klips kabel", "cable clip", "klips na kabel"]):
        result["object_type"] = "cable_clip"

    # Preset nazwy boardów
    for preset_key, preset_vals in _PRESETS.items():
        if preset_key in t:
            result.update(preset_vals)
            break

    # Wymiary WxDxH
    d3 = _find_dim3(text)
    if d3:
        result["width"], result["depth"], result["height"] = d3

    # Grubość ścianki
    for kw in ["ścian", "wall", "thick", "grub"]:
        if kw in t:
            m = re.search(rf"{kw}\w*\s*(\d+(?:\.\d+)?)", t)
            if m:
                result["wall"] = float(m.group(1))
                break

    # Wieko / lid
    if any(k in t for k in ["bez wiek", "no lid", "bez pokr", "open top", "otwarty"]):
        result["lid"] = False
    elif any(k in t for k in ["z wiekiem", "with lid", "wieko", "pokrywa", "lid"]):
        result["lid"] = True

    # Standoffy
    if any(k in t for k in ["bez standoff", "bez dystans", "no standoff"]):
        result["standoffs"] = False

    # Rozmiar otworu standoffa (M2/M3/M4)
    m_match = re.search(r"m(\d)\s+standoff|standoff\s+m(\d)", t)
    if m_match:
        mnum = int(m_match.group(1) or m_match.group(2))
        result["standoff_id"] = {2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}.get(mnum, 1.5)

    # Zaokrąglenia
    m = re.search(r"zaokr\w*\s*(\d+(?:\.\d+)?)|round\w*\s*(\d+(?:\.\d+)?)|fillet\s*(\d+(?:\.\d+)?)", t)
    if m:
        result["corner_r"] = float(next(v for v in m.groups() if v))

    # Wycięcia złączy
    for kw, spec in _CUTOUT_KEYWORDS.items():
        if kw in t:
            import copy
            cut = copy.deepcopy(spec)
            # Szukaj ściany w pobliżu słowa kluczowego
            idx = t.find(kw)
            context = t[max(0, idx-30):idx+60]
            for wall_kw, wall_code in _WALL_KEYWORDS.items():
                if wall_kw in context:
                    cut.wall = wall_code
                    break
            result["cutouts"].append(cut)

    return result


def build_from_description(text: str) -> dict[str, trimesh.Trimesh]:
    """Główna funkcja: tekst → dict z meshami."""
    params = parse_description(text)
    otype = params["object_type"]

    if otype == "panel":
        d2 = _find_dim2(text)
        w, h = (d2[0], d2[1]) if d2 else (params["width"], params["depth"])
        return {"panel": make_panel(w, h, params["wall"])}

    if otype == "bracket":
        return {"bracket": make_bracket(
            params["width"], params["height"], params["depth"],
            params["wall"],
        )}

    if otype == "standoff":
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        h  = float(nums[0]) if len(nums) > 0 else 10.0
        od = float(nums[1]) if len(nums) > 1 else 6.0
        id_ = float(nums[2]) if len(nums) > 2 else 3.2
        return {"standoff": make_standoff(h, od, id_)}

    if otype == "din_clip":
        return {"din_clip": make_din_clip()}

    if otype == "cable_clip":
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        dia = float(nums[0]) if nums else 5.0
        return {"cable_clip": make_cable_clip(dia)}

    # Domyślnie: obudowa
    return make_enclosure(
        width=params["width"],
        depth=params["depth"],
        height=params["height"],
        wall=params["wall"],
        lid=params["lid"],
        standoffs=params["standoffs"],
        standoff_h=params["standoff_h"],
        standoff_id=params["standoff_id"],
        corner_r=params["corner_r"],
        cutouts=params["cutouts"],
        holes=params["holes"],
        separate_lid=True,
    )


def export_stl(mesh: trimesh.Trimesh, path: str) -> None:
    mesh.export(path)


def export_all_stl(meshes: dict[str, trimesh.Trimesh], base_path: str) -> list[str]:
    """Eksportuje każdy mesh jako osobny plik STL."""
    base = Path(base_path)
    paths = []
    for name, mesh in meshes.items():
        p = base.parent / f"{base.stem}_{name}.stl"
        mesh.export(str(p))
        paths.append(str(p))
    return paths
