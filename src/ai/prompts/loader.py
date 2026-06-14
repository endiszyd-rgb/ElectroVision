from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_CACHE: dict[str, str] = {}


def load_prompt(name: str) -> str:
    if name not in _CACHE:
        path = _PROMPTS_DIR / f"{name}.txt"
        _CACHE[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _CACHE[name]
