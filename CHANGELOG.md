# ElectroVision — Changelog / Blog

## v0.10.0 — 2026-06-16

### Co nowego

#### Autorouter — automatyczne trasowanie ścieżek (Ctrl+Shift+2)
Nowy moduł `src/algorithms/autorouter.py`: silnik trasowania na siatce 2-warstwowej
(F.Cu/B.Cu) algorytmem A* (odmiana algorytmu Lee/wave-propagation):
- `collect_unrouted_nets(board)` — wykrywa sieci niepołączone w pełni (heurystyka: liczność
  segmentów ścieżek < N-1 dla N padów sieci)
- `RouteGrid` / `build_grid_from_board()` — siatka z przeszkodami z istniejących padów
  (uwzględnia rotację komponentu), ścieżek i przelotek; pady przewlekane blokują obie warstwy
- `route_two_points()` — A* z 8 kierunkami ruchu na warstwie + przejście międzywarstwowe (via)
  z karą kosztową, żeby preferować trasowanie na jednej warstwie
- `route_net()` — łączy wielopadowe sieci metodą Prima (MST): dołącza najbliższy niepołączony
  pad jeden po drugim, blokując już ułożone ścieżki jako przeszkody dla kolejnych segmentów
- `autoroute_board()` — trasuje całą płytkę, sieci sortowane od najprostszych (najmniej padów),
  zwraca `AutorouteResult` z listą trasowanych/nieudanych sieci i sumaryczną długością
- `src/ui/dialogs/autorouter_dialog.py` — dialog z podglądem przed zastosowaniem: parametry
  (rozmiar siatki, szerokość ścieżki, prześwit, wiertło/średnica przelotki, limit sieci),
  generowanie w wątku tła, tabela wynikowa per sieć (✓/✗), przycisk „Zastosuj do projektu"

#### Naprawiono
- Błąd importu `QShortcut` (`PySide6.QtWidgets` → `PySide6.QtGui` w Qt6) w
  `src/ui/panels/pcb_editor_panel.py`, który blokował uruchomienie całej aplikacji

#### Testy (46 nowych)
- `TestPadWorldPos` — pozycja pada z uwzględnieniem rotacji komponentu (0°/90°/180°)
- `TestCollectUnroutedNets/TestRouteGrid/TestBuildGridFromBoard` — wykrywanie sieci, siatka, przeszkody
- `TestRouteTwoPoints/TestSimplifyPath/TestPathLength/TestRouteNet` — ścieżkowanie A*, uproszczenie trasy
- `TestAutorouteBoard` — integracja end-to-end, limit sieci, success rate, szerokość ścieżek
- Łącznie: 281 testów

## v0.9.0 — 2026-06-16

### Co nowego

#### Opisowe tworzenie obiektów 3D i eksport STL (Ctrl+Shift+3)
Silnik geometryczny `src/generators/descriptive_stl.py` na bazie `trimesh` + `manifold3d` (CSG):
- **Parser opisu PL/EN** — `parse_description(text)` rozpoznaje wymiary (`60x40x25`), grubość ścianki,
  słowa kluczowe (`z wiekiem`/`lid`, `standoffy`/`standoffs`), typ obiektu (obudowa/panel/kątownik/standoff)
  oraz 15+ wycięć na złącza (USB-C, micro/mini USB, HDMI, RJ45, DC Jack, jack 3.5mm, SD card, OLED, wentylacja…)
- **Presety płytek** — arduino (uno/nano), esp32, esp8266, raspberry (pi4/zero), rp2040/pico, STM32 Blue Pill, 18650
- **6 fabryk geometrii**: `make_enclosure` (pudełko z wiekiem, standoffami M3, zaokrąglonymi narożnikami,
  wycięciami CSG-difference), `make_panel`, `make_bracket`, `make_standoff`, `make_din_clip`, `make_cable_clip`
- Dialog z 4 zakładkami: opis tekstowy z podglądem parsowania, formularz obudowy z 15 presetami,
  inne obiekty (panel/kątownik/standoff/klips DIN/klips na kabel), edytor prymitywów CSG (box/cylinder/sphere, add/sub)
- Generowanie w wątku tła (`QThread`), podgląd 3D w `STL3DView`, eksport STL per-część do wybranego folderu

