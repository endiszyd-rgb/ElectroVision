"""STL Agent — specjalizowany agent do projektowania obudów 3D."""
from __future__ import annotations
import json
from typing import Callable

from src.ai.agents.base_agent import BaseAgent


class STLAgent(BaseAgent):
    DOMAIN     = "stl"
    SYSTEM_KEY = "stl_system"
    RAG_CHUNKS = 6

    def design_enclosure(self, params: dict, board=None, on_chunk=None, on_done=None, on_error=None) -> None:
        board_info = ""
        if board:
            connectors = [c for c in board.components if c.component_type == "connector"]
            board_info = (
                f"PCB: {board.width_mm:.1f} × {board.height_mm:.1f} mm\n"
                f"Grubość PCB: {params.get('pcb_thickness', 1.6)} mm\n"
                f"Złącza ({len(connectors)}): {', '.join(c.reference + ':' + c.value for c in connectors[:8])}\n"
                f"Liczba komponentów: {len(board.components)}\n"
                f"Najwyższy komponent (szacunek): ~15mm"
            )
        prompt = (
            f"Zaprojektuj obudowę 3D dla płytki:\n{board_info}\n\n"
            f"Parametry:\n{json.dumps(params, ensure_ascii=False, indent=2)}\n\n"
            "Podaj:\n"
            "1. Zewnętrzne wymiary obudowy (dł × szer × wys)\n"
            "2. Pozycje i rozmiary otworów na złącza (od lewej krawędzi, od dołu)\n"
            "3. System mocowania PCB (standoffs: pozycja, średnica, wysokość)\n"
            "4. Projekt wieka (snap-fit: wymiary, lub śruby M3: pozycje)\n"
            "5. Zalecenia druku 3D: materiał, wypełnienie, temperatura, podpory\n"
            "6. Kod CadQuery (Python) do wygenerowania głównej bryły obudowy\n\n"
            "Kod CadQuery musi być kompletny i wykonywalny — użyj `import cadquery as cq`."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def from_description(self, description: str, board=None, on_chunk=None, on_done=None, on_error=None) -> None:
        board_info = ""
        if board:
            board_info = f"PCB {board.width_mm:.0f}×{board.height_mm:.0f}mm, {len(board.components)} komponentów. "
        prompt = (
            f"Użytkownik opisuje obudowę: '{description}'\n"
            f"{board_info}\n"
            "Na podstawie opisu:\n"
            "1. Przetłumacz na konkretne parametry (mm, materiał, kolor, typ mocowania)\n"
            "2. Podaj wymiary zewnętrzne obudowy\n"
            "3. Pozycje i rozmiary wszystkich otworów\n"
            "4. Wygeneruj kompletny kod CadQuery\n"
            "5. Lista plików do wydruku (obudowa.stl, wieko.stl)\n"
            "6. Zalecenia slicera (Cura/PrusaSlicer): layer height, infill%, supporty"
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def validate_geometry(self, stl_path: str, issues: list, on_chunk=None, on_done=None, on_error=None) -> None:
        issues_text = "\n".join(f"- [{i['severity'].upper()}] {i['message']}" for i in issues)
        prompt = (
            f"Analiza problemów geometrycznych pliku STL:\n{issues_text}\n\n"
            "Dla każdego problemu:\n"
            "1. Co oznacza (przyczyna techniczna)\n"
            "2. Jak naprawić w Meshmixer / Blender / Fusion 360\n"
            "3. Czy plik nadaje się do druku 3D mimo błędu?\n"
            "4. Jak zapobiec w przyszłości (CadQuery tip)"
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def generate_cadquery(self, description: str, on_chunk=None, on_done=None, on_error=None) -> None:
        prompt = (
            f"Napisz kompletny, wykonywalny kod CadQuery (Python) dla:\n{description}\n\n"
            "Wymagania:\n"
            "- import cadquery as cq\n"
            "- Parametry jako zmienne na początku (łatwa edycja)\n"
            "- Eksport do STEP: result.val().exportStep('output.step')\n"
            "- Eksport do STL: cq.exporters.export(result, 'output.stl')\n"
            "- Komentarze przy każdej operacji\n"
            "- Obsługa standoffów, wycięć na złącza, zaokrągleń\n\n"
            "Kod musi być gotowy do skopiowania i uruchomienia."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)
