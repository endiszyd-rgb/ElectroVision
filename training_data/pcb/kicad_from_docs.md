# KiCad PCB Design — Dane z oficjalnej dokumentacji (docs.kicad.org)

## Reguły projektowe (Design Rules)

### Ograniczenia globalne (Constraints)
- Copper Clearance: minimalne odstępy między elementami miedzianymi
- Track Width: bezwzględne minimum szerokości ścieżki
- Via Sizes: minimalna średnica otworu i pad
- Arc Approximation Error: maksymalny błąd aproksymacji łuku = 0.005mm (domyślnie)
- Thermal Relief Spokes: minimalna liczba pasm termicznych do strefy

### Net Classes
Każda sieć należy do klasy z konfigurowalnymi parametrami:
- Copper clearance — odstęp miedź do miedzi
- Track width — zalecana szerokość (nie minimum)
- Via size — preferowana wielkość przelotki (annulus + hole)
- Differential pair spacing and gap

"Wartości te będą użyte przy tworzeniu ścieżek i przelotki, chyba że bardziej szczegółowa reguła je nadpisze."

## Warstwy

### Warstwy miedziane
- Do 32 warstw miedzianych
- KiCad wymaga parzystej liczby warstw
- Maksymalne wymiary płytki: ~4m × 4m (rozdzielczość 1nm, 32-bit)

### Warstwy technologiczne (14 dostępnych)
- Silkscreen (Front + Back)
- Solder Mask (Front + Back)
- Solder Paste (Front + Back)
- Component Adhesive (Front + Back)
- Fabrication layers (Front + Back)
- Courtyard layers (Front + Back)
- Board Edge (Edge.Cuts)

### Warstwy ogólnego przeznaczenia
13 warstw użytkownika do własnych zastosowań (User.Drawings, User.1-9)

## Routing (Trasowanie)

### Tryby routera
1. **Highlight Collisions** — ręczne trasowanie, do 2 segmentów na akcję, nie przesuwa przeszkód
2. **Shove** — automatyczne przesuwanie przeszkód, przesuwa ścieżki i komponenty
3. **Walk Around** — omija przeszkody bez przesuwania

### Kąty ścieżek
- Tryb standardowy: poziome/pionowe (H/V) i 45°
- Tryb Highlight Collisions: dowolne kąty

### Typy przelotki
- Through via — przez całą grubość płytki
- Microvia — tylko przez 1 warstwę (HDI)
- Blind via — od warstwy zewnętrznej do wybranej
- Buried via — między warstwami wewnętrznymi

## Strefy miedzi (Copper Zones)

### Parametry wypełnienia
- Priority Level: kolejność wypełniania nakładających się stref
- Minimum Width: minimalna szerokość wąskich szyjek (usuwane poniżej progu)
- Corner Smoothing: sfazowanie (chamfer) lub zaokrąglenie (fillet) z konfigurowalnym rozmiarem
- Island Removal: usuwanie izolowanych wysp miedzi poniżej progu
- Hatch Fill: alternatywa dla pełnego wypełnienia (siatka z konfigurowalną orientacją, szerokością, odstępem)

### Thermal Reliefs (Odciążenie termiczne)
- Solid: pełny kontakt miedzią
- Thermal Reliefs: pasma z przerwami (zwiększa odporność termiczną — łatwiejsze lutowanie THT)
- Reliefs for PTH: mix (thermal dla THT, solid dla SMD)
- None: brak połączenia ze strefą

Konfigurowalne: liczba pasm, odstęp, szerokość pasma

## Teardrops
Płynne rozszerzenie ścieżki do pada/przelotki:
- Zapobiega oderwaniu pada przy naprężeniach
- Konfiguracja dla: okrągłych padów, prostokątnych padów, ścieżka-do-ścieżki
- Parametry: proporcje (długość × szerokość), typ krzywej

## DRC (Design Rule Check)

### Kategorie sprawdzeń
- Clearance violations (naruszenia prześwitu)
- Unconnected nets (niepołączone sieci — ratsnest)
- Short circuits (zwarcia)
- Silkscreen on pads (silkscreen na padach)
- Courtyard overlap (nakładające się courtyards)
- Via annular ring violations
- Board edge clearance
- Hole size violations

### Custom DRC Rules
KiCad obsługuje własny język reguł DRC:
```
(rule "High voltage clearance"
  (condition "A.NetClass == 'HV' || B.NetClass == 'HV'")
  (constraint clearance (min 3mm))
)
```

## Predefiniowane rozmiary ścieżek i przelotki
"Zdefiniuj wymiary ścieżek i przelotki, które chcesz mieć dostępne podczas trasowania."
Szybki dostęp przez skrót klawiszowy podczas interaktywnego routingu.

## Eksport Gerber
Pliki niezbędne do produkcji:
- *.Cu (wszystkie warstwy miedziane)
- *.Mask (maski lutownicze)
- *.SilkS (silkscreen)
- Edge.Cuts (kontur płytki)
- *.drl (wiercenia Excellon)

Format: Gerber X2 (zalecany dla nowoczesnych fabów, zawiera metadane)
Precyzja: 4.6 (10nm rozdzielczość)

Źródło: https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html
