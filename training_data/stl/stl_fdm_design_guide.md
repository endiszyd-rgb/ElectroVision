# Przewodnik projektowania STL/STEP dla elektroniki

## Materiały do druku 3D

### PLA (Polylactic Acid)
- Temperatura dyszy: 180-230°C
- Temperatura stołu: 20-60°C (bez ogrzewania możliwe)
- Tg (temperatura zeszklenia): 55-60°C
- Zastosowanie: prototypy, obudowy do pomieszczeń wewnętrznych
- Wady: kruchy, wrażliwy na wilgoć, słaba odporność UV i chemiczna
- Zalety: tani, łatwy w druku, biodegradowalny
- Orientacja: najlepiej leżąco (bez podpór)

### PETG (Polyethylene Terephthalate Glycol)
- Temperatura dyszy: 230-250°C
- Temperatura stołu: 70-90°C
- Tg: 70-80°C
- Zastosowanie: **ZALECANY** dla obudów elektroniki
- Zalety: twardy + elastyczny, odporny chemicznie, mało higroskopijny
- Wady: struny (stringing), trudniejszy w druku niż PLA
- Retraction: 1-3mm (Bowden), 0.5-1mm (Direct Drive)

### ABS (Acrylonitrile Butadiene Styrene)
- Temperatura dyszy: 230-250°C
- Temperatura stołu: 100-110°C (wymagane!)
- Tg: 100-115°C
- Zastosowanie: obudowy przemysłowe, elementy mechaniczne
- Wady: wymaga obudowanej drukarki, opary szkodliwe, warping
- Zalety: można szlifować, szpachlować acetone smoothing

### ASA (Acrylonitrile Styrene Acrylate)
- Jak ABS + wysoka odporność UV
- Zastosowanie: obudowy zewnętrzne (outdoor), urządzenia przemysłowe
- Temperatura stołu: 90-110°C

### TPU (Thermoplastic Polyurethane)
- Temperatura dyszy: 210-230°C
- Elastyczny (Shore A 87-98)
- Zastosowanie: uszczelki, osłony, kable, antywibracyjne mocowania
- Druk: tylko Direct Drive, powoli (<30mm/s)

### Resin (SLA/DLP)
- Precyzja: 0.025-0.05mm (warstwy) vs 0.1-0.2mm FDM
- Zastosowanie: wydruki o wysokiej dokładności, małe części
- Wady: kruchy, wymaga post-processingu (UV curing), drogi
- Alternatywa: Anycubic Photon, Elegoo Mars

## Tolerancje i pasowania

### FDM (filament)
- Wymiar nominalny → rzeczywisty: -0.1 do +0.3mm
- Otwory: wydrukuj ×0.9 wymiaru nominalnego lub reamer
- Sworzeń/wał wchodzący suwliwie: wymiar - 0.4mm
- Wcisk (press fit): wymiar - 0.1 do -0.2mm
- Otwory na śruby:
  - M2 luz: 2.4mm, gwint samogwintujący: 1.8mm
  - M2.5 luz: 2.9mm, gwint: 2.2mm
  - M3 luz: 3.4mm, gwint samogwintujący: 2.7mm
  - M4 luz: 4.5mm, gwint: 3.6mm

### SLA (resin)
- Znacznie dokładniejsze: ±0.05mm
- Otwory: wymiar - 0.1mm wystarczy

## Parametry obudów PCB

### Grubość ścianek
- FDM minimum: 1.2mm (= 3× linia 0.4mm)
- FDM zalecane: 2.0-2.5mm
- SLA minimum: 0.6mm
- Narożniki wewnętrzne: R ≥ 0.5mm (unikaj ostrych kątów)
- Zewnętrzne: R = 1.0-3.0mm (estetyka)

### Standoffs (filarki mocowania PCB)
- Zewnętrzna średnica: 5.0mm
- Wewnętrzne otwory:
  - M2: ⌀2.2mm (luz), ⌀1.8mm (gwint samogwintujący)
  - M2.5: ⌀2.7mm / ⌀2.2mm
  - M3: ⌀3.4mm / ⌀2.7mm
