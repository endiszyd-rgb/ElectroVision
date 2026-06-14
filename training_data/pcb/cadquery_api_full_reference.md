# CadQuery API — Complete Reference
Source: cadquery.readthedocs.io/en/latest/apireference.html

## Core Object Model

CadQuery provides four primary objects:
- **Workplane** — Main design interface, wraps topological entities with 2D context
- **Sketch** — Constraint-based 2D sketches
- **Selector** — Filters geometric entities (edges, faces, vertices)
- **Assembly** — Hierarchical assemblies with constraints

---

## Workplane Methods — Complete

### Construction / Navigation
```python
cq.Workplane("XY")           # Start on XY plane (z=0)
cq.Workplane("YZ")           # Start on YZ plane
cq.Workplane("XZ")           # Start on XZ plane
.workplane(offset=0)          # New workplane on current face
.workplane(centerOption="CenterOfMass")
.faces(">Z").workplane()      # Workplane on top face
```

### 2D Primitives
```python
.rect(width, height)                    # Rectangle (centered by default)
.rect(w, h, centered=False)             # Corner-anchored rectangle
.circle(radius)                         # Circle
.ellipse(x_radius, y_radius)           # Ellipse
.polygon(sides, diameter)              # Regular polygon
.slot2D(length, diameter, angle=0)     # Rounded slot
.polyline([(x1,y1),(x2,y2),...])       # Connected line segments
```

### 2D Lines and Arcs
```python
.lineTo(x, y)                   # Line to absolute point
.line(xDist, yDist)             # Line relative distance
.vLine(distance)                # Vertical line
.hLine(distance)                # Horizontal line
.polarLine(distance, angle)     # Line at angle (degrees)
.threePointArc(point1, point2)  # Arc through midpoint
.radiusArc(endPoint, radius)    # Arc defined by radius
.tangentArcPoint(endpoint)      # Tangent arc
.close()                        # Close current wire
```

### 2D Arrays
```python
.rarray(xSpacing, ySpacing, xCount, yCount)   # Rectangular array
.polarArray(radius, startAngle, angle, count)  # Polar array
```

### 3D Operations
```python
.extrude(distance)                  # Extrude up
.extrude(distance, combine=False)   # Extrude as separate solid
.cutBlind(distance)                 # Blind cut (remove material)
.cutThruAll()                       # Cut through all
.revolve(angleDegrees=360)          # Revolve around axis
.loft()                             # Loft between wires on stack
.sweep(path)                        # Sweep wire along path
.twistExtrude(distance, angleDeg)   # Helix-like extrusion
```

### 3D Primitives
```python
.box(length, width, height)              # Box primitive
.box(l, w, h, centered=(True,True,True)) # Box with centering control
.sphere(radius)                          # Sphere
.cylinder(height, radius)               # Cylinder
.cone(height, radius1, radius2)         # Truncated cone
.wedge(dx, dy, dz, xmin, zmin, xmax, zmax)  # Wedge
```

### Boolean Operations
```python
.union(other)          # Merge solids
.cut(other)            # Subtract solid
.intersect(other)      # Keep intersection only
.combine()             # Merge all items on stack
```

### Holes
```python
.hole(diameter)                            # Simple through hole
.hole(diameter, depth)                     # Blind hole
.cboreHole(diameter, cboreDiameter, cboreDepth)     # Counterbore
.cskHole(diameter, cskDiameter, cskAngle) # Countersink
```

### Modifications
```python
.fillet(radius)          # Fillet selected edges
.chamfer(length)         # Chamfer selected edges
.shell(thickness)        # Hollow out (remove selected faces)
.split(keepTop=True)     # Split solid
.mirror("XY")            # Mirror about XY plane
.mirror(mirrorPlane="ZY")
```

### Transforms
```python
.translate((x, y, z))               # Move
.rotate((0,0,0), (0,0,1), angle)    # Rotate around axis
.rotateAboutCenter((0,0,1), angle)  # Rotate about centroid
.mirror("XY")                       # Mirror
```

### Face/Edge/Vertex Selection
```python
.faces(">Z")         # Top face (most positive Z)
.faces("<Z")         # Bottom face (most negative Z)
.faces(">X")         # Right face
.faces("<X")         # Left face
.faces(">Y")         # Front face
.faces("<Y")         # Back face
.faces("|Z")         # Faces parallel to Z (i.e., side walls)
.faces("#Z")         # Faces perpendicular to Z (top/bottom)

.edges("|Z")         # Vertical edges
.edges(">Z")         # Top edges
.edges("<Z")         # Bottom edges
.edges(">>Z[-2]")    # Second-highest Z edges

.vertices(">Z")      # Top vertices
.vertices("<Z")      # Bottom vertices
```

### Stack Management
```python
.val()               # Get first value (Shape/Vector)
.vals()              # Get all values
.add(obj)            # Add object to stack
.end(n=1)            # Go n levels up parent chain
.size()              # Count items on stack
.all()               # All CQ objects on stack
.first()             # First item
.last()              # Last item
```