#### Testy (60 nowych)
- `TestPrimitive/TestHoleSpec/TestCutoutSpec` — dataclasses geometrii
- `TestParseDescription` — wymiary, presety, wycięcia, typy obiektów, słowa kluczowe PL/EN
- `TestMakeWithTrimesh` — mesh generation, CSG enclosure z wycięciami, eksport STL na dysk
- Łącznie: 235 testów

## v0.8.0 — 2026-06-15

### Co nowego

#### Menedżer punktów testowych — ICT / Flying Probe (Ctrl+Shift+I)
- Automatyczne wykrywanie TP* / TEST* komponentów na płytce
- Raport pokrycia sieci: % sieci z punktem testowym, lista sieci bez TP
- Mapa QPainter: wszystkie TP zaznaczone na układzie płytki (front=zielony, back=czerwony)
- Podświetlanie wybranej sieci na mapie przy kliknięciu TP w tabeli
- Dodawanie nowych TP przez formularz (ref, sieć, X/Y, strona, średnica)
- Usuwanie TP z projektu bezpośrednio z listy
- Eksport CSV dla testera latającego (format Spea/GenRad/Takaya): ref, net, X, Y, strona, śr.

#### Profile reguł DRC — presety fabrykatów (Ctrl+Shift+Q)
9 wbudowanych profili z rzeczywistymi wymaganiami:
- **JLCPCB Standard** — 5/5 mil (0.127 mm), via ≥0.3 mm
- **JLCPCB Advanced (HDI)** — 3/3 mil (0.075 mm), laser via ≥0.1 mm
- **PCBWay Standard** — 4 mil (0.1 mm), via ≥0.3 mm
- **PCBWay Advanced (HDI)** — 2 mil (0.05 mm), microvia ≥0.1 mm
- **OSH Park** — 5 mil, drill ≥10 mil (0.254 mm), USA
- **Eurocircuits Standard** — 4 mil, certyfikat UL/REACH/RoHS
- **ITead/Seeed Standard** — 6 mil, 10 kolorów soldermask
- **Hobbyist** / **Profesjonalny** — liberalne/restrykcyjne reguły ogólne

Funkcje: jednym kliknięciem zastosuj profil do projektu (aktualizuje PCBValidator), porównanie z bieżącymi ustawieniami DRC, eksport/import JSON, duplikowanie i edycja profili

#### Testy (31 nowych)
- `TestIsTestPoint` — detekcja TP/TEST prefix
- `TestScanTestPoints` — zbieranie TP z boardu, pozycje, sieci
- `TestCoverageReport` — pokrycie sieci, F/B count, lista niepokrytych
- `TestExportCSV` — header, liczba wierszy, sortowanie po ref
- `TestDRCProfile` — serialization, check_vs_profile, JSON roundtrip
- `TestBuiltinProfiles` — count, JLCPCB reguły, Advanced < Standard
- Łącznie: 175 testów

## v0.7.0 — 2026-06-15

### Co nowego

#### Analizator miedzianych wylewy — Copper Pour (Ctrl+Shift+P)
Trzy zakładki:
- **Statystyki stref** — tabela wszystkich `CopperZone` z: warstwą, siecią, polem [mm²], obwodem [mm], liczbą padów wewnątrz, prześwitem; pasek postępu wypełnienia miedzi; podsumowanie per warstwa
- **Edytor strefy** — zmiana warstwy, sieci, prześwitu, priorytetu i wierzchołków poligonu (format X,Y jeden na linię); przycisk „Wstaw prostokąt z płytki"
- **Wskazówki DFM** — automatyczne raporty: niskie/wysokie wypełnienie, brak B.Cu GND, zbyt małe prześwity, strefy bez padów
- Podgląd QPainter — płytka z konturem i strefami zakolorowanymi per warstwa, podświetlenie zaznaczonej strefy

#### Generator symboli schematycznych (Ctrl+Shift+M)
Eksport do KiCad 7 `.kicad_sym`:
- Tabela pinów: numer, nazwa, typ (10 typów: input/output/bidirectional/power_in/GND/...), strona (L/P/G/D), długość
- Auto-układ: `input`→lewy, `output`→prawy, `VCC/VDD`→górny, `GND/VSS`→dolny, `no_connect`→prawy
- Dodawanie hurtowe pinów przez okno tekstowe (format: `NR NAZWA TYP STRONA`)
- 4 wbudowane presety: Op-Amp, N-MOSFET, MCU 8-pin, Złącze 4-pin
- Podgląd QPainter w czasie rzeczywistym z kolorami per typ pinu
- Eksport `.kicad_sym` gotowy do dodania jako biblioteka w KiCad > Symbol Editor

