from dataclasses import dataclass, field


@dataclass
class Net:
    number: int
    name: str

    def is_power(self) -> bool:
        name_upper = self.name.upper()
        return any(p in name_upper for p in ("VCC", "VDD", "GND", "PWR", "3V3", "5V", "12V"))
