# ElectroVision

Desktopowa aplikacja do projektowania elektroniki PCB z lokalnym AI (Ollama), interaktywnym edytorem płytki, wizualizacją 3D, generatorem kodu MCU, eksportem STL/STEP obudów oraz zestawem narzędzi analizy elektronicznej.

---

## Szybki start

```bash
# Jednoklikowe uruchomienie (Windows)
start.bat

# Lub ręcznie:
pip install -r requirements.txt
python main.py
```

Wymaga:
- **Python 3.10+** (zalecany 3.11 lub 3.12)
- **[Ollama](https://ollama.ai)** — `ollama serve` + `ollama pull llama3`

Opcjonalnie: KiCad 7/8 · PrusaSlicer/Cura · Arduino IDE

---

## Możliwości

### Edytor PCB (interaktywny)
- Tryby: **Wybierz / Trasuj / Przelotka / Usuń / Strefa miedzi / Umieść komponent / Pomiar**
- Skróty: `S` Wybierz · `R` Trasuj · `V` Przelotka · `X` Usuń · `Z` Strefa · `T` Pomiar · `Space` Obróć · `M` Lustro · `F` Dopasuj · `Ctrl+D` Duplikuj · `Ctrl+Z/Y` Cofnij/Ponów
- Biblioteka komponentów: R, C, LED, diody, złącza, MCU, tranzystory, kryształy, drivery
- Warstwy: widoczność per warstwa, tylko Cu, wszystkie
- Ratsnest (brakujące połączenia), copper pour (strefy miedzi)
- **Dwuklik na komponent** → dialog właściwości (ref, wartość, footprint, XY, rotacja, warstwa, ±90°, mirror)
- **Klik ścieżki** → pokazuje długość, impedancję Z₀ (IPC-2141A), maks. prąd (IPC-2221)
- **Narzędzie pomiaru (T)** — mierzy odległość między dwoma punktami na płytce
- **Nakładka DRC** — błędy wyświetlane jako czerwone X bezpośrednio na edytorze
- Historia cofnij/ponów z opisami komend
- Snap-to-grid (siatka konfigurowalna)
- Statystyki płytki: wymiary, gęstość komponentów, łączna długość ścieżek, aktywne warstwy
- Eksport do `.kicad_pcb`

### Narzędzia analizy elektronicznej (menu Narzędzia)

#### Kalkulator elektroniczny (Ctrl+K)
- Microstrip / stripline impedancja (IPC-2141A, 5 zakładek)
- Prąd ścieżki (IPC-2221 krzywe A/B, zewnętrzna/wewnętrzna)
- Filtr RC — częstotliwość odcięcia
- Dzielnik napięcia
- Rezystor LED z doborem wartości E24

#### Analiza zasilania (Ctrl+Shift+W)
- Detekcja szyn zasilania z nazw sieci (VCC, 3.3V, VDD, VBUS, …)
- Szacowanie poboru prądu per komponent (30+ typów z bazy)
- Budżet mocy: prąd, moc, napięcie, liczba komponentów per rail
- Sprawdzenie kondensatorów blokujących i bulk
- Zalecenia: regulator, kondensatory, minimalna szerokość ścieżki
- Eksport raportu TXT

#### Estymacja termiczna (Ctrl+Shift+T)
- Temperatura złącza T_j = T_amb + θ_JA × P dla każdego komponentu
- Baza θ_JA dla 15+ popularnych pakietów i IC
- Współczynnik chłodzenia (konwekcja naturalna, wentylator, plane miedzi)
- Progi: OK / Podwyższony / Wysoki / KRYTYCZNY
- Eksport raportu TXT

#### Analiza sygnałowa / SI
- Opóźnienie propagacji i krytyczna długość ścieżki (λ/4 rule)
- Efektywne pasmo z czasu narastania (BW = 0.35/Tr)
- Przesłuch NEXT (reguła 3W, coupling coefficient)
- Indukcyjność przelotki (IPC-2141A)
- Skanowanie ścieżek projektu vs krytyczna długość przy danej częstotliwości

#### Edytor stosu warstw (Ctrl+Shift+L)
- Szablony: 2-warstwowa / 4-warstwowa / 6-warstwowa (FR4, JLC)
- Wizualny przekrój poprzeczny stosu z skalą grubości
- Dodawanie/usuwanie/przesuwanie warstw
- Kalkulator impedancji microstrip i stripline per warstwa
- Solver szerokości dla zadanej impedancji docelowej (np. 50 Ω)
- Kolor wskaźnika: zielony (±5 Ω od celu) / żółty (±15 Ω) / czerwony
- Eksport stackupu do TXT

#### Wyszukiwarka komponentów (Ctrl+F)
- Lokalna baza 30+ popularnych komponentów (R, C, LED, IC, złącza, …)
- Filtrowanie po kategorii i frazie
- Linki do sklepów: LCSC (direct), DigiKey, Mouser, TME, Botland
- Dodaj do projektu jednym kliknięciem (auto-generacja referencji)

### AI — Generator projektu PCB
- Opisz słowami: *„Sterownik silnika DC 12V, ESP32, zabezpieczenie przetężeniowe"*
- AI (Ollama) generuje projekt z komponentami, sieciami i układem

### AI — Designer obudowy STL
- Opisz obudowę: *„IP54, montaż na szynę DIN, otwory USB-C"*
- AI generuje kod trimesh/CadQuery, wykonuje w sandboxie, pokazuje podgląd

### Przeglądarka PCB 2D / 3D
- Render 2D — QPainter, wszystkie warstwy KiCad z kolorami, zoom/pan
- Render 3D — Three.js w WebEngine lub soft-renderer QPainter

### Schemat
- Parser `.kicad_sch` (KiCad 6/7/8)
- Podgląd symboli, sieci, oznaczeń z renderem QPainter

### BOM — Lista komponentów
- Grupowanie (wartość + footprint), eksport CSV / Excel / HTML / PDF
- **LCSC CSV** — gotowy do zamówienia SMT na JLCPCB
- Klik w BOM → highlight komponentu na edytorze PCB
- AI: analiza, zamienniki, szacowanie kosztów, sprawdzenie braków

### Generator kodu MCU
- Arduino (`.ino`), MicroPython (`.py`), C++/ESP-IDF (`.cpp`)
- Automatyczna detekcja: ESP32, BME280, SSD1306, NeoPixel, MPU-6050, …
- Szablony Jinja2 z importami, inicjalizacją i przykładową pętlą

### STL / STEP — Generator obudów
- Generacja obudowy (dno + wieko) dopasowanej do PCB
- Automatyczne otwory na złącza (USB-C, DC Jack, JST, przyciski)
- Eksport `.stl` + `.step` (CadQuery opcjonalnie)
- Wbudowana przeglądarka 3D

### Eksport produkcyjny
- **Gerber + Drill** (Ctrl+G)
- **JLCPCB/PCBWay ZIP** (Ctrl+Shift+G) — Gerber + BOM CSV + CPL CSV
- **Netlist CSV** — per pad (Net, Component, Pin, X_mm, Y_mm)
- **Netlist KiCad (.net)** — bracket notation
- **PDF** — BOM, kosztorys, pełny raport projektu (Ctrl+P)

### Walidacja DRC
- DRC: szerokość ścieżek, prześwity, przelotki, zduplikowane refy, otwór, strefy
- STL: grubość ścianek, kąty nawisu, manifold geometry
- Wyjaśnienia AI: *„Wyjaśnij błąd"* / *„Plan naprawy krok po kroku"*
- Błędy widoczne bezpośrednio na edytorze PCB

### Trasowanie AI
- Sugestie rozmieszczenia + routingu generowane przez Ollama
- Zintegrowany DRC po trasowaniu

### Koszty
- Kosztorys z bazą LCSC, waluta USD/PLN/EUR, ilość szt.
- Eksport PDF / CSV

### Net Inspector
- Drzewo sieci elektrycznych z liczbą komponentów i padów
- Statystyki sieci, klik → highlight w edytorze PCB
- AI analiza sieci

### AI Asystent (RAG)
- Lokalny LLM przez Ollama (Llama 3, Mistral, CodeLlama, Qwen2)
- Baza wiedzy PCB/STL aktualizowana z GitHub i stron spec
- Nauka z URL / PDF / wklejonego tekstu

### Chmura / Git
- Push/pull GitHub (token PAT)
- Sync z Google Drive (OAuth2)
- Lokalny serwer projektów (Flask REST API)

### Autosave
- Automatyczny zapis co 5 minut (konfigurowalne) do `~/.electrovision_autosave/`
- Status Ollama w pasku statusu (🟢 / 🔴)

---

## Skróty klawiszowe

| Skrót | Akcja |
|---|---|
| `Ctrl+O` | Importuj KiCad PCB |
| `Ctrl+S` | Zapisz projekt |
| `Ctrl+P` | Eksport PDF |
| `Ctrl+G` | Gerber + Drill |
| `Ctrl+Shift+G` | JLCPCB ZIP |
| `Ctrl+K` | Kalkulator elektroniczny |
| `Ctrl+Shift+W` | Analiza zasilania |
| `Ctrl+Shift+T` | Estymacja termiczna |
| `Ctrl+Shift+L` | Edytor stackupu |
| `Ctrl+F` | Wyszukaj komponent |
| `Ctrl+,` | Ustawienia |
| `Alt+1–9` | Przełącz zakładki |
| `S` | Tryb Wybierz |
| `R` | Tryb Trasuj |
| `V` | Przelotka |
| `X` | Usuń |
| `Z` | Strefa miedzi |
| `T` | Narzędzie pomiaru |
| `Space` | Obróć komponent |
| `M` | Mirror (odbicie) |
| `F` | Dopasuj widok |
| `Ctrl+D` | Duplikuj komponent |
| `Ctrl+Z/Y` | Cofnij / Ponów |

---

## Struktura projektu

```
ElectroVision/
├── main.py                     # Punkt wejścia
├── start.bat                   # Jednoklikowe uruchomienie (Windows)
├── requirements.txt
├── src/
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── dialogs/
│   │   │   ├── ai_project_dialog.py
│   │   │   ├── ai_stl_dialog.py
│   │   │   ├── component_props_dialog.py
│   │   │   ├── component_search_dialog.py  # Wyszukiwarka komponentów + sklepy
│   │   │   ├── electronics_calc_dialog.py  # Kalkulator (microstrip, IPC-2221, RC, …)
│   │   │   ├── power_analysis_dialog.py    # Analiza zasilania
│   │   │   ├── thermal_dialog.py           # Estymacja termiczna T_j
│   │   │   ├── signal_analysis_dialog.py   # SI: propagacja, crosstalk, via
│   │   │   ├── stackup_editor_dialog.py    # Edytor stosu warstw + Z0
│   │   │   ├── settings_dialog.py
│   │   │   └── template_dialog.py
│   │   ├── panels/
│   │   │   ├── pcb_editor_panel.py         # Edytor + właściwości + historia
│   │   │   ├── bom_panel.py
│   │   │   ├── validation_panel.py
│   │   │   ├── net_inspector_panel.py
│   │   │   ├── cost_panel.py
│   │   │   ├── routing_panel.py
│   │   │   └── ...
│   │   └── widgets/
│   │       ├── pcb_editor.py               # Canvas QPainter — tryby, undo, DRC overlay
│   │       └── ...
│   ├── generators/
│   │   ├── jlcpcb_generator.py             # JLCPCB ZIP (Gerber + BOM + CPL)
│   │   ├── netlist_generator.py            # CSV + KiCad .net
│   │   ├── gerber_generator.py
│   │   ├── pdf_generator.py
│   │   └── ...
│   ├── validators/
│   │   ├── pcb_drc.py
│   │   └── stl_validator.py
│   └── ai/
│       ├── bridge.py
│       └── ...
└── tests/
```

---

## Konfiguracja AI (Ollama)

```bash
ollama serve
ollama pull llama3        # domyślny
ollama pull codellama     # lepszy do kodu
ollama pull qwen2         # alternatywa
```

W aplikacji: **Ctrl+,** → AI/Ollama → model/host.

---

## Zależności

| Biblioteka | Cel |
|---|---|
| `PySide6>=6.8` | GUI Qt6 |
| `sexpdata` | Parser KiCad |
| `trimesh + numpy` | STL generator |
| `Jinja2` | Szablony kodu MCU |
| `pandas + openpyxl` | BOM Excel |
| `ollama` | Lokalny AI client |
| `flask` | Serwer projektów |
| `reportlab` | Eksport PDF |

> CadQuery — opcjonalnie (STEP export).  
> PySide6-WebEngine — opcjonalnie (3D Three.js renderer).

---

## Testy

```bash
pytest tests/ -v
```
