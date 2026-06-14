# CadQuery API Reference — Kompletny przewodnik dla obudów elektroniki
# Źródło: https://cadquery.readthedocs.io

## Instalacja
```bash
pip install cadquery
# lub przez conda (zalecane):
conda install -c conda-forge cadquery
```

## Warstwy API
1. **Fluent API** — Workplane, Sketch, Assembly (główny interfejs)
2. **Direct API** — Shape, Compound, Solid, Shell, Face, Wire, Edge, Vertex
3. **Geometry API** — Vector, Plane, Location
4. **OCCT API** — niskopoziomowe bindingi przez OCP

## Workplane — tworzenie brył

### box() — prostopadłościan
```python
Workplane.box(length, width, height, centered=True)
# length=80, width=60, height=30 → pudełko 80×60×30mm
result = cq.Workplane("XY").box(80, 60, 30)
```

### cylinder() — walec
```python
Workplane.cylinder(height, radius, direct=None)
result = cq.Workplane("XY").cylinder(10, 5)  # wys=10, promień=5
```

### sphere() — kula
```python
Workplane.sphere(radius, direct=None, angle1=None, angle2=None)
result = cq.Workplane("XY").sphere(5)
```

## Operacje odejmowania

### hole() — otwór (prosty)
```python
Workplane.hole(diameter, depth=None, clean=True)
# Tworzy otwór pod bieżącym workplane
result = result.faces(">Z").hole(3.4)   # otwór M3
```

### cboreHole() — otwór z pogłębieniem
```python
Workplane.cboreHole(diameter, cboreDiameter, cboreDepth, depth=None)
result = result.cboreHole(3.4, 6.5, 3.0)  # M3 z łbem
```

### cskHole() — otwór stożkowy
```python
Workplane.cskHole(diameter, cskDiameter, cskAngle, depth=None)
result = result.cskHole(3.4, 6.0, 82)   # M3 countersunk
```

### cutBlind() — wycięcie na głębokość
```python
Workplane.cutBlind(until, clean=True, both=False, taper=None)
# Wycięcie prostokąta na zadaną głębokość
result = result.faces("<Y").workplane().rect(10, 4).cutBlind(-2.5)
```

### cutThruAll() — wycięcie przez całą bryłę
```python
Workplane.cutThruAll(clean=True, taper=None)
result = result.faces(">Z").workplane().circle(5).cutThruAll()
```

### cut() — boolean cut
```python
Workplane.cut(toCut, clean=True, tol=None)
body = body.cut(notch)
```

## Modyfikacje krawędzi

### fillet() — zaokrąglenie
```python
Workplane.fillet(radius)
result = result.edges("|Z").fillet(2.0)   # narożniki pionowe
result = result.edges(">Z").fillet(1.0)   # krawędź górna
```

### chamfer() — sfazowanie
```python
Workplane.chamfer(length, length2=None)
result = result.edges(">Z").chamfer(0.5)
```

### shell() — wydrążenie (tworzenie skorupy)
```python
Workplane.shell(thickness, kind=None)
# Tworzy pudełko ze ściankami
result = cq.Workplane("XY").box(80, 60, 30).shell(-2.0)
# Uwaga: ujemna grubość = ścianki do wewnątrz
```

## Selekcja elementów

### faces() — wybór ścian
```python
Workplane.faces(selector=None, tag=None)
# Selektory kierunkowe:
">Z"  # najwyższa ściana (góra)
"<Z"  # najniższa ściana (dół)
">Y"  # ściana od strony Y+
"<Y"  # ściana od strony Y-
">X"  # ściana prawa
"<X"  # ściana lewa
```

### edges() — wybór krawędzi
```python
Workplane.edges(selector=None, tag=None)
"|Z"  # krawędzie równoległe do osi Z (pionowe)
"|X"  # krawędzie równoległe do osi X
">Z"  # najwyższe krawędzie
```

### vertices() — wybór wierzchołków
```python
Workplane.vertices(selector=None, tag=None)
```

## Transformacje

### translate() — przesunięcie
```python
Workplane.translate(vec)
result = result.translate((10, 0, 5))  # x=+10, z=+5
```

