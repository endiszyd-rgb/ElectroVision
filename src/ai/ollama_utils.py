"""Ollama connectivity helpers — check, start, diagnose."""
from __future__ import annotations
import subprocess
import sys
from typing import Optional


_OLLAMA_URL = "http://localhost:11434"


def is_ollama_running() -> bool:
    """Return True if Ollama API is reachable at localhost:11434."""
    try:
        import urllib.request
        urllib.request.urlopen(_OLLAMA_URL, timeout=2)
        return True
    except Exception:
        return False


def is_connection_error(exc_or_msg: "Exception | str") -> bool:
    """Return True if the error represents a refused/unavailable connection."""
    msg = str(exc_or_msg).lower()
    keywords = (
        "connection", "refused", "winerror 10061", "winerror 10060",
        "połączenia", "odmawia", "connect", "timed out", "timeout",
        "unreachable", "10061", "10060",
    )
    return any(k in msg for k in keywords)


def friendly_error(exc_or_msg: "Exception | str") -> str:
    """Convert a raw exception/message to a user-friendly Polish string."""
    msg = str(exc_or_msg)
    if "No module named 'ollama'" in msg or "ImportError" in msg:
        return (
            "Brakuje pakietu Python 'ollama'.\n\n"
            "Zainstaluj w terminalu:\n"
            "    pip install ollama\n\n"
            "Następnie pobierz model:\n"
            "    ollama pull llama3"
        )
    if is_connection_error(msg):
        return (
            "Ollama nie jest uruchomiona (lub nie zainstalowana).\n\n"
            "Aby korzystać z funkcji AI:\n"
            "  1. Pobierz Ollama ze strony:  https://ollama.ai\n"
            "  2. Zainstaluj i uruchom aplikację Ollama\n"
            "  3. W terminalu wpisz:  ollama pull llama3\n"
            "  4. Wróć do ElectroVision i spróbuj ponownie.\n\n"
            "Możesz też kliknąć przycisk poniżej, aby uruchomić 'ollama serve'."
        )
    if "model" in msg.lower() and ("not found" in msg.lower() or "pull" in msg.lower()):
        return (
            "Model AI nie jest zainstalowany.\n\n"
            "Pobierz model wpisując w terminalu:\n"
            "    ollama pull llama3\n\n"
            "Lub wybierz inny model w ElectroVision > AI > Wybierz model."
        )
    return f"Błąd AI:\n{msg}"


def try_start_ollama() -> tuple[bool, str]:
    """Try to start 'ollama serve' in the background.
    Returns (success, message).
    """
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True, "Uruchomiono 'ollama serve'. Poczekaj kilka sekund i spróbuj ponownie."
    except FileNotFoundError:
        return False, (
            "Nie znaleziono programu 'ollama'.\n"
            "Pobierz i zainstaluj ze strony: https://ollama.ai"
        )
    except Exception as e:
        return False, f"Nie udało się uruchomić Ollama: {e}"
