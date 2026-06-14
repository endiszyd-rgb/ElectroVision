"""
AIBridge — centralny interfejs AI dla wszystkich modułów ElectroVision.

Każdy panel/generator/walidator używa AIBridge zamiast bezpośrednio wywoływać Ollama.
Bridge zapewnia:
- Spójny kontekst projektu wstrzykiwany do każdego promptu
- Streaming odpowiedzi przez QThread + Signal
- Fallback gdy Ollama niedostępne
- Cache ostatnich odpowiedzi
- Logowanie rozmów (historia na sesję)
"""
from __future__ import annotations

import json
from typing import Callable, Optional
from PySide6.QtCore import QObject, QThread, Signal, Slot


class AIStreamWorker(QObject):
    """Executes a streaming Ollama call in a background thread."""
    chunk    = Signal(str)
    finished = Signal(str)   # emits full accumulated text
    error    = Signal(str)

    def __init__(self, prompt: str, system: str, model: str, context: dict):
        super().__init__()
        self._prompt  = prompt
        self._system  = system
        self._model   = model
        self._context = context

    @Slot()
    def run(self) -> None:
        full = ""
        try:
            import ollama
            messages = []
            if self._system:
                messages.append({"role": "system", "content": self._system})
            if self._context:
                ctx_str = "## Kontekst projektu:\n" + json.dumps(self._context, ensure_ascii=False, indent=2)
                messages.append({"role": "system", "content": ctx_str})
            messages.append({"role": "user", "content": self._prompt})

            stream = ollama.chat(model=self._model, messages=messages, stream=True)
            for part in stream:
                text = part["message"]["content"]
                if text:
                    full += text
                    self.chunk.emit(text)
            self.finished.emit(full)
        except ImportError:
            msg = (
                "Brak biblioteki ollama.\n"
                "Zainstaluj: pip install ollama\n"
                "Następnie uruchom Ollama: https://ollama.ai"
            )
            self.error.emit(msg)
        except Exception as e:
            err = str(e)
            if "connection" in err.lower() or "refused" in err.lower():
                err = (
                    "Nie można połączyć z Ollama.\n"
                    "1. Pobierz: https://ollama.ai\n"
                    "2. Uruchom: ollama serve\n"
                    "3. Pobierz model: ollama pull llama3"
                )
            self.error.emit(err)