- Wysokość: PCB thickness + 1-3mm (margines pod PCB)
- Typowo: 3-5mm wysokości
- Pozycja: odpowiada otworom montażowym na PCB

### Wieko (lid)
Typy zamknięcia:
1. **Snap-fit** (zatrzask):
   - Lip: 1.5mm × 1.5mm na obudowie, rowek na wieczku
   - Wcisk: 0.3-0.5mm
   - Kąt skośny: 30-45° dla łatwego zamykania
2. **Śruby M3**: 4 narożniki, nakrętki wcisnięte (heat insert)
3. **Magnesy**: ⌀6mm × 2mm neodymowe, wcisk -0.1mm
4. **Klej** (permanent): brak zamknięcia mechanicznego

### Otwory na złącza (typowe wymiary)
| Złącze | Otwór w obudowie |
|---|---|
| USB-A | 12.5 × 5.5mm |
| USB-B | 9.0 × 8.0mm |
| USB Micro-B | 8.5 × 3.5mm |
| USB-C | 10.0 × 4.0mm |
| DC Jack 2.1mm | ⌀7.0mm lub 10×6mm prostokąt |
| DC Jack 2.5mm | ⌀8.0mm |
| RJ45 (Ethernet) | 16.5 × 14.0mm |
| DB9 (RS232) | 32.0 × 12.5mm |
| Przycisk ⌀12mm | ⌀12.5mm |
| Przycisk tact 6×6 | 7.0 × 7.0mm |
| LED ⌀5mm | ⌀5.2mm |
| LED SMD | 3.0 × 1.5mm |
| Antena RP-SMA | ⌀8.5mm |

## Reguły druku 3D (DFM)

### Nawisy (Overhangs)
- FDM: bez podpór do 45° (niektóre drukarki do 60°)
- Reguła: jeśli kąt >45° od pionu → potrzebne podpory
- Podpory: auto w slicer (Cura/PrusaSlicer), usuwać ręcznie
- Optymalizacja: projektuj z myślą o druku BEZ podpór

### Mosty (Bridges)
- FDM: mosty do 50-60mm bez podpór (zależy od materiału, prędkości)
- PETG: lepsze niż PLA dla mostów
- Tip: chłodzenie 100% dla mostów

### Minimalny rozmiar elementów
- FDM: minimalna grubość elementu = 2× szerokość dyszy (2× 0.4mm = 0.8mm)
- Najcieńsze ścianki: 0.4mm (1 linia) - niestabilne
- Zalecane minimum: 1.2mm (3 linie)
- Filigranowe elementy (haki, zaczepy): ≥2mm

### Orientacja na stole drukarki
- Maksymalna wytrzymałość: warstwy prostopadle do sił (XY > Z)
- Otwory okrągłe: drukuj pionowo dla lepszej okrągłości
- Obudowy: drukuj otworem do góry (brak podpór wewnątrz)

## CadQuery — podstawy dla obudów elektroniki

### Instalacja
```bash
pip install cadquery
conda install -c conda-forge cadquery  # (łatwiejsze)
```

### Prosta obudowa
```python
import cadquery as cq

# Parametry
length = 80.0
width  = 60.0
height = 30.0
wall   = 2.0
r      = 2.0  # zaokrąglenie narożników

# Bryła zewnętrzna
outer = cq.Workplane("XY").box(length, width, height).edges("|Z").fillet(r)

# Odejmij wnętrze
inner_offset = wall
inner = cq.Workplane("XY").box(
    length - 2*wall, width - 2*wall, height - wall
).translate((0, 0, wall/2))

result = outer.cut(inner)

# Eksport
cq.exporters.export(result, "enclosure.stl")
result.val().exportStep("enclosure.step")
```

