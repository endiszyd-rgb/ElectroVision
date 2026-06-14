# ElectroVision — Changelog / Blog

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
