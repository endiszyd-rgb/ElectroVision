# ElectroVision — Changelog / Blog

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