#### Testy (43 nowe)
- `TestPolygonArea/Perimeter/PointInPolygon` — geometria stref (shoelace, ray casting)
- `TestAnalyseZones/TestBoardCopperSummary` — analiza padów wewnątrz strefy, pole per warstwa
- `TestSymPin/TestSymbolDef/TestPresets/TestKiCadExport` — auto-layout, presety, format .kicad_sym
- Łącznie: 144 testów

## v0.6.0 — 2026-06-15

### Co nowego

#### Klasy sieci — Net Classes Manager (Ctrl+Shift+C)
Definiowanie reguł trasowania per klasa sieci:
- 6 wbudowanych presetów: Default, Power, HighSpeed, DiffPair, RF, Analog
- Konfiguracja: min. szerokość ścieżki, prześwit, wiercenie/pierścień przelotki, gap i skew pary różnicowej
- Kolor podświetlenia każdej klasy (wybór z color pickera)
- Przypisywanie sieci do klas ręcznie lub przez auto-przypisanie z projektu (wzorzec)
- Eksport / import JSON, przełącznik presetów

#### Warianty projektu — Design Variants Manager (Ctrl+Shift+V)
Zarządzanie alternatywnymi konfiguracjami BOM:
- Tworzenie wielu wariantów (produkcyjna, prototyp, lite, DNI…)
- Oznaczanie komponentów jako DNP (Do Not Populate) per wariant
- Podstawianie wartości i obudów per komponent per wariant
- Duplikowanie wariantu, filtrowanie tabeli, masowe DNP zaznaczonych
- Eksport BOM wariantu do CSV, eksport/import konfiguracji JSON
- Pasek statusu: łącznie / montowane / DNP per wariant

## v0.5.0 — 2026-06-15

### Co nowego

#### Topologia sieci — graf połączeń (Ctrl+Shift+Y)
Dialog renderuje netlist jako graf z układem Fruchterman-Reingold:
- Węzły = komponenty, krawędzie = sieci elektryczne
- Kolory węzłów według typu (IC, rezystor, kondensator, …)
- Filtry: ukryj szyny zasilania / GND, filtr po nazwie sieci
- Zoom + pan, klik w węzeł → info panel z listą sieci, klik w krawędź → lista komponentów
- Parametry: liczba iteracji layoutu, maksymalna liczba węzłów

#### Generator tablicy komponentów (Ctrl+Shift+B)
Duplikowanie wybranego komponentu w regularnych wzorcach:
- Tryb siatki (rows × cols), liniowy poziomy lub pionowy
- Automatyczne nadawanie unikalnych referencji z wybranego numeru startowego
- Opcjonalne przypisanie sieci per element (`LED{n}`, `PWM{n}`, …)
- Podgląd canvas + tabela pozycji przed zatwierdzeniem

#### Analiza długości ścieżek / Pary różnicowe (Ctrl+Shift+E)
Trzy zakładki:
- **Długości ścieżek** — sortowalna tabela wszystkich sieci: długość [mm], liczba ścieżek, śr. szerokość, warstwy, opóźnienie [ps] przy zadanym Er
- **Pary różnicowe** — auto-detekcja par P/N (+/−, DP/DN) z mismatching [mm] i [ps], threshold tolerancji
- **Analizy krytyczne** — raport tekstowy: najdłuższe ścieżki, sumaryczna długość, pary poza tolerancją

#### Testy jednostkowe (35 nowych testów)
Pokrycie modułów v0.4: `test_new_modules.py` — power analysis, DFM checker, auto-annotation, netlist generator, stackup impedance, signal analysis, board outline (35 testów, 64 łącznie).

#### Poprawki błędów
- `component.component_type`: sprawdzenie `LED` teraz wyprzedza `L` (inductor) — `LED1` nie był już klasyfikowany jako cewka
- `_parse_capacitance_uf`: 1 mF → 1000 µF (nie 1 000 000 µF)
- `calc_via_inductance_nh`: stała IPC-2141A (5.08) dotyczy cali — podzielono przez 25.4 dla wejść mm → prawidłowy wynik ~1.3 nH zamiast ~0.033 nH

---

## v0.4.0 — 2026-06-15

### Co nowego

