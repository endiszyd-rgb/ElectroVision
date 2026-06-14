from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from .models.pcb_board import PCBBoard


@dataclass
class Project:
    name: str = "Nowy projekt"
    path: Optional[Path] = None
    board: Optional[PCBBoard] = None
    modified: bool = False

    def is_empty(self) -> bool:
        return self.board is None

    def save_path_str(self) -> str:
        return str(self.path) if self.path else ""
