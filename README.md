# ElectroVision

Desktopowa aplikacja do projektowania elektroniki PCB z lokalnym AI (Ollama), interaktywnym edytorem płytki, wizualizacją 3D, generatorem kodu MCU i eksportem STL/STEP obudów.

---

## Szybki start

```bash
# Jednoklikowe uruchomienie (Windows) — instaluje venv, deps, uruchamia Ollama + aplikację
start.bat

# Lub ręcznie:
pip install -r requirements.txt
python main.py
```

Wymaga:
- **Python 3.10+** (zalecany 3.11 lub 3.12)
- **[Ollama](https://ollama.ai)** — `ollama serve` + `ollama pull llama3`

Opcjonalnie:
- KiCad 7/8 — import/eksport `.kicad_pcb` / `.kicad_sch`
- PrusaSlicer / Cura — otwieranie wygenerowanych plików STL
- Arduino IDE — wgrywanie wygenerowanego kodu

---

## Możliwości

### Edytor PCB (interaktywny)
- Tryby: **Wybierz / Trasuj / Przelotka / Usuń / Strefa miedzi / Umieść komponent**
- Skróty: `S` Wybierz · `R` Trasuj · `V` Przelotka · `X` Usuń · `Z` Strefa · `N` Ratsnest · `Space` Obróć · `M` Lustro · `F` Dopasuj widok · `Ctrl+Z/Y` Cofnij/Ponów
- Widoczność warstw (checkboxy per warstwa + „Wszystkie" / „Tylko Cu")
- Ratsnest (brakujące połączenia) z przełącznikiem
- Strefy miedzi (copper pour) z obsługą sieci
- Znajdź komponent: **Ctrl+F** → pole wyszukiwania + lista
- **Dwuklik na komponent → dialog właściwości** (ref, wartość, footprint, XY, rotacja, warstwa)
- **Nakładka DRC** — po walidacji błędy wyświetlają się jako czerwone X bezpośrednio na płytce
- Biblioteka komponentów (rezystory, kondensatory, LED, złącza, MCU, tranzystory, kryształy)
- Wyrównanie i rozmieszenie komponentów
- Eksport do `.kicad_pcb`

### AI — Generator projektu PCB
- Opisz słowami: *„Sterownik silnika DC 12V, ESP32, zabezpieczenie przetężeniowe, 4 enkodery"*
- AI (Ollama) generuje projekt z komponentami, sieciami i układem — gotowy do edycji

### AI — Designer obudowy STL/STEP
- Opisz obudowę: *„IP54, montaż na szynę DIN, otwory USB-C i DC jack"*
- AI generuje kod Python (trimesh/CadQuery), wykonuje go w sandboxie, pokazuje podgląd STL
- 6 wbudowanych szablonów: standardowa drukowana, IP65 zewnętrzna, szyna DIN, rack 1U i inne

### Przeglądarka PCB 2D / 3D
- Render 2D — QPainter, wszystkie warstwy KiCad z kolorami, zoom/pan
- Render 3D — Three.js w WebEngine **lub** soft-renderer QPainter (bez WebEngine)

### Schemat
- Parser `.kicad_sch` (KiCad 6/7/8)
- Podgląd symboli, sieci, oznaczeń

### BOM — Lista komponentów
- Grupowanie (wartość + footprint), eksport CSV / Excel / PDF
- Filtrowanie po typie

### Generator kodu MCU
- Arduino (`.ino`), MicroPython (`.py`), C++/ESP-IDF (`.cpp`)
- Automatyczna detekcja komponentów (ESP32, BME280, SSD1306, NeoPixel, …)
- Szablony Jinja2 z importami, inicjalizacją i przykładowym pętlą

### STL / STEP — Generator obudów
- Generacja obudowy (dno + wieko) dopasowanej do PCB
- Automatyczne otwory na złącza (USB-C, DC Jack, JST, przyciski)
- Wysokość obudowy z bazy danych komponentów (50+ typów)
- Eksport `.stl` (trimesh) + `.step` (CadQuery gdy dostępny)
- Przeglądarka 3D wbudowana (WebEngine lub soft-renderer)

### Walidacja DRC + STL
- DRC: szerokość ścieżek, prześwity, przelotki, zduplikowane refy, otwór, strefy
- STL: grubość ścianek, kąty nawisu, manifold geometry
- Wyjaśnienia AI: *„Wyjaśnij błąd"* / *„Plan naprawy krok po kroku"*
- **Błędy DRC widoczne bezpośrednio na edytorze PCB** (czerwone X z opisem)

### Trasowanie AI
- Sugestie rozmieszczenia + routingu generowane przez Ollama
- Zintegrowany DRC po trasowaniu

### Koszty
- Kosztorys komponentów z bazą LCSC
- Eksport PDF raportu kosztów

### Net Inspector
- Wizualizacja połączeń sieciowych
- Klik na sieć → highlight ścieżek i komponentów w edytorze

### AI Asystent (RAG)
- Lokalny LLM przez Ollama (Llama 3, Mistral, CodeLlama, Qwen2)
- Baza wiedzy PCB/STL aktualizowana z GitHub i stron spec
- Nauka z URL / PDF / wklejonego tekstu
- Kontekst projektu (rozmiary płytki, komponenty) przekazywany automatycznie

### Chmura / Git
- Push/pull GitHub (token PAT)
- Sync z Google Drive (OAuth2)
- Lokalny serwer projektów (Flask REST API)

### Ustawienia (Ctrl+,)
- Model Ollama, host, timeout
- Progi DRC (szerokość ścieżek, prześwity, przelotki)
- Domyślne parametry edytora (szerokość ścieżki, siatka, via)
- Motyw, język, autosave

---

## Struktura projektu

```
ElectroVision/
├── main.py                     # Punkt wejścia
├── start.bat                   # Jednoklikowe uruchomienie (Windows)
├── requirements.txt
├── src/
│   ├── app.py                  # QApplication + dark theme
│   ├── ui/
│   │   ├── main_window.py      # Główne okno, menu, zakładki, Ollama indicator
│   │   ├── dialogs/
│   │   │   ├── ai_project_dialog.py      # AI PCB generator
│   │   │   ├── ai_stl_dialog.py          # AI STL designer
│   │   │   ├── component_props_dialog.py # Edycja właściwości komponentu
│   │   │   ├── settings_dialog.py        # Ustawienia aplikacji
│   │   │   ├── template_dialog.py        # Wybór szablonu projektu
│   │   │   └── ollama_error_dialog.py    # Diagnostyka Ollama
│   │   ├── panels/
│   │   │   ├── pcb_editor_panel.py       # Edytor PCB + panel warstw/find
│   │   │   ├── pcb_viewer_panel.py       # Przeglądarka 2D/3D
│   │   │   ├── bom_panel.py
│   │   │   ├── code_gen_panel.py
│   │   │   ├── stl_gen_panel.py          # Generator STL + AI Designer
│   │   │   ├── schematic_panel.py
│   │   │   ├── routing_panel.py
│   │   │   ├── cost_panel.py
│   │   │   ├── net_inspector_panel.py
│   │   │   ├── validation_panel.py
│   │   │   ├── components_panel.py
│   │   │   ├── ai_panel.py
│   │   │   ├── cloud_panel.py
│   │   │   └── url_learning_panel.py
│   │   └── widgets/
│   │       ├── pcb_editor.py             # Canvas edytora PCB (QPainter)
│   │       ├── pcb_2d_view.py
│   │       ├── pcb_3d_view.py            # Three.js lub soft-renderer
│   │       ├── stl_3d_view.py            # STL przeglądarka
│   │       └── component_table.py
│   ├── core/
│   │   ├── models/             # PCBBoard, Component, Layer, Net, CopperZone
│   │   ├── parsers/            # KiCad PCB + schematic parser
│   │   ├── project.py
│   │   └── project_io.py       # Zapis/odczyt .evproj (JSON)
│   ├── generators/
│   │   ├── bom_generator.py
│   │   ├── code_generator.py
│   │   ├── stl_generator.py    # Obudowy STL/STEP z bazy komponentów
│   │   ├── gerber_generator.py # Gerber + Drill
│   │   ├── kicad_generator.py  # Eksport .kicad_pcb
│   │   └── pdf_generator.py    # Raporty PDF
│   ├── validators/
│   │   ├── pcb_drc.py          # DRC: ścieżki, prześwity, przelotki
│   │   └── stl_validator.py
│   ├── ai/
│   │   ├── bridge.py           # Fasada do Ollama
│   │   ├── ollama_utils.py     # is_ollama_running(), list_models()
│   │   ├── prompts/            # Systemowe prompty (.txt)
│   │   ├── knowledge/          # Baza wiedzy PCB/STL
│   │   ├── rag/                # Retrieval-Augmented Generation
│   │   └── agents/             # Agenci AI (PCB, STL, Kod)
│   └── cloud/
│       ├── github/
│       ├── gdrive/
│       └── server/             # REST client dla lokalnego serwera
└── tests/
```

---

## Konfiguracja AI (Ollama)

```bash
# Zainstaluj Ollama
# Windows: https://ollama.ai → Download
ollama serve
ollama pull llama3        # domyślny model
# opcjonalnie:
ollama pull codellama     # lepszy do generowania kodu
ollama pull qwen2         # alternatywa
```

W aplikacji: **Ctrl+,** → zakładka AI/Ollama → zmień model/host.

Status Ollama widoczny w pasku statusu (🟢 / 🔴).

---

## Format projektu (.evproj)

Plik JSON zawierający:
- Metadane projektu (nazwa, data, wersja)
- `board` — pełna struktura PCBBoard (komponenty, ścieżki, przelotki, warstwy, sieci, strefy miedzi)

Eksport dodatkowy: Gerber (`Ctrl+G`), PDF raport (`Ctrl+P`), `.kicad_pcb`.

---

## Zależności

| Biblioteka | Cel |
|-----------|-----|
| `PySide6>=6.8` | GUI Qt6 |
| `sexpdata` | Parser KiCad S-expression |
| `trimesh + numpy` | STL generator + przeglądarka |
| `Jinja2` | Szablony kodu MCU |
| `pandas + openpyxl` | BOM Excel |
| `ollama` | Lokalny AI client |
| `flask` | Serwer projektów |
| `PyGithub` | GitHub API |
| `google-api-python-client` | Google Drive |
| `reportlab` | Eksport PDF |

> CadQuery (`cadquery>=2.4`) — opcjonalnie (Python ≤3.12), dla eksportu STEP.  
> PySide6-WebEngine — opcjonalnie, dla renderera 3D Three.js (Python ≤3.12).

---

## Testy

```bash
pytest tests/ -v
```

---

## Licencja

MIT