#### Analiza zasilania (Ctrl+Shift+W)
Nowy dialog analizuje płytkę PCB pod kątem zasilania:
- Automatyczna detekcja szyn zasilania z nazw sieci (VCC, 3.3V, VDD, VBUS, VBAT, …)
- Szacowanie poboru prądu per komponent — baza 35+ typów (ESP32, STM32, L298, LED, …)
- Budżet mocy: prąd [mA], moc [mW], napięcie, liczba komponentów per rail
- Sprawdzenie kondensatorów blokujących (1 × 100nF na IC) i bulk (>10 µF gdy >200 mA)
- Zalecenia: typ regulatora, wartość kondensatorów, minimalna szerokość ścieżki (IPC-2221)
- Eksport raportu TXT

#### Estymacja termiczna (Ctrl+Shift+T)
Dialog oblicza temperaturę złącza T_j dla każdego komponentu:
- Baza θ_JA (°C/W) dla 15+ popularnych pakietów (TO-220, SOT-223, QFN, LQFP, …)
- T_j = T_amb + θ_JA × P — parametryzowalna temperatura otoczenia i typ chłodzenia
- Progi: OK (<70°C) / Podwyższony (70–100°C) / Wysoki (100–150°C) / KRYTYCZNY (>150°C)
- Zalecenia dla komponentów krytycznych (radiator, plane miedzi)

#### Analiza sygnałowa / SI
Zakładki dla trzech zagadnień sygnałowych:
- **Propagacja** — opóźnienie propagacji (ps/mm), krytyczna długość ścieżki (λ/4 rule), efektywne pasmo z czasu narastania (BW = 0.35/Tr), automatyczna rekomendacja terminacji
- **Przesłuch** — NEXT (coupling coefficient), reguła 3W, długość równoległego odcinka
- **Przelotka** — indukcyjność (IPC-2141A), reaktancja przy danej częstotliwości, optymalizacja (back-drill, via-in-pad)
- Skanowanie wszystkich ścieżek projektu i oznaczanie tych wymagających terminacji

#### Edytor stosu warstw (Ctrl+Shift+L)
Pełny edytor PCB stackupu:
- 3 szablony: 2-warstwowa / 4-warstwowa (JLC) / 6-warstwowa FR4
- Wizualny przekrój poprzeczny z skalą proporcjonalną do grubości
- Edycja: nazwa, typ, grubość, εr, tan δ, materiał
- **Kalkulator impedancji microstrip i stripline** per warstwa (IPC-2141A)
- Solver szerokości W dla zadanej Z₀ (np. 50 Ω) metodą bisekcji
- Kolor wskaźnika: zielony ±5 Ω / żółty ±15 Ω / czerwony

#### Wyszukiwarka komponentów (Ctrl+F)
Lokalna baza 30+ popularnych komponentów z linkami do sklepów:
- Filtrowanie po nazwie, wartości, LCSC# i kategorii
- Linki: LCSC (direct), DigiKey, Mouser, TME, Botland
- Dodaj do projektu jednym kliknięciem — auto-generacja referencji

#### Netlist export
- **Netlist CSV** — per pad (Net, Component, Reference, Pin, X_mm, Y_mm)
- **Net summary CSV** — per net (Net, Pins, Members)
- **Netlist KiCad (.net)** — bracket notation kompatybilny z KiCad

#### JLCPCB / PCBWay export (Ctrl+Shift+G)
ZIP z pełnym pakietem produkcyjnym: pliki Gerber, BOM CSV (format LCSC), CPL CSV (placement list, Y-axis flip).

#### Autosave
Automatyczny zapis projektu co 5 minut do `~/.electrovision_autosave/`. Interwał konfigurowalny w Ustawieniach.

#### Rozszerzony panel statystyk
Statystyki płytki (zakładka w edytorze PCB) pokazują teraz: wymiary, powierzchnię, gęstość komponentów (komp/cm²), łączną długość ścieżek, zakres szerokości, warstwy aktywne.

---

## v0.3.0 — 2026-06-14

### Co nowego

#### AI STL Designer — opisz obudowę słowami, dostań gotowy plik 3D
Nowy moduł w zakładce STL/STEP 3D. Wpisujesz opis obudowy np.  
*„Obudowa IP54 do PCB 80×60mm, montaż na szynę DIN, otwory: USB-C na lewej ścianie, DC Jack na prawej"*  
— AI generuje kod Python (trimesh lub CadQuery), wykonuje go w sandboxie i pokazuje podgląd 3D.  
Możesz edytować kod, wykonać ponownie i zapisać gotowy STL.  
Dostępne 6 szablonów (IP65, DIN, rack 1U, minimalna SMD, drukowana standardowa).  
Podświetlanie składni Python i streaming odpowiedzi AI w czasie rzeczywistym.