---

## Selector Syntax (String)

Selectors filter geometric entities:

| Syntax | Meaning |
|--------|---------|
| `">X"` | Maximum X (rightmost) |
| `"<X"` | Minimum X (leftmost) |
| `">Y"` | Maximum Y (front) |
| `"<Y"` | Minimum Y (back) |
| `">Z"` | Maximum Z (top) |
| `"<Z"` | Minimum Z (bottom) |
| `"\|Z"` | Parallel to Z axis |
| `"#Z"` | Perpendicular to Z axis |
| `">>Z[-2]"` | Second-last in Z direction |
| `"not >Z"` | NOT top face |
| `">Z and >X"` | AND combination |
| `">Z or <Z"` | OR combination |

---

## Exporters

```python
from cadquery import exporters

# Export to STL (for 3D printing slicer)
exporters.export(shape, "part.stl")

# Export to STEP (for Fusion 360, FreeCAD)
exporters.export(shape, "part.step")

# Export to AMF
exporters.export(shape, "part.amf")

# Export to SVG (for 2D projection)
exporters.export(shape, "part.svg")

# Export to DXF
exporters.export(shape, "part.dxf")

# Assembly save
assembly.save("assembly.step")
assembly.save("assembly.stl", exportType="STL")
```

---

## Assembly

```python
import cadquery as cq

# Create parts
body = cq.Workplane("XY").box(100, 80, 30)
lid  = cq.Workplane("XY").box(100, 80, 5)

# Build assembly
asm = cq.Assembly()
asm.add(body, name="body", color=cq.Color("gray"))
asm.add(lid, name="lid",
        loc=cq.Location(cq.Vector(0, 0, 32)),   # offset 32mm up
        color=cq.Color("darkgray"))

asm.save("assembly.step")
```

---

## Complete PCB Enclosure Example

```python
import cadquery as cq
from cadquery import exporters

# ── Parameters ──────────────────────────────────
PCB_W   = 100.0   # PCB width  (mm)
PCB_L   = 80.0    # PCB length (mm)
PCB_T   = 1.6     # PCB thickness
MARGIN  = 3.0     # PCB to wall margin
WALL    = 2.0     # Wall thickness
HEIGHT  = 30.0    # Inside enclosure height
R       = 2.5     # Corner radius
STANDOFF_H = 4.0  # Standoff height
STANDOFF_R = 2.5  # Standoff outer radius
SCREW_R    = 1.35 # M2.7 self-tapping

# ── Outer box ───────────────────────────────────
ext_w = PCB_W + 2*MARGIN + 2*WALL
ext_l = PCB_L + 2*MARGIN + 2*WALL
ext_h = HEIGHT + WALL

body = (cq.Workplane("XY")
    .box(ext_l, ext_w, ext_h)
    .edges("|Z").fillet(R)
    .shell(-WALL)
)

# ── Standoffs (4 corners) ───────────────────────
for sx, sy in [
    ( PCB_L/2 - 3,  PCB_W/2 - 3),
    (-PCB_L/2 + 3,  PCB_W/2 - 3),
    ( PCB_L/2 - 3, -PCB_W/2 + 3),
    (-PCB_L/2 + 3, -PCB_W/2 + 3),
]:
    so = (cq.Workplane("XY")
        .center(sx, sy)
        .cylinder(STANDOFF_H, STANDOFF_R)
        .faces(">Z").hole(SCREW_R * 2, STANDOFF_H)
        .translate((0, 0, WALL))
    )
    body = body.union(so)

# ── USB-C cutout (front wall) ───────────────────
body = (body
    .faces(">Y").workplane()
    .center(0, -HEIGHT/2 + 5)
    .rect(10.0, 4.0)
    .cutBlind(-3.5)
)

# ── Lid ────────────────────────────────────────
lid = (cq.Workplane("XY")
    .box(ext_l, ext_w, WALL + 2.0)
    .edges("|Z").fillet(R)
    .shell(-WALL)
    .translate((0, 0, HEIGHT + WALL))
)

# ── Export ─────────────────────────────────────
exporters.export(body, "enclosure_body.stl")
exporters.export(body, "enclosure_body.step")
exporters.export(lid, "enclosure_lid.stl")
exporters.export(lid, "enclosure_lid.step")
print("Done: enclosure_body.stl + enclosure_lid.stl")
```

---

## Importers

```python
from cadquery import importers

# Import STEP file
result = importers.importStep("existing_part.step")

# Import DXF (as wire in XY plane)
result = importers.importDXF("profile.dxf", tol=1e-3)
```

---

## Color Reference

```python
cq.Color("red")
cq.Color("green")
cq.Color("blue")
cq.Color("gray")
cq.Color("darkgray")
cq.Color(r, g, b)         # RGB 0.0-1.0
cq.Color(r, g, b, alpha)  # RGBA with transparency
```