class AIBridge(QObject):
    """
    Singleton-like AI interface shared by all ElectroVision panels.

    Usage
    -----
    bridge = AIBridge.instance()
    bridge.set_model("llama3")
    bridge.set_project_context(board=board, project_name="MyPCB")

    # Async streaming (for UI):
    bridge.ask_async(
        prompt="Przeanalizuj tę płytkę",
        system_key="pcb_system",
        on_chunk=lambda t: text_edit.insertPlainText(t),
        on_done=lambda full: print("Done"),
        on_error=lambda e: print(e),
    )

    # Sync (for generators, validators):
    result = bridge.ask_sync("Zaproponuj obudowę", "stl_system")
    """

    _instance: Optional["AIBridge"] = None

    @classmethod
    def instance(cls) -> "AIBridge":
        if cls._instance is None:
            cls._instance = AIBridge()
        return cls._instance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model   = "llama3"
        self._context: dict = {}
        self._history: list[dict] = []
        self._thread: Optional[QThread] = None
        self._worker: Optional[AIStreamWorker] = None

    # ------------------------------------------------------------------ config

    def set_model(self, model: str) -> None:
        self._model = model

    def get_model(self) -> str:
        return self._model

    def set_project_context(
        self,
        project_name: str = "",
        board=None,
        stl_params: dict | None = None,
    ) -> None:
        ctx: dict = {"project": project_name}
        if board:
            ctx["pcb"] = {
                "width_mm":   round(board.width_mm, 2),
                "height_mm":  round(board.height_mm, 2),
                "components": len(board.components),
                "traces":     len(board.traces),
                "vias":       len(board.vias),
                "nets":       len(board.nets),
                "comp_list":  [
                    f"{c.reference}:{c.value}({c.component_type})"
                    for c in board.components[:30]
                ],
            }
        if stl_params:
            ctx["stl"] = stl_params
        self._context = ctx

    # ------------------------------------------------------------------ prompts

    def _load_system(self, key: str) -> str:
        try:
            from src.ai.prompts.loader import load_prompt
            return load_prompt(key)
        except Exception:
            return ""

    def _rag_context(self, prompt: str, domain: str = "") -> str:
        """Retrieve relevant knowledge chunks from local RAG database."""
        try:
            from src.ai.rag.knowledge_base import LocalKnowledgeBase
            kb = LocalKnowledgeBase.instance()
            if kb.is_ready:
                return kb.context_for_query(prompt, k=5, domain=domain, max_chars=2500)
        except Exception:
            pass
        return ""

    def _domain_for_key(self, key: str) -> str:
        return {"pcb_system": "pcb", "stl_system": "stl", "code_system": "code"}.get(key, "")

    # ------------------------------------------------------------------ async API

    def ask_async(
        self,
        prompt: str,
        system_key: str = "pcb_system",
        extra_system: str = "",
        on_chunk: Callable[[str], None] | None = None,
        on_done: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        use_rag: bool = True,
    ) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        system = self._load_system(system_key)
        rag_ctx = self._rag_context(prompt, self._domain_for_key(system_key)) if use_rag else ""
        if rag_ctx:
            system = f"{system}\n\n{rag_ctx}"
        if extra_system:
            system = f"{system}\n\n{extra_system}"

        self._worker = AIStreamWorker(prompt, system, self._model, self._context)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        if on_chunk:
            self._worker.chunk.connect(on_chunk)
        if on_done:
            self._worker.finished.connect(on_done)
            self._worker.finished.connect(lambda _: self._cleanup())
        else:
            self._worker.finished.connect(self._cleanup)
        if on_error:
            self._worker.error.connect(on_error)
            self._worker.error.connect(lambda _: self._cleanup())
        else:
            self._worker.error.connect(self._cleanup)

        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

    def _cleanup(self, *_) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ------------------------------------------------------------------ sync API (for non-UI callers)

    def ask_sync(self, prompt: str, system_key: str = "pcb_system", extra_system: str = "") -> str:
        """Blocking call — do NOT use from the GUI thread."""
        try:
            import ollama
            system = self._load_system(system_key)
            if extra_system:
                system = f"{system}\n\n{extra_system}"
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            if self._context:
                messages.append({"role": "system", "content": json.dumps(self._context, ensure_ascii=False)})
            messages.append({"role": "user", "content": prompt})
            resp = ollama.chat(model=self._model, messages=messages)
            return resp["message"]["content"]
        except Exception as e:
            return f"[AI niedostępne: {e}]"

    # ------------------------------------------------------------------ helpers for each module

    def analyze_bom(self, components: list, on_chunk=None, on_done=None, on_error=None) -> None:
        comp_text = "\n".join(
            f"- {c.reference}: {c.value} ({c.component_type}), fp={c.footprint.split(':')[-1]}"
            for c in components
        )
        prompt = (
            f"Przeanalizuj poniższą listę BOM:\n{comp_text}\n\n"
            "Wykonaj:\n"
            "1. Grupowanie komponentów według funkcji\n"
            "2. Identyfikacja potencjalnych problemów z dostępnością\n"
            "3. Propozycja tańszych zamienników dla drogich elementów\n"
            "4. Szacunkowy koszt (podaj widełki cenowe dla małych serii)\n"
            "5. Lista brakujących komponentów (filtrowanie, zabezpieczenia)\n"
            "6. Ocena kompletności projektu"
        )
        self.ask_async(prompt, "pcb_system", on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def improve_code(self, code: str, platform: str, mcu: str, on_chunk=None, on_done=None, on_error=None) -> None:
        prompt = (
            f"Przejrzyj i rozbuduj poniższy kod dla {platform} / {mcu}:\n\n"
            f"```\n{code[:3000]}\n```\n\n"
            "Wykonaj:\n"
            "1. Napraw wszelkie błędy i przeoczenia\n"
            "2. Dodaj obsługę błędów i timeouty\n"
            "3. Dodaj watchdog jeśli MCU to obsługuje\n"
            "4. Dodaj komentarze wyjaśniające kluczowe fragmenty\n"
            "5. Zaproponuj optymalizacje energetyczne (deep sleep, przerwania)\n"
            "6. Sprawdź poprawność inicjalizacji wszystkich peryferiów"
        )
        self.ask_async(prompt, "code_system", on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def design_enclosure(self, params: dict, board=None, on_chunk=None, on_done=None, on_error=None) -> None:
        board_info = ""
        if board:
            bb = board.bounding_box
            connectors = [c for c in board.components if c.component_type == "connector"]
            board_info = (
                f"Wymiary PCB: {board.width_mm:.1f} x {board.height_mm:.1f} mm\n"
                f"Grubość PCB: {params.get('pcb_thickness', 1.6)} mm\n"
                f"Złącza ({len(connectors)}): {', '.join(c.reference+':'+c.value for c in connectors[:8])}\n"
                f"Liczba komponentów: {len(board.components)}"
            )
        prompt = (
            f"Zaprojektuj obudowę 3D dla płytki PCB:\n{board_info}\n\n"
            f"Parametry użytkownika:\n{json.dumps(params, ensure_ascii=False, indent=2)}\n\n"
            "Podaj:\n"
            "1. Szczegółowe wymiary obudowy (dł x szer x wys) z marginesami\n"
            "2. Pozycje i wymiary otworów na wszystkie złącza\n"
            "3. Projekt systemu mocowania (standoffs, śruby, snap-fit)\n"
            "4. Szczegóły wieka (kołki, uchwyty, uszczelka)\n"
            "5. Zalecenia druku 3D (materiał, wypełnienie, temperatura, podpory)\n"
            "6. Pseudokod CadQuery do wygenerowania głównej bryły"
        )
        self.ask_async(prompt, "stl_system", on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def explain_drc_issues(self, issues: list, on_chunk=None, on_done=None, on_error=None) -> None:
        if not issues:
            if on_done:
                on_done("Brak błędów DRC do wyjaśnienia.")
            return
        issues_text = "\n".join(
            f"[{i.get('severity','?').upper()}] {i.get('position','')} — {i.get('message','')} | Sugestia: {i.get('suggestion','')}"
            for i in issues[:30]
        )
        prompt = (
            f"Przeanalizuj poniższe błędy DRC z projektu PCB:\n\n{issues_text}\n\n"
            "Dla każdego błędu podaj:\n"
            "1. Dlaczego ten błąd jest ważny (konsekwencje w produkcji)\n"
            "2. Dokładny sposób naprawy w KiCad\n"
            "3. Priorytet naprawy (krytyczny / ważny / kosmetyczny)\n"
            "4. Czy można wdrożyć wyjątek (DRC waiver) i kiedy\n\n"
            "Na końcu podaj: które błędy muszą być naprawione PRZED zamówieniem PCB."
        )
        self.ask_async(prompt, "pcb_system", on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def analyze_pcb(self, board, on_chunk=None, on_done=None, on_error=None) -> None:
        if not board:
            return
        comp_summary = {}
        for c in board.components:
            comp_summary[c.component_type] = comp_summary.get(c.component_type, 0) + 1
        prompt = (
            f"Dokonaj kompleksowej analizy płytki PCB:\n"
            f"Wymiary: {board.width_mm:.1f} x {board.height_mm:.1f} mm\n"
            f"Komponenty: {json.dumps(comp_summary, ensure_ascii=False)}\n"
            f"Ścieżki: {len(board.traces)}, Przelotki: {len(board.vias)}, Sieci: {len(board.nets)}\n\n"
            "Oceń:\n"
            "1. Ogólną architekturę układu (co to za projekt?)\n"
            "2. Potencjalne problemy z zasilaniem i filtrowaniem\n"
            "3. Ryzyko EMI/EMC\n"
            "4. Rekomendacje co do stackupu warstw\n"
            "5. Miejsca wymagające szczególnej uwagi przy trasowaniu\n"
            "6. Proponowane ulepszenia funkcjonalne"
        )
        self.ask_async(prompt, "pcb_system", on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def generate_project_meta(self, project_name: str, board=None, on_done=None, on_error=None) -> None:
        board_info = ""
        if board:
            board_info = (
                f"PCB {board.width_mm:.0f}x{board.height_mm:.0f}mm, "
                f"{len(board.components)} komponentów, "
                f"{len(board.nets)} sieci"
            )
        prompt = (
            f"Dla projektu elektronicznego '{project_name}' ({board_info}) wygeneruj JSON:\n"
            '{"title": "...", "description": "...", "tags": ["tag1","tag2","tag3"], '
            '"category": "...", "difficulty": "beginner/intermediate/advanced"}\n\n'
            "Opis powinien być po angielsku (dla GitHub), max 120 znaków. "
            "Tagi: technologie, MCU, zastosowanie. "
            "Odpowiedz TYLKO czystym JSON bez markdown."
        )
        def _on_done(text: str) -> None:
            try:
                start = text.find("{")
                end   = text.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(text[start:end])
                    if on_done:
                        on_done(data)
                    return
            except Exception:
                pass
            if on_done:
                on_done({"title": project_name, "description": "", "tags": []})

        self.ask_async(prompt, "pcb_system", on_done=_on_done, on_error=on_error)
