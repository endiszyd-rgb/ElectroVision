# ElectroVision AI — Materiały treningowe (RAG)

Ten folder zawiera wiedzę techniczną dla lokalnego systemu AI.

## Struktura

```
training_data/
├── Modelfile              ← Ollama Modelfile (custom model "electrovision")
├── build_rag.py           ← Skrypt budujący indeks RAG
├── README.md              ← Ten plik
├── pcb/
│   ├── pcb_design_rules.md    ← Reguły projektowania PCB (IPC-2221)
│   └── kicad_from_docs.md     ← Dane z dokumentacji KiCad 8.0
├── stl/
│   ├── stl_fdm_design_guide.md    ← Przewodnik FDM, materiały, tolerancje
│   └── cadquery_api_reference.md  ← Kompletne API CadQuery z przykładami
├── code/
│   ├── arduino_reference.md       ← Arduino Language Reference + biblioteki
│   └── esp32_idf_reference.md     ← ESP-IDF GPIO, I2C, FreeRTOS, WiFi
└── qa_pairs/
    └── pcb_qa.jsonl               ← Pary Q&A do fine-tuningu (opcjonalne)
```

## Jak to działa

### RAG (Retrieval Augmented Generation)
1. Pliki .md są dzielone na fragmenty (~400 słów)
2. Każdy fragment jest przekształcany w wektor embeddings (sentence-transformers)
3. Przy każdym pytaniu: AI szuka TOP-5 najpassujących fragmentów
4. Fragmenty są wstrzykiwane do promptu → Ollama ma kontekst

### Pierwsze uruchomienie
```bash
pip install sentence-transformers numpy
python training_data/build_rag.py
```

### Tworzenie modelu Ollama "electrovision"
```bash
ollama pull llama3        # pobierz bazowy model
ollama create electrovision -f training_data/Modelfile
ollama run electrovision
```
W ElectroVision: AI → Wybierz model → wpisz "electrovision"

## Dodawanie własnej wiedzy

Dodaj plik .txt lub .md do dowolnego podkatalogu, np.:
```
training_data/pcb/moj_projekt_pcb.md
training_data/code/wzorce_freertos.md
```
Następnie odbuduj indeks:
```bash
python training_data/build_rag.py
```

## Format Q&A do fine-tuningu (zaawansowane)

Plik `qa_pairs/pcb_qa.jsonl` zawiera pary pytanie-odpowiedź w formacie JSONL:
```json
{"instruction": "Pytanie...", "response": "Odpowiedź..."}
```

Do fine-tuningu potrzeba GPU (min 8GB VRAM) i narzędzi jak:
- Unsloth: https://github.com/unslothai/unsloth
- LLaMA Factory: https://github.com/hiyouga/LLaMA-Factory

## Statystyki bazy wiedzy

| Plik | Szacowane chunki | Domena |
|---|---|---|
| pcb_design_rules.md | ~45 | PCB |
| kicad_from_docs.md | ~20 | PCB |
| stl_fdm_design_guide.md | ~50 | STL |
| cadquery_api_reference.md | ~40 | STL |
| arduino_reference.md | ~45 | Code |
| esp32_idf_reference.md | ~50 | Code |
| pcb_system.txt (prompt) | ~80 | PCB |
| stl_system.txt (prompt) | ~30 | STL |
| code_system.txt (prompt) | ~25 | Code |
| **RAZEM** | **~385 chunków** | Wszystkie |