#### Edytor PCB — dialog właściwości komponentu
Dwuklik na dowolnym komponencie w trybie SELECT otwiera okno właściwości:  
ref, wartość, footprint, XY, rotacja, warstwa. Wszystkie zmiany można cofnąć (Ctrl+Z).

#### Nakładka DRC na edytorze PCB
Po uruchomieniu walidacji DRC błędy pojawiają się bezpośrednio na płytce jako czerwone X z opisem.  
Kliknij „Uruchom walidację" w zakładce Walidacja DRC — błędy pojawią się zarówno w tabeli jak i na edytorze.

---

## v0.2.0 — 2026-05

### Co nowego

#### AI Generator projektu PCB
Opisz projekt słowami: *„Sterownik silnika DC 12V z PWM, ESP32, zabezpieczenie przetężeniowe, enkodery"*.  
AI generuje projekt z komponentami, sieciami i wstępnym rozmieszczeniem — gotowy do edycji w edytorze.

#### Edytor PCB — rozbudowa
- Strefy miedzi (copper pour) z wyborem sieci i eksportem do Gerber
- Ratsnest — wizualizacja brakujących połączeń z przełącznikiem (N)
- Widoczność warstw — checkboxy z kolorowymi kropkami, przyciski „Wszystkie / Tylko Cu"
- Znajdź komponent: Ctrl+F → lista wszystkich komponentów z filtrowaniem

#### Ustawienia (Ctrl+,)
Dialog z czterema zakładkami: AI/Ollama (model, host, timeout), DRC (progi), Edytor PCB (siatka, szerokość ścieżki), Ogólne (motyw, autosave).  
Ustawienia zapisywane w `~/.electrovision_settings.json`.

#### Wskaźnik Ollama w pasku statusu
Zielona / czerwona kropka pokazuje w czasie rzeczywistym czy serwer AI jest dostępny.  
Automatyczne sprawdzanie co 8 sekund.

#### `start.bat` — jednoklinkowe uruchomienie
Skrypt tworzy venv Python w `C:\ev`, instaluje wymagania, uruchamia Ollama i aplikację.  
Na końcu sesji zatrzymuje Ollama jeśli go uruchomił.

#### Gerber + Drill export (Ctrl+G)
Eksport plików produkcyjnych: F.Cu, B.Cu, F.SilkS, B.SilkS, F.Mask, B.Mask, Edge.Cuts + plik wiercenia Excellon.

---

## v0.1.0 — 2026-04

### Pierwsze wydanie

- PCB 2D/3D przeglądarka (QPainter + Three.js)
- Interaktywny edytor PCB: SELECT, ROUTE, VIA, DELETE, ADD_COMP
- Import `.kicad_pcb` i `.kicad_sch`
- BOM — eksport CSV / Excel / PDF
- Generator kodu MCU: Arduino, MicroPython, C++/ESP-IDF
- STL generator obudów (trimesh + baza wysokości komponentów)
- DRC walidator z AI wyjaśnieniami (Ollama)
- Net Inspector z podświetlaniem sieci
- Baza komponentów PCB
- GitHub + Google Drive sync
- Lokalny serwer projektów (Flask)
- Szablony projektów (Arduino Nano, ESP32, STM32, RP2040)
- Nauka AI z URL / PDF / tekstu
- AI Asystent z RAG i bazą wiedzy PCB/STL

---

## Architektura w skrócie

```
main.py
  └─ MainWindow (PySide6)
       ├─ PCBEditorPanel         ← edytor canvas (QPainter)
       ├─ STLGenPanel            ← generator + AI Designer
       ├─ ValidationPanel        ← DRC → nakładka na edytorze
       ├─ NetInspectorPanel      → highlight sieci w edytorze
       └─ ComponentsPanel        → umieszczanie z biblioteki
```

AI lokalnie przez **Ollama** (Llama 3 / Mistral / CodeLlama / Qwen2) — zero chmury, zero API key.

---

## Roadmapa

- [ ] Spice netlist — basic symulacja obwodów
- [ ] Auto-router AI — pełne trasowanie z Ollama
- [ ] Podgląd 3D z komponentami (THT + SMD) w edytorze
- [ ] Plugin system — zewnętrzne moduły Python
- [ ] Eksport JLCPCB / PCBWay (BOM + CPL + Gerber w jednym ZIP)
