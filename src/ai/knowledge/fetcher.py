"""
Knowledge base fetcher — downloads free PCB and STL reference data.

Sources used (all free/open):
  - KiCad standard library README (GitHub: KiCad/kicad-symbols)
  - KiCad footprint library index (GitHub: KiCad/kicad-footprints)
  - Arduino library index (GitHub: arduino/library-registry)
  - Thingiverse Electronics category metadata (public API)
  - Common component datasheets (via search scrape — Wikipedia + datasheetspdf)
"""

import json
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

_SOURCES = {
    "kicad_symbols": {
        "url": "https://raw.githubusercontent.com/KiCad/kicad-symbols/master/README.md",
        "file": "kicad_symbols_readme.txt",
        "type": "text",
    },
    "arduino_libraries": {
        "url": "https://raw.githubusercontent.com/arduino/library-registry/main/registries.json",
        "file": "arduino_libraries.json",
        "type": "json",
    },
    "kicad_footprints_index": {
        "url": "https://api.github.com/repos/KiCad/kicad-footprints/git/trees/main?recursive=1",
        "file": "kicad_footprints_index.json",
        "type": "json",
    },
}

_BUILTIN_COMPONENT_DB: dict = {
    "resistors": {
        "description": "Rezystory SMD i THT",
        "common_values": ["10Ω", "100Ω", "1kΩ", "10kΩ", "100kΩ", "1MΩ"],
        "common_packages": ["0201", "0402", "0603", "0805", "1206", "THT"],
        "power_ratings": ["1/20W", "1/16W", "1/10W", "1/8W", "1/4W", "1/2W", "1W"],
        "tolerances": ["1%", "5%"],
        "notes": "Dodaj pull-up/pull-down 10kΩ na linie GPIO. Szeregowe 33Ω przy sygnałach USB.",
    },
    "capacitors": {
        "description": "Kondensatory ceramiczne, elektrolityczne, tantalowe",
        "common_values": ["100pF", "1nF", "10nF", "100nF", "1µF", "10µF", "100µF", "1000µF"],
        "common_packages": ["0201", "0402", "0603", "0805", "1206", "THT", "SMD_A", "SMD_B"],
        "notes": "100nF blokujące przy każdym VCC pinu IC (max 5mm od pinu). 10µF bulk na liniach zasilania.",
    },
    "microcontrollers": {
        "esp32": {
            "manufacturer": "Espressif",
            "cores": 2,
            "freq_mhz": 240,
            "flash": "4MB",
            "ram": "520KB",
            "gpio": 34,
            "interfaces": ["UART×3", "SPI×4", "I2C×2", "I2S×2", "WiFi", "BT"],
            "voltage": "3.3V",
            "package": "QFN48",
            "notes": "GPIO 34-39 input only. Nie używaj GPIO 0, 2, 15 jako output przy bootowaniu.",
        },
        "stm32f103": {
            "manufacturer": "STMicroelectronics",
            "cores": 1,
            "freq_mhz": 72,
            "flash": "64/128KB",
            "ram": "20KB",
            "gpio": 37,
            "interfaces": ["UART×3", "SPI×2", "I2C×2", "CAN", "USB"],
            "voltage": "3.3V",
            "package": "LQFP48",
        },
        "rp2040": {
            "manufacturer": "Raspberry Pi",
            "cores": 2,
            "freq_mhz": 133,
            "flash": "external (QSPI)",
            "ram": "264KB",
            "gpio": 30,
            "interfaces": ["UART×2", "SPI×2", "I2C×2", "PIO×2", "USB"],
            "voltage": "3.3V",
            "package": "QFN56",
        },
    },
    "sensors": {
        "bme280": {
            "type": "temperatura/wilgotność/ciśnienie",
            "interface": "I2C (0x76/0x77) lub SPI",
            "voltage": "1.71-3.6V",
            "range": "-40..+85°C, 0..100% RH, 300..1100 hPa",
            "library": "Adafruit_BME280",
        },
        "mpu6050": {
            "type": "akcelerometr 3-osiowy + żyroskop 3-osiowy",
            "interface": "I2C (0x68/0x69)",
            "voltage": "3.3V",
            "library": "MPU6050 by Electronic Cats",
        },
        "ds18b20": {
            "type": "temperatura (1-Wire)",
            "interface": "1-Wire (parasite power)",
            "voltage": "3.0-5.5V",
            "range": "-55..+125°C ±0.5°C",
            "library": "DallasTemperature + OneWire",
            "notes": "Pull-up 4.7kΩ na DQ pin.",
        },
    },
    "displays": {
        "ssd1306": {
            "type": "OLED 128×64 lub 128×32",
            "interface": "I2C (0x3C/0x3D) lub SPI",
            "voltage": "3.3-5V",
            "library": "Adafruit_SSD1306",
            "notes": "Zasilanie osobne 3.3V dla pełnej jasności.",
        },
        "st7789": {
            "type": "LCD TFT kolor 240×240 lub 240×320",
            "interface": "SPI (do 80MHz)",
            "voltage": "3.3V",
            "library": "Adafruit_ST7789 lub TFT_eSPI",
        },
    },
    "pcb_rules": {
        "min_trace_width": 0.1,
        "min_clearance": 0.1,
        "min_via_drill": 0.2,
        "min_via_annular": 0.1,
        "min_edge_clearance": 0.3,
        "power_trace_width_per_amp": 0.5,
        "recommended_bypass_cap": "100nF + 10µF per IC power pin",
        "stackup_standard": "4-layer: Signal / GND / PWR / Signal",
    },
    "stl_design_rules": {
        "min_wall_thickness_fdm": 1.2,
        "min_wall_thickness_sla": 0.4,
        "min_feature_size_fdm": 0.4,
        "max_overhang_without_support": 45,
        "standoff_outer_diameter": 5.0,
        "standoff_screw_m2_hole": 2.2,
        "standoff_screw_m3_hole": 3.2,
        "usb_a_cutout": [12.0, 5.0],
        "usb_micro_cutout": [8.0, 3.5],
        "usb_c_cutout": [9.5, 3.5],
        "barrel_jack_21mm_hole": 6.5,
        "tolerance_fdm_loose": 0.4,
        "tolerance_fdm_press_fit": 0.1,
        "recommended_infill": 20,
        "recommended_perimeters": 3,
    },
}


