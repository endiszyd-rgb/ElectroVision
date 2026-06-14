# STL i STEP — Formaty plików 3D dla elektroniki

## STL (STereoLithography / Standard Triangle Language)

### Format ASCII STL
```
solid nazwa_bryly
  facet normal 0.0 0.0 1.0          ← wektor normalny trójkąta
    outer loop
      vertex 0.0 0.0 0.0            ← wierzchołek 1 (x y z w mm)
      vertex 100.0 0.0 0.0          ← wierzchołek 2
      vertex 100.0 80.0 0.0         ← wierzchołek 3
    endloop
  endfacet
  facet normal ...
    ...
  endfacet
endsolid nazwa_bryly
```

### Format Binary STL (80 bajtów header + dane)
```
UINT8[80]    – nagłówek (dowolny tekst, NOT "solid")
UINT32       – liczba trójkątów N
N × (        – dla każdego trójkąta:
  FLOAT32[3] – wektor normalny (nx, ny, nz)
  FLOAT32[3] – wierzchołek 1  (x1, y1, z1)
  FLOAT32[3] – wierzchołek 2  (x2, y2, z2)
  FLOAT32[3] – wierzchołek 3  (x3, y3, z3)
  UINT16     – attribute byte count (zwykle 0)
)
```

Rozmiar binary: 84 + N × 50 bajtów
Przykład: 10 000 trójkątów = ~500KB binary vs ~2MB ASCII

### Wymagania dla dobrego STL do druku 3D
- Manifold mesh (zamknięta bryła): każda krawędź należy do dokładnie 2 trójkątów
- Spójne normalne: wszystkie normalne skierowane NA ZEWNĄTRZ bryły
- Brak self-intersections (bryła nie może się sama przecinać)
- Minimalna grubość ściany: ≥ 0.8mm (FDM), ≥ 0.2mm (SLA)
- Wszystkie wartości dodatnie Z (oś Z = oś druku)
- Jednostki: mm (slicer ustawiony na mm)

### Walidacja STL w Python (trimesh)
```python
import trimesh

mesh = trimesh.load('enclosure.stl')

# Sprawdzenie manifold
print("Manifold:", mesh.is_watertight)

# Naprawa podstawowych błędów
trimesh.repair.fix_normals(mesh)
trimesh.repair.fill_holes(mesh)

# Statystyki
print(f"Trójkąty: {len(mesh.faces)}")
print(f"Wierzchołki: {len(mesh.vertices)}")
print(f"Wymiary: {mesh.bounding_box.extents} mm")
print(f"Objętość: {mesh.volume:.1f} mm³")
print(f"Masa PETG: {mesh.volume * 1.27e-3:.1f} g")  # gęstość PETG=1.27g/cm³

# Eksport naprawionego
mesh.export('enclosure_fixed.stl')
```

---

## STEP (Standard for the Exchange of Product Data — ISO 10303)

### Dlaczego STEP jest lepszy niż STL dla inżynierów
| Cecha | STL | STEP |
|-------|-----|------|
| Geometria | Siatka trójkątów (przybliżona) | B-Rep (dokładna) |
| Edytowalność | Nie (tylko obrót/skala) | Tak (Fusion 360, FreeCAD) |
| Parametry | Nie | Tak (w niektórych) |
| Przeznaczenie | Druk 3D slicer | CAD, CNC, produkcja |
| Wielkość pliku | Mała | Duża |

### Format STEP AP214 (najczęściej używany)
```
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE STEP translator 7.7'),'2;1');
FILE_NAME('part.step','2024-01-15T12:00:00',(''),(''),'','','');
FILE_SCHEMA(('AP214IS_FINAL_MIM_CC;1.0.0'));
ENDSEC;
DATA;
#1=PRODUCT('PCB Enclosure','PCB Enclosure','',());
#2=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE(...)
...  ← setki linii geometrii B-Rep
ENDSEC;
END-ISO-10303-21;
```