### Dodanie standoffów
```python
standoff_r = 2.5     # zewnętrzna
hole_r     = 1.1     # M2 gwint
sh         = 4.0     # wysokość

def add_standoff(wp, x, y):
    return (wp
        .center(x, y)
        .cylinder(sh, standoff_r)
        .faces(">Z")
        .hole(hole_r * 2, sh)
    )
```

### Wycięcie na złącze USB-C
```python
usb_w = 10.0; usb_h = 4.0
result = (result
    .faces(">Y")           # ściana boczna
    .workplane()
    .rect(usb_w, usb_h)
    .cutBlind(-wall - 0.1)
)
```

## STEP — format dla Fusion 360

### Format ISO-10303-21 (STEP AP214)
- Pełna nazwa: Standard for the Exchange of Product Model Data
- AP214: Aerospace manufacturing (de facto standard CAD)
- AP242: Nowszy, MBD support
- Fusion 360 importuje oba formaty przez: File → Open → *.step

### Konwencja nazw dla STEP z CadQuery
```python
# Ustaw metadane dla Fusion 360
result = result.tag("Enclosure_Body")
# Eksport z metadanymi
result.val().exportStep(
    "enclosure.step",
    write_pcurves=True,
    precision_mode=0,
)
```

### Workflow Fusion 360 z ElectroVision
1. ElectroVision generuje `enclosure.step` przez CadQuery
2. Fusion 360: File → Open → *.step
3. Fusion automatycznie konwertuje na parametryczną bryłę B-rep
4. Możesz modyfikować: wymiary, dodawać wycięcia, zaokrąglenia
5. Eksport z Fusion: STL dla druku, STEP dla klienta

## Wzorce obudów

### Typ 1: Prosta skrzynka (Box)
- 2 części: dół + wieczko
- Łączenie: snap-fit lub śruby
- Zastosowanie: większość urządzeń IoT

### Typ 2: Obudowa DIN Rail
- Montaż na szynie DIN 35mm (EN 60715)
- Szerokość modułu: 17.5mm (1M), 35mm (2M), 70mm (4M)
- Zatrzask DIN standardowy: wydrukuj lub kup metalowy

### Typ 3: Montaż ścienny (Wall Mount)
- Otwory montażowe ⌀5mm, rozstaw 60mm lub 80mm
- Kierunek montażu: złącza dostępne od przodu

### Typ 4: Panel Front (rack 19")
- 1U = 44.45mm, 2U = 88.9mm
- Szerokość: 482.6mm (19")
- Material: aluminium lub PETG (dla 3D print)

### Typ 5: IP54/IP65 (pyłoszczelny/wodoodporny)
- IP54: ochrona przed pyłem + bryzgami
- IP65: pyłoszczelny + strumień wody
- Uszczelka: rowek 1.5×1.5mm, O-ring ⌀3.0mm NBR (EPDM)
- Kable: dławiki PG7 (⌀2-6.5mm kabla) lub M12 (8-12mm)

## Slicer — parametry Cura/PrusaSlicer

### Profil dla PETG obudowy elektroniki
- Grubość warstwy: 0.2mm (jakość), 0.15mm (wysoka jakość)
- Szerokość linii: 0.4mm (standardowa dysza)
- Wypełnienie: 25-40% (Gyroid lub Grid)
- Perimety (ściany): 4-5 linii (=1.6-2.0mm mur)
- Top/Bottom layers: 4-6 (=0.8-1.2mm płyta)
- Temperatura dyszy: 245°C (PETG)
- Temperatura stołu: 85°C
- Prędkość druku: 50mm/s (perim.), 80mm/s (infill)
- Chłodzenie: 50% (PETG nie lubi pełnego chłodzenia)
- Retraction: 1.5mm / 30mm/s (Direct Drive)
- Ironing: TAK dla górnych powierzchni estetycznych

### Szacowanie czasu i materiału
- Gęstość PLA: 1.24 g/cm³, PETG: 1.27 g/cm³
- Filament 1.75mm, ⌀=1.75: 1m ≈ 2.98g (PLA)
- Szacunek: 1cm³ bryły → ~0.25-0.35g filamentu (25-40% infill)
