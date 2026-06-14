# PCB Design Rules — Kompletny przewodnik

## Szerokości ścieżek (Trace Width)

### Reguła prądu IPC-2221
Wzór: W [mm] = I / (k × ΔT^0.44 × t^0.725)
- I = prąd [A]
- k = 0.048 dla zewnętrznych, 0.024 dla wewnętrznych warstw
- ΔT = dopuszczalny wzrost temperatury [°C] (zazwyczaj 10°C)
- t = grubość miedzi [oz] (standardowo 1oz = 35µm)

### Tabela praktyczna
| Prąd [A] | Min. szerokość 1oz zewnętrzna | 1oz wewnętrzna |
|---|---|---|
| 0.1A | 0.15mm | 0.25mm |
| 0.5A | 0.25mm | 0.50mm |
| 1.0A | 0.50mm | 1.00mm |
| 2.0A | 0.80mm | 1.60mm |
| 5.0A | 2.50mm | 4.00mm |
| 10.0A | 5.00mm | (plane) |

### Impedancja kontrolowana
- Single-ended 50Ω: SPI, I2C, GPIO >50MHz, RF
- Differential 90Ω: USB 2.0 D+/D-
- Differential 100Ω: LVDS, Ethernet 100Base-T
- Differential 85Ω: USB 3.0
- Oblicz: Saturn PCB Design Toolkit (bezpłatny)

## Prześwity (Clearance)

### Napięcia poniżej 50V
- Sygnał do sygnału: ≥0.15mm
- Zasilanie do masy: ≥0.2mm
- Wewnętrzne warstwy: można zmniejszyć o 30%

### Wysokie napięcia (IPC-2221 Class B3)
- 50-150V: ≥0.5mm
- 150-300V: ≥1.0mm
- 300-600V: ≥2.0mm
- 600-1200V: ≥4.0mm
- 230V AC (wejście sieciowe): ≥3.0mm (bezpieczne minimum)

### RF i HF
- Antena: ≥0.3mm od innych elementów + clearance ≥ szerokość ścieżki
- Kryształ: ≥0.5mm od ścieżek, zero ścieżek pod kryształem

## Przelotki (Via)

### Standardowe przez-otworowe
- Drill min: 0.2mm (PCBWay, JLCPCB standard: 0.3mm)
- Pad min: drill + 0.25mm annular ring
- Rekomendowane: drill 0.4mm, pad 0.8mm
- Aspect ratio: głębokość/drill ≤ 10:1 (dla PCB 1.6mm = drill ≥ 0.16mm)

### Micro via (HDI)
- Drill: 0.1-0.15mm
- Tylko przez 1 warstwę (blind via)
- Koszt: 2-3× droższe

### Via termiczne
- Cel: odprowadzanie ciepła spod padu MOSFET/regulator
- Grid: co 1.0mm, drill 0.3mm, pad 0.7mm
- Zalew epoksydowy (via plugging) jeśli pad SMD na via

### Via-in-pad
- Dozwolone jeśli wypełnione (electroplated fill)
- Bez wypełnienia: tin wcieka przez via podczas lutowania

## Pady i Footprinty

### Standard IPC-7351B Level B (nominal)
Używaj Level B jako domyślny (balans między kompaktowością a lutowalnością):

| Obudowa | Pad size (L×W) | Pitch |
|---|---|---|
| 0201 | 0.6×0.5mm | — |
| 0402 | 0.9×0.65mm | — |
| 0603 | 1.5×0.9mm | — |
| 0805 | 2.2×1.4mm | — |
| 1206 | 3.4×1.8mm | — |
| SOT-23-3 | 1.0×1.3mm | 1.9mm |
| SOT-23-5 | 0.9×1.1mm | 0.95mm |
| QFP-32 | 0.45×1.6mm | 0.8mm |
| QFN-32 | 0.4×0.5mm | 0.5mm |
| BGA-64 | 0.45mm circ | 0.8mm |
| THT ⌀0.8 lead | pad 1.6mm | — |

### Zasady silkscreen
- Nie na padach (DRC error)
- Min. rozmiar tekstu: 0.5mm wysokość, 0.1mm grubość
- Referencja komponentu: czytalna po zmontowaniu
- Polarity marking: + przy kondensatorach elektrolitycznych, pin 1 przy IC

## Stackup warstw

### 2-layer (tani, do ~100MHz)
```
TOP  Cu 35µm
     FR4 1.6mm
BOT  Cu 35µm
```
Koszt: $2 za 5 szt 10×10cm (JLCPCB)

### 4-layer (zalecany, do 1GHz)
```
L1  TOP  Cu 35µm
         Prepreg 0.2mm (Er=4.4)
L2  GND  Cu 35µm       ← ciągła płaszczyzna GND
         Core 1.2mm
L3  PWR  Cu 35µm       ← płaszczyzna VCC/VDD
         Prepreg 0.2mm
L4  BOT  Cu 35µm
```
Koszt: ~$10 za 5 szt (JLCPCB)
50Ω dla 0.15mm ścieżki na L1 nad L2 GND (verify w kalkulatorze!)

### 6-layer (dla USB 3.0, DDR, PCIe)
```
L1  Sygnał
L2  GND
L3  Sygnał (controlled impedance pairs)
L4  Sygnał (controlled impedance pairs)
L5  PWR
L6  Sygnał
```

## Reguły montażu (DFM)

### SMD — fala lutownicza vs reflow
- Strona TOP: reflow (pasta + pick & place + piec)
- Strona BOT z SMD: drugi reflow lub wave soldering (ryzyko!)
- Komponenty THT: ręczne lutowanie lub wave soldering

### Clearance komponentów
- SMD-SMD: ≥0.2mm
- THT do krawędzi: ≥2mm (dla fali lutowniczej)
- Komponenty wysokie (kond. elektrolit.): ≥5mm od sąsiadów
- Heatsink clearance: sprawdź w datasheet

### Test pointy (ICT)
- Umieść na każdym węźle sygnałowym
- ⌀1.0mm pad, siatka ≥2.54mm (standardowe sondy)
- Strona BOT (typowo dla łoża gwoździ)
- Oznacz jako TP1, TP2 na silkscreen

### Panel (panelizacja do produkcji)
- V-cut: kąt 45°, głębokość 1/3 grubości PCB
- Mouse bites: otwory ⌀0.5mm w rzędzie, co 0.8mm
- Tooling holes: ⌀3.2mm w narożnikach panelu (dla pick & place)
- Fiducial marks: ⌀1.0mm Cu pad, clearance ⌀3mm, 3 szt

## Eksport Gerber z KiCad

### Pliki wymagane przez producentów
1. F.Cu.gbr — górna warstwa miedzi
2. B.Cu.gbr — dolna warstwa miedzi
3. F.Mask.gbr — maska górna
4. B.Mask.gbr — maska dolna
5. F.SilkS.gbr — silkscreen górny
6. B.SilkS.gbr — silkscreen dolny
7. Edge.Cuts.gbr — krawędź PCB
8. drill.drl — otwory (format Excellon)
9. (opcjonalnie) In1.Cu, In2.Cu — warstwy wewnętrzne

### Ustawienia KiCad (Plot)
- Format: Gerber
- Gerber precision: 4.6 (10nm)
- Subract soldermask from silkscreen: TAK
- Use Gerber X2 format: TAK (dla nowoczesnych fabów)