### Eksport STEP z CadQuery
```python
import cadquery as cq
from cadquery import exporters

# Eksport pojedynczej bryły
body = cq.Workplane("XY").box(100, 80, 30)
exporters.export(body, "part.step")   # AP214 domyślnie

# Eksport Assembly (wszystkie części oddzielnie)
asm = cq.Assembly()
asm.add(body, name="enclosure_body")
asm.add(lid,  name="enclosure_lid")
asm.save("assembly.step")             # Zawiera wszystkie nazwy parts

# AP242 (nowszy standard)
exporters.export(body, "part_ap242.step",
                 exportType=cq.exporters.ExportTypes.STEP)
```

### Import STEP w popularnych programach
| Program | Import STEP | Edytowalność |
|---------|-------------|-------------|
| Fusion 360 | File → Open → .step | Tak, jako B-Rep |
| FreeCAD | File → Import → .step | Tak, Part module |
| SolidWorks | File → Open → .step | Tak, w Native |
| PrusaSlicer | File → Import → STL (nie STEP!) | Nie |
| Cura | Nie obsługuje STEP | Nie |

---

## PCB → 3D Model (konwersja)

### Jak KiCad generuje 3D PCB
KiCad 7/8 posiada wbudowany eksport 3D STEP:
- File → Export → STEP
- Eksportuje: płytkę FR4, pady, ścieżki Cu, komponenty 3D
- Wymaga modeli 3D komponentów (`.wrl` lub `.step`) z biblioteki KiCad
- Modele KiCad: `$KISYS3DMOD` = folder z tysiącami gotowych modeli

### Ścieżki do modeli 3D KiCad
Standardowe lokalizacje:
- Windows: `C:\Program Files\KiCad\8.0\share\kicad\3dmodels\`
- Linux: `/usr/share/kicad/3dmodels/`
- Online: https://kicad.github.io/packages3d/ (GitHub repo)

Formaty modeli KiCad:
- `.wrl` — VRML 97 (używany w KiCad do podglądu)
- `.step` — STEP AP214 (do eksportu MCAD)

### Generowanie uproszczonego 3D modelu PCB (bez KiCad)
```python
import cadquery as cq
from cadquery import exporters

# Parametry z KiCad PCB
PCB_W = 100.0  # mm
PCB_H = 80.0   # mm
PCB_T = 1.6    # grubość

# 1. Płytka FR4 (zielona)
pcb = (cq.Workplane("XY")
    .box(PCB_W, PCB_H, PCB_T)
    .translate((PCB_W/2, PCB_H/2, 0))
)

# 2. Komponent: ESP32-WROOM (38.5 × 52 × 3.1 mm)
esp32 = (cq.Workplane("XY")
    .box(38.5, 52.0, 3.1)
    .translate((35, 25, PCB_T + 3.1/2))  # pozycja na płytce
)

# 3. Kondensator elektrolityczny (cylindryczny, Ø10mm, h=16mm)
cap = (cq.Workplane("XY")
    .cylinder(16.0, 5.0)                 # r = 10/2 = 5mm
    .translate((20, 60, PCB_T + 8.0))
)

# 4. USB connector (14.5 × 10.5 × 7 mm)
usb = (cq.Workplane("XY")
    .box(14.5, 10.5, 7.0)
    .translate((50, 2, PCB_T + 3.5))
)

# Złóż wszystko
asm = cq.Assembly()
asm.add(pcb,   name="pcb_fr4",  color=cq.Color(0.0, 0.4, 0.0))   # zielona płytka
asm.add(esp32, name="esp32",    color=cq.Color(0.5, 0.5, 0.5))   # szary moduł
asm.add(cap,   name="cap_e",    color=cq.Color(0.0, 0.0, 0.5))   # niebieski cap
asm.add(usb,   name="usb_conn", color=cq.Color(0.7, 0.7, 0.7))   # srebrny USB