class KnowledgeFetcher:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_all(self) -> str:
        self._save_builtin()
        results = []
        for name, src in _SOURCES.items():
            result = self._fetch_one(name, src)
            results.append(result)
        return " | ".join(results)

    def _save_builtin(self) -> None:
        path = DATA_DIR / "components_knowledge.json"
        path.write_text(json.dumps(_BUILTIN_COMPONENT_DB, ensure_ascii=False, indent=2), encoding="utf-8")

    def _fetch_one(self, name: str, src: dict) -> str:
        try:
            req = urllib.request.Request(
                src["url"],
                headers={"User-Agent": "ElectroVision/0.1 PCB-Tool"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()

            out_path = DATA_DIR / src["file"]
            if src["type"] == "json":
                data = json.loads(raw)
                out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                out_path.write_bytes(raw)
            return f"{name}:OK"
        except Exception as e:
            return f"{name}:FAIL({e})"

    def load_knowledge(self) -> dict:
        path = DATA_DIR / "components_knowledge.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return _BUILTIN_COMPONENT_DB

    def knowledge_as_context(self) -> str:
        kb = self.load_knowledge()
        lines = []
        if "pcb_rules" in kb:
            r = kb["pcb_rules"]
            lines.append(f"PCB min trace: {r['min_trace_width']}mm, clearance: {r['min_clearance']}mm, via drill: {r['min_via_drill']}mm")
        if "stl_design_rules" in kb:
            s = kb["stl_design_rules"]
            lines.append(f"STL min wall FDM: {s['min_wall_thickness_fdm']}mm, max overhang: {s['max_overhang_without_support']}°")
        if "microcontrollers" in kb:
            for mcu, data in kb["microcontrollers"].items():
                lines.append(f"MCU {mcu.upper()}: {data.get('freq_mhz')}MHz, {data.get('ram')} RAM, {data.get('interfaces')}")
        return "\n".join(lines)
