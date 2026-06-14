"""
LocalKnowledgeBase — lokalny silnik RAG dla ElectroVision AI.

Działa w 100% offline bez GPU:
- sentence-transformers (all-MiniLM-L6-v2, 22MB) do embeddingów
- numpy do obliczeń podobieństwa (cosine similarity)
- Zapis/odczyt z pliku JSON (zero dodatkowych baz danych)

Użycie:
    kb = LocalKnowledgeBase.instance()
    kb.build()                          # jednorazowo przy starcie
    chunks = kb.search("ESP32 WiFi", k=5)
    context = kb.context_for_query("szerokość ścieżki 2A")
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Optional

import numpy as np

_DATA_DIR = Path(__file__).parent.parent / "knowledge" / "data"
_INDEX_FILE = _DATA_DIR / "rag_index.npz"
_CHUNKS_FILE = _DATA_DIR / "rag_chunks.json"


def _split_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """Split text into overlapping chunks by sentence boundaries."""
    sentences = re.split(r'(?<=[.!?\n])\s+', text.strip())
    chunks, current, length = [], [], 0
    for sent in sentences:
        words = len(sent.split())
        if length + words > chunk_size and current:
            chunks.append(" ".join(current))
            keep = []
            keep_len = 0
            for s in reversed(current):
                w = len(s.split())
                if keep_len + w > overlap:
                    break
                keep.insert(0, s)
                keep_len += w
            current = keep
            length = keep_len
        current.append(sent)
        length += words
    if current:
        chunks.append(" ".join(current))
    return [c for c in chunks if len(c.strip()) > 20]


class LocalKnowledgeBase:
    """Singleton RAG knowledge base with local embeddings."""

    _instance: Optional["LocalKnowledgeBase"] = None

    @classmethod
    def instance(cls) -> "LocalKnowledgeBase":
        if cls._instance is None:
            cls._instance = LocalKnowledgeBase()
        return cls._instance

    def __init__(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._embeddings: Optional[np.ndarray] = None
        self._chunks: list[dict] = []
        self._model = None
        self._ready = False

    # ── Embed model ───────────────────────────────────────────────────────────

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                return None
        return self._model

    def _embed(self, texts: list[str]) -> Optional[np.ndarray]:
        model = self._get_model()
        if model is None:
            return None
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    # ── Build index ───────────────────────────────────────────────────────────

    def build(self, force: bool = False) -> str:
        """Scan knowledge files, build embedding index. Returns status message."""
        knowledge_files = list(_DATA_DIR.parent.parent.parent.glob("training_data/**/*.txt")) + \
                          list(_DATA_DIR.parent.parent.parent.glob("training_data/**/*.md")) + \
                          list(_DATA_DIR.glob("*.txt")) + \
                          list(_DATA_DIR.glob("*.md")) + \
                          list((_DATA_DIR.parent / "prompts").glob("*.txt"))

        src_hash = hashlib.md5(str(sorted(str(f) for f in knowledge_files)).encode()).hexdigest()
        meta_file = _DATA_DIR / "rag_meta.json"

        if not force and _INDEX_FILE.exists() and _CHUNKS_FILE.exists() and meta_file.exists():
            meta = json.loads(meta_file.read_text())
            if meta.get("hash") == src_hash:
                return self._load()

        all_chunks: list[dict] = []
        for f in knowledge_files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for i, chunk in enumerate(_split_text(text)):
                    all_chunks.append({
                        "text":   chunk,
                        "source": f.name,
                        "idx":    i,
                    })
            except Exception:
                continue

        if not all_chunks:
            return "Brak plików wiedzy — dodaj pliki do training_data/"

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embed(texts)
        if embeddings is None:
            self._chunks = all_chunks
            self._ready = True
            return f"Załadowano {len(all_chunks)} chunków (bez embeddingów — zainstaluj sentence-transformers)"

        np.savez_compressed(str(_INDEX_FILE), embeddings=embeddings)
        _CHUNKS_FILE.write_text(json.dumps(all_chunks, ensure_ascii=False), encoding="utf-8")
        meta_file.write_text(json.dumps({"hash": src_hash, "count": len(all_chunks)}))

        self._embeddings = embeddings
        self._chunks = all_chunks
        self._ready = True
        return f"Zbudowano indeks RAG: {len(all_chunks)} chunków z {len(knowledge_files)} plików"

    def _load(self) -> str:
        try:
            data = np.load(str(_INDEX_FILE))
            self._embeddings = data["embeddings"]
            self._chunks = json.loads(_CHUNKS_FILE.read_text(encoding="utf-8"))
            self._ready = True
            return f"Załadowano indeks RAG: {len(self._chunks)} chunków"
        except Exception as e:
            return f"Błąd ładowania indeksu: {e}"

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5, domain: str = "") -> list[dict]:
        """Return top-k most relevant chunks for query."""
        if not self._ready:
            return []

        if self._embeddings is not None:
            q_emb = self._embed([query])
            if q_emb is None:
                return self._keyword_search(query, k, domain)
            scores = (self._embeddings @ q_emb[0]).flatten()
            if domain:
                for i, chunk in enumerate(self._chunks):
                    if domain.lower() not in chunk.get("source", "").lower():
                        scores[i] *= 0.5
            top_k = np.argsort(scores)[::-1][:k]
            return [
                {**self._chunks[i], "score": float(scores[i])}
                for i in top_k if scores[i] > 0.1
            ]

        return self._keyword_search(query, k, domain)

    def _keyword_search(self, query: str, k: int, domain: str) -> list[dict]:
        """Fallback: TF-IDF style keyword scoring when no embeddings."""
        words = set(query.lower().split())
        scored = []
        for chunk in self._chunks:
            if domain and domain.lower() not in chunk.get("source", "").lower():
                continue
            text_lower = chunk["text"].lower()
            score = sum(text_lower.count(w) for w in words)
            if score > 0:
                scored.append({**chunk, "score": score})
        scored.sort(key=lambda x: -x["score"])
        return scored[:k]

    def context_for_query(self, query: str, k: int = 6, domain: str = "", max_chars: int = 3000) -> str:
        """Return formatted context string for injection into LLM prompt."""
        chunks = self.search(query, k=k, domain=domain)
        if not chunks:
            return ""
        parts = []
        total = 0
        for c in chunks:
            text = c["text"]
            if total + len(text) > max_chars:
                break
            parts.append(f"[{c['source']}]\n{text}")
            total += len(text)
        return "## Wiedza techniczna (RAG):\n\n" + "\n\n---\n\n".join(parts)

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)