asm.save("pcb_3d_model.step")
exporters.export(asm.toCompound(), "pcb_3d_model.stl")
print("PCB 3D model saved!")
```

---

## Wymiary komponentów PCB (3D modele uproszczone)

### Popularne obudowy SMD (do renderowania 3D)
| Obudowa | Wymiary (Dx, Dy, Dz) | Opis |
|---------|----------------------|------|
| 0402 | 1.0 × 0.5 × 0.5 mm | Rezystor/kondensator |
| 0603 | 1.6 × 0.8 × 0.8 mm | Rezystor/kondensator |
| 0805 | 2.0 × 1.25 × 1.0 mm | Rezystor/kondensator |
| 1206 | 3.2 × 1.6 × 1.2 mm | Kondensator większy |
| SOT-23 | 3.0 × 1.75 × 1.5 mm | Tranzystor, LDO (3 nogi) |
| SOT-223 | 6.5 × 3.5 × 1.8 mm | LDO większy (AMS1117) |
| SO-8 | 5.0 × 4.0 × 1.75 mm | Op-amp, MOSFET driver |
| SOIC-16 | 10.0 × 7.5 × 2.35 mm | IC 16-pin |
| TQFP-48 | 9.0 × 9.0 × 1.4 mm | MCU (STM32, ATmega) |
| QFN-32 | 5.0 × 5.0 × 0.85 mm | MCU bezołowiowy |
| ESP32-WROOM-32 | 25.5 × 18.0 × 3.1 mm | Moduł WiFi/BLE |
| BME280 (LGA-8) | 2.5 × 2.5 × 0.93 mm | Sensor środowiskowy |
| SSD1306 moduł | 27.0 × 27.0 × 4.0 mm | OLED 0.96" |

### Popularne złącza THT
| Złącze | Wymiary | Uwagi |
|--------|---------|-------|
| USB Micro-B THT | 8.0 × 5.5 × 3.5 mm | Konektor USB |
| USB-C THT | 9.0 × 7.5 × 3.5 mm | Konektor USB-C |
| DC Jack 2.1mm | 9.5 × 9.5 × 13.0 mm | Zasilanie |
| Pin Header 1×02 2.54mm | 5.0 × 2.54 × 8.0 mm | Goldpin |
| Pin Header 1×08 2.54mm | 21.0 × 2.54 × 8.0 mm | Goldpin |
| Screw Terminal 2pin | 9.5 × 7.0 × 8.0 mm | Śrubowy |
| JST PH 2pin | 4.0 × 3.5 × 6.5 mm | Konektor akumulatora |
| RJ45 THT | 16.0 × 21.0 × 13.5 mm | Ethernet |

---

## Wizualizacja PCB w Three.js

### Warstwy PCB i ich kolory
```javascript
const PCB_COLORS = {
    'F.Cu':    0xc8780a,   // Copper front (złota)
    'B.Cu':    0xc8780a,   // Copper back
    'F.Mask':  0x009900,   // Soldermask (zielona)
    'B.Mask':  0x009900,
    'F.SilkS': 0xf0f0f0,   // Silkscreen (biała)
    'B.SilkS': 0xf0f0f0,
    'F.Fab':   0x808080,   // Fab layer
    'Edge.Cuts': 0xffff00, // Kontur płytki (żółty)
    'FR4':     0x1a6b1a,   // Płytka bazowa (ciemnozielona)
};
```

### Three.js Box (komponent na płytce)
```javascript
function addComponent(scene, x, y, z, w, h, d, color) {
    const geo = new THREE.BoxGeometry(w, h, d);
    const mat = new THREE.MeshPhongMaterial({color: color});
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z + d/2);
    scene.add(mesh);
    return mesh;
}

// PCB board
addComponent(scene, pcbW/2, pcbH/2, 0, pcbW, pcbH, 1.6, 0x1a6b1a);

// Component example: ESP32
addComponent(scene, 35, 25, 1.6, 38.5, 52.0, 3.1, 0x555555);
```
