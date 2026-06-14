# ElectroVision

Desktopowa aplikacja do projektowania elektroniki PCB z lokalnym AI, wizualizacją 3D, generatorem kodu i eksportem STL/STEP.

## Wymagania

- Python 3.10+
- [Ollama](https://ollama.ai) (dla AI) — `ollama serve` + `ollama pull llama3`
- KiCad (opcjonalnie, do edycji PCB)
- Fusion 360 (opcjonalnie, do edycji STEP/STL)
- Arduino IDE (opcjonalnie, do wgrywania kodu)

## Instalacja

```bash
pip install -r requirements.txt
python main.py
```

## Moduły i możliwości konfiguracji

### `src/core/models/` — Modele danych

| Plik | Co zmienić |
|------|------------|
| `component.py` | `component_type` — reguły rozpoznawania typu komponentu wg prefixu ref |
| `pcb_board.py` | `bounding_box` — logika obliczania granic płytki |
| `layer.py` | `kicad_layers()` — lista standardowych warstw KiCad |

### `src/core/parsers/kicad_parser.py` — Parser KiCad

Parsuje pliki `.kicad_pcb` (format S-expression KiCad 6/7/8).

**Co można zmienić:**
- `MIN_TRACE_WIDTH_MM` — minimalna szerokość ścieżki (domyślnie 0.1mm)
- `_parse_footprints()` — rozszerzenie o dodatkowe właściwości footprintu
- Obsługa KiCad 5: format S-expression starszy, wymaga drobnych zmian

### `src/generators/bom_generator.py` — Eksport BOM

**Co można zmienić:**
- `group_components()` — logika grupowania (wg wartości + footprintu)
- `to_excel()` — style arkusza (kolory, czcionki, nagłówki)
- Dodanie nowych formatów (np. HTML, JSON, Mouser/Digi-Key BOM)

### `src/generators/code_generator.py` — Generator kodu Arduino/MicroPython/C++

**Co można zmienić:**
- `_COMPONENT_KNOWLEDGE` — biblioteki i kod init/loop dla każdego typu komponentu
- `_VALUE_OVERRIDES` — mapowanie nazwy wartości → konkretne biblioteki (np. "bme280" → Adafruit_BME280)
- `_ARDUINO_TEMPLATE`, `_MICROPYTHON_TEMPLATE`, `_CPP_TEMPLATE` — szablony Jinja2 kodu
- Dodanie nowych platform (PlatformIO, Zephyr RTOS, Arduino ESP8266)

### `src/generators/stl_generator.py` — Generator STL + STEP

**Co można zmienić:**
- `pcb_thickness` — grubość FR4 (domyślnie 1.6mm)
- `enclosure_margin` — margines obudowy od krawędzi PCB (domyślnie 3mm)
- `wall_thickness` — grubość ścianek (domyślnie 2.0mm)
- `corner_radius` — zaokrąglenie narożników (domyślnie 2.0mm)
- `_make_enclosure()` — geometria głównej obudowy (CadQuery)
- `_make_lid()` — geometria wieka obudowy
- `_export_stl_trimesh()` — fallback gdy CadQuery niedostępne

### `src/validators/pcb_drc.py` — Walidator PCB (DRC)

**Co można zmienić:**
- `MIN_TRACE_WIDTH_MM = 0.1` — minimalna szerokość ścieżki
- `MIN_CLEARANCE_MM = 0.1` — minimalny prześwit między ścieżkami
- `MIN_EDGE_CLEARANCE = 0.3` — prześwit od krawędzi płytki
- `MIN_VIA_DRILL_MM = 0.2` — minimalny otwór przelotki
- `MIN_VIA_ANNULAR_MM = 0.1` — minimalny pierścień anularny
- Dodanie nowych reguł w metodach `_check_*`

### `src/validators/stl_validator.py` — Walidator STL/STEP

**Co można zmienić:**
- `MIN_WALL_THICKNESS_MM = 0.8` — minimalna grubość ścianki
- `MAX_OVERHANG_ANGLE = 60.0` — maksymalny kąt nawisu
- `MAX_FILE_SIZE_MB = 500` — ostrzeżenie o dużym pliku

### `src/ai/prompts/` — Systemowe prompty dla AI (Ollama)

| Plik | Zastosowanie |
|------|-------------|
| `pcb_system.txt` | Kontekst AI dla projektowania PCB |
| `stl_system.txt` | Kontekst AI dla projektowania obudów |
| `code_system.txt` | Kontekst AI dla generowania kodu |

**Jak dostosować:** Edytuj pliki `.txt` aby zmienić wiedzę i styl odpowiedzi AI. Możesz dodać własne reguły, preferowane komponenty, specyficzne standardy firmy.

### `src/ai/knowledge/fetcher.py` — Baza wiedzy

**Co można zmienić:**
- `_BUILTIN_COMPONENT_DB` — wbudowana baza komponentów (MCU, sensory, wyświetlacze)
- `_SOURCES` — źródła internetowe do pobrania (GitHub repos, listy bibliotek)
- `fetch_all()` — logika aktualizacji bazy wiedzy

### `src/cloud/github/client.py` — Integracja GitHub

**Konfiguracja:**
- Token GitHub Personal Access Token (Settings → Developer Settings → Personal Access Tokens)
- Zakres uprawnień: `repo` (prywatne repozytoria)

### `src/cloud/gdrive/client.py` — Integracja Google Drive

**Konfiguracja:**
1. Google Cloud Console → New Project → Enable Drive API
2. Create OAuth2 credentials (Desktop app) → pobierz `credentials.json`
3. Umieść w `%USERPROFILE%\.electrovision\gdrive_credentials.json`

### `server/app.py` — Serwer projektów (Flask)

**Konfiguracja:**
- `EV_SERVER_HOST` — env var, adres nasłuchiwania (domyślnie `0.0.0.0`)
- `EV_SERVER_PORT` — env var, port (domyślnie `8765`)
- `STORAGE_DIR` — folder przechowywania projektów

**Uruchomienie:**
```bash
python -m server.app
# lub przez GUI: panel Chmura → Uruchom serwer lokalny
```

## Struktura folderów

```
ElectroVision/
├── main.py                    # Punkt wejścia
├── requirements.txt           # Zależności Python
├── pyproject.toml             # Metadane projektu
├── server/                    # Serwer projektów (Flask)
│   ├── app.py                 # REST API
│   └── storage/               # Dane przechowywane lokalnie
├── assets/
│   └── templates/             # Szablony Jinja2 kodu (arduino/micropython/c_cpp)
├── src/
│   ├── app.py                 # QApplication + dark theme
│   ├── ui/
│   │   ├── main_window.py     # Główne okno, menu, zakładki
│   │   ├── panels/            # Panele zakładek
│   │   └── widgets/           # Widgety (2D PCB view, 3D WebEngine view, tabela BOM)
│   ├── core/
│   │   ├── models/            # Modele danych (PCBBoard, Component, Layer, Net)
│   │   └── parsers/           # Parser KiCad
│   ├── generators/            # Generatory (BOM, kod, STL+STEP)
│   ├── validators/            # Walidatory (PCB DRC, STL geometry)
│   ├── ai/
│   │   ├── prompts/           # Systemowe prompty dla Ollama
│   │   └── knowledge/         # Baza wiedzy PCB/STL + data fetcher
│   └── cloud/
│       ├── github/            # GitHub API client
│       ├── gdrive/            # Google Drive client
│       └── server/            # Client dla ElectroVision Server
└── tests/                     # Testy pytest
```

## Uruchomienie testów

```bash
pytest tests/ -v
```

## Zależności zewnętrzne

| Biblioteka | Cel | Instalacja |
|-----------|-----|-----------|
| PySide6 | GUI Qt6 | pip install PySide6 |
| sexpdata | Parser S-expression (KiCad) | pip install sexpdata |
| cadquery | Generator 3D STEP/STL | pip install cadquery |
| trimesh | Fallback STL + walidacja | pip install trimesh |
| Jinja2 | Szablony kodu | pip install Jinja2 |
| pandas + openpyxl | BOM Excel | pip install pandas openpyxl |
| ollama | Lokalny AI client | pip install ollama |
| Flask | Serwer projektów | pip install flask |
| PyGithub | GitHub integration | pip install PyGithub |
| google-api-python-client | Google Drive | pip install google-api-python-client google-auth-oauthlib |