### rotate() — obrót
```python
Workplane.rotate(axisStartPoint, axisEndPoint, angleDegrees)
result = result.rotate((0,0,0), (0,0,1), 45)  # 45° wokół Z
```

### mirror() — lustro
```python
Workplane.mirror(mirrorPlane=None, basePointVector=None)
```

## Operacje logiczne (Boolean)

### union() — złączenie
```python
Workplane.union(toUnion=None, clean=True, glue=False, tol=None)
result = body.union(lid)
```

### intersect() — przecięcie
```python
Workplane.intersect(toIntersect, clean=True, tol=None)
```

## Eksport

### export() — zapis do pliku
```python
import cadquery as cq
from cadquery import exporters

# STL (do slicera)
exporters.export(result, "enclosure.stl")

# STEP (do Fusion 360)
exporters.export(result, "enclosure.step")

# SVG (rzut)
exporters.export(result, "top_view.svg")

# Alternatywnie przez val():
result.val().exportStep("enclosure.step")
```

## Kompletny przykład — obudowa PCB

```python
import cadquery as cq
from cadquery import exporters

# ── Parametry ──────────────────────────────────
pcb_w   = 80.0   # szerokość PCB
pcb_l   = 60.0   # długość PCB
pcb_h   = 1.6    # grubość PCB
margin  = 3.0    # margines od PCB do ścianki
wall    = 2.0    # grubość ścianki
height  = 30.0   # wewnętrzna wysokość
r       = 2.0    # zaokrąglenie narożników
so_h    = 4.0    # wysokość standoffów
so_ro   = 2.5    # zewnętrzny promień standoffu
so_ri   = 1.1    # promień otworu M2

# ── Wymiary zewnętrzne ──────────────────────────
ext_w = pcb_w + 2 * margin + 2 * wall
ext_l = pcb_l + 2 * margin + 2 * wall
ext_h = height + wall  # dno + wysokość

# ── Obudowa (bryła zewnętrzna - wewnętrzna) ─────
outer = (cq.Workplane("XY")
    .box(ext_l, ext_w, ext_h)
    .edges("|Z").fillet(r)
)
inner = (cq.Workplane("XY")
    .box(ext_l - 2*wall, ext_w - 2*wall, ext_h - wall)
    .translate((0, 0, wall / 2))
)
body = outer.cut(inner)

# ── Standoffy (narożniki PCB) ─────────────────────
standoff_positions = [
    ( (pcb_l/2 - 3),  (pcb_w/2 - 3)),
    (-(pcb_l/2 - 3),  (pcb_w/2 - 3)),
    ( (pcb_l/2 - 3), -(pcb_w/2 - 3)),
    (-(pcb_l/2 - 3), -(pcb_w/2 - 3)),
]
for (sx, sy) in standoff_positions:
    so = (cq.Workplane("XY")
        .center(sx, sy)
        .cylinder(so_h, so_ro)
        .faces(">Z")
        .hole(so_ri * 2, so_h)
        .translate((0, 0, wall))
    )
    body = body.union(so)

# ── Wycięcie USB-C (bok Y-) ────────────────────
body = (body
    .faces("<Y").workplane()
    .center(0, -height/2 + 8)
    .rect(10.0, 4.0)
    .cutBlind(-(wall + 0.1))
)

# ── Eksport ────────────────────────────────────
exporters.export(body, "enclosure_body.stl")
exporters.export(body, "enclosure_body.step")
print("Wygenerowano: enclosure_body.stl + .step")
```

## Assembly — złożenie wieloczęściowe

```python
import cadquery as cq

body = cq.Workplane("XY").box(80, 60, 25)
lid  = cq.Workplane("XY").box(80, 60, 5).translate((0, 0, 27.5))

asm = (cq.Assembly()
    .add(body, name="body", color=cq.Color("gray"))
    .add(lid,  name="lid",  color=cq.Color("lightgray"))
)
asm.save("full_enclosure.step")
```

Źródła:
- https://cadquery.readthedocs.io/en/latest/classreference.html
- https://cadquery.readthedocs.io/en/latest/apireference.html
