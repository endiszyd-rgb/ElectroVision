"""PCB Agent — specjalizowany agent do analizy i projektowania PCB."""
from __future__ import annotations
import json
from typing import Callable

from src.ai.agents.base_agent import BaseAgent


class PCBAgent(BaseAgent):
    DOMAIN     = "pcb"
    SYSTEM_KEY = "pcb_system"
    RAG_CHUNKS = 8

    def analyze_board(self, board, on_chunk=None, on_done=None, on_error=None) -> None:
        types: dict = {}
        for c in board.components:
            types[c.component_type] = types.get(c.component_type, 0) + 1
        nets_power = [n.name for n in board.nets if any(p in n.name.upper() for p in ("VCC","VDD","GND","3V3","5V","12V","PWR"))]

        prompt = (
            f"Kompleksowa analiza projektu PCB:\n"
            f"Wymiary: {board.width_mm:.1f} × {board.height_mm:.1f} mm\n"
            f"Komponenty: {json.dumps(types, ensure_ascii=False)}\n"
            f"Ścieżki: {len(board.traces)}, Przelotki: {len(board.vias)}, Sieci: {len(board.nets)}\n"
            f"Sieci zasilania: {', '.join(nets_power[:10])}\n\n"
            "Oceń:\n"
            "1. Co to za projekt (funkcja układu)?\n"
            "2. Problemy z zasilaniem i filtrowaniem (brakujące kondensatory?)\n"
            "3. Ryzyko EMI/EMC (pętle, kryształy, RF)\n"
            "4. Rekomendacje stackupu warstw\n"
            "5. Krytyczne miejsca routingu\n"
            "6. Proponowane ulepszenia BOM"
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def suggest_routing(self, board, on_chunk=None, on_done=None, on_error=None) -> None:
        prompt = (
            f"Zaproponuj strategię routingu dla płytki {board.width_mm:.0f}×{board.height_mm:.0f}mm "
            f"z {len(board.components)} komponentami i {len(board.nets)} sieciami.\n\n"
            "Podaj: priorytety grup sygnałów, impedancję, separację analog/cyfrowy, "
            "plane fill, via stitching, szerokości ścieżek zasilania."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def check_power_supply(self, board, on_chunk=None, on_done=None, on_error=None) -> None:
        caps = [c for c in board.components if c.component_type == "capacitor"]
        ics  = [c for c in board.components if c.component_type == "ic"]
        regs = [c for c in board.components if any(kw in c.value.upper() for kw in ("AMS","LM78","LDO","BUCK","REG","7805","1117","MP2"))]
        prompt = (
            f"Analiza zasilania:\n"
            f"Regulatory: {[c.value for c in regs]}\n"
            f"IC do zasilania: {len(ics)} układów\n"
            f"Kondensatory: {len(caps)} szt.\n"
            f"Stosunek: {len(caps)/max(len(ics),1):.1f} kondensatora na IC (norma: ≥2)\n\n"
            "Oceń: czy jest wystarczające filtrowanie? Jakie kondensatory dodać i gdzie?"
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def explain_component(self, component, on_chunk=None, on_done=None, on_error=None) -> None:
        pads = ", ".join(f"P{p.number}={p.net_name}" for p in component.pads[:8] if p.net_name)
        prompt = (
            f"Wyjaśnij komponent: {component.reference} — {component.value}\n"
            f"Typ: {component.component_type}, Footprint: {component.footprint}\n"
            f"Pozycja: X={component.x:.2f} Y={component.y:.2f} mm, warstwa: {component.layer}\n"
            f"Pady i sieci: {pads}\n\n"
            "Podaj: funkcja w układzie, sposób podłączenia, pull-up/down, kod init, częste błędy."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def explain_drc(self, issues: list, on_chunk=None, on_done=None, on_error=None) -> None:
        text = "\n".join(
            f"[{i.get('severity','?').upper()}] {i.get('position','')} — {i.get('message','')} | {i.get('suggestion','')}"
            for i in issues[:25]
        )
        prompt = (
            f"Analizuj błędy DRC i podaj priorytetowy plan naprawy:\n\n{text}\n\n"
            "Dla każdego: dlaczego ważny → jak naprawić w KiCad → priorytet (krytyczny/ważny/info)."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)
