#!/usr/bin/env python3
"""
build_rag.py — Buduje lokalny indeks RAG dla ElectroVision AI.

Uruchom raz po instalacji lub po dodaniu nowych plików wiedzy:
    python training_data/build_rag.py

Wymaga: pip install sentence-transformers numpy
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    print("═" * 60)
    print("  ElectroVision AI — Budowanie bazy wiedzy RAG")
    print("═" * 60)

    # Sprawdź sentence-transformers
    try:
        import sentence_transformers
        print(f"✓ sentence-transformers {sentence_transformers.__version__}")
    except ImportError:
        print("✗ Brak sentence-transformers!")
        print("  Zainstaluj: pip install sentence-transformers")
        print("  (wymaga ~80MB pobrania, model AI embeddings)")
        print()
        print("  Alternatywnie RAG będzie działał w trybie keyword-search")
        print("  (mniej dokładny, ale bez dodatkowych zależności)")

    # Sprawdź numpy
    try:
        import numpy as np
        print(f"✓ numpy {np.__version__}")
    except ImportError:
        print("✗ Brak numpy! Zainstaluj: pip install numpy")
        sys.exit(1)

    # Zbuduj indeks
    from src.ai.rag.knowledge_base import LocalKnowledgeBase
    kb = LocalKnowledgeBase.instance()

    print()
    print("Indeksowanie plików wiedzy...")
    t0 = time.time()
    result = kb.build(force=True)
    elapsed = time.time() - t0

    print(f"✓ {result}")
    print(f"  Czas budowania: {elapsed:.1f}s")
    print(f"  Chunki: {kb.chunk_count}")
    print()

    # Test wyszukiwania
    print("Test wyszukiwania:")
    queries = [
        "szerokość ścieżki dla prądu 2A",
        "CadQuery standoff obudowa",
        "ESP32 GPIO konfiguracja przerwanie",
    ]
    for q in queries:
        chunks = kb.search(q, k=2)
        if chunks:
            best = chunks[0]
            print(f"  Q: '{q}'")
            print(f"  → [{best['source']}] score={best.get('score',0):.3f}: {best['text'][:80]}…")
        else:
            print(f"  Q: '{q}' → brak wyników")
    print()

    print("═" * 60)
    print("  RAG gotowy! ElectroVision AI używa teraz lokalnej wiedzy.")
    print()
    print("  Aby zainstalować model Ollama 'electrovision':")
    print("    ollama create electrovision -f training_data/Modelfile")
    print("    ollama run electrovision")
    print("═" * 60)


if __name__ == "__main__":
    main()
