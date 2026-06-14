"""Base class for specialized ElectroVision AI agents."""
from __future__ import annotations
from typing import Callable, Optional


class BaseAgent:
    """
    Specjalizowany agent AI z dostępem do RAG i Ollama.

    Każdy agent ma:
    - Własny system prompt (specjalizacja dziedzinowa)
    - Własne metody pomocnicze
    - Dostęp do bazy wiedzy RAG
    - Wspólny interfejs ask_async / ask_sync
    """

    DOMAIN: str = ""          # słowo kluczowe do filtrowania RAG (pcb / stl / code)
    SYSTEM_KEY: str = ""      # klucz system promptu z pliku txt
    RAG_CHUNKS: int = 6       # ile chunków RAG dołączyć

    def __init__(self) -> None:
        from src.ai.bridge import AIBridge
        from src.ai.rag.knowledge_base import LocalKnowledgeBase
        self._bridge = AIBridge.instance()
        self._kb = LocalKnowledgeBase.instance()

    def _rag_context(self, query: str) -> str:
        if not self._kb.is_ready:
            return ""
        return self._kb.context_for_query(query, k=self.RAG_CHUNKS, domain=self.DOMAIN)

    def ask_async(
        self,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
        on_done: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        use_rag: bool = True,
    ) -> None:
        extra = self._rag_context(prompt) if use_rag else ""
        self._bridge.ask_async(
            prompt=prompt,
            system_key=self.SYSTEM_KEY,
            extra_system=extra,
            on_chunk=on_chunk,
            on_done=on_done,
            on_error=on_error,
        )

    def ask_sync(self, prompt: str, use_rag: bool = True) -> str:
        extra = self._rag_context(prompt) if use_rag else ""
        return self._bridge.ask_sync(prompt, system_key=self.SYSTEM_KEY, extra_system=extra)
