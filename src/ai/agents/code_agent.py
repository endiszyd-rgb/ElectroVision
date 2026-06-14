"""Code Agent — specjalizowany agent do generowania i analizy kodu embedded."""
from __future__ import annotations
from typing import Callable

from src.ai.agents.base_agent import BaseAgent


class CodeAgent(BaseAgent):
    DOMAIN     = "code"
    SYSTEM_KEY = "code_system"
    RAG_CHUNKS = 7

    def generate(self, components: list, platform: str, mcu: str,
                 on_chunk=None, on_done=None, on_error=None) -> None:
        comp_text = "\n".join(
            f"- {c.reference}: {c.value} ({c.component_type}), fp={c.footprint.split(':')[-1]}"
            for c in components[:30]
        )
        prompt = (
            f"Wygeneruj kompletny, gotowy do wgrania kod dla {platform} / {mcu}:\n\n"
            f"Lista komponentów:\n{comp_text}\n\n"
            "Wymagania:\n"
            "1. Wszystkie wymagane #include / import\n"
            "2. Stałe z numerami pinów (opisowe nazwy, nie liczby magiczne)\n"
            "3. Inicjalizacja WSZYSTKICH komponentów w setup() / main()\n"
            "4. Pętla główna z odczytem sensorów i sterowaniem wyjściami\n"
            "5. Obsługa błędów komunikacji (I2C, SPI timeout, retry)\n"
            "6. Komentarze przy nieoczywistych fragmentach\n"
            "7. Watchdog / feed watchdog w pętli (jeśli MCU obsługuje)\n\n"
            "Zwróć TYLKO kod, gotowy do skopiowania."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def improve(self, code: str, platform: str, mcu: str,
                on_chunk=None, on_done=None, on_error=None) -> None:
        prompt = (
            f"Ulepsz poniższy kod dla {platform} / {mcu}:\n\n"
            f"```\n{code[:4000]}\n```\n\n"
            "Popraw:\n"
            "1. Błędy i niebezpieczne wzorce\n"
            "2. Dodaj pełną obsługę błędów (timeout, retry, fallback)\n"
            "3. Zastąp delay() non-blocking millis()/micros()\n"
            "4. Watchdog timer\n"
            "5. Optymalizacja energetyczna (sleep, przerwania)\n"
            "6. Komentarze przy trudnych fragmentach\n\n"
            "Zwróć ulepszony kod + krótkie podsumowanie zmian."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def debug(self, code: str, platform: str, mcu: str,
              on_chunk=None, on_done=None, on_error=None) -> None:
        prompt = (
            f"Znajdź błędy i zagrożenia w kodzie dla {platform} / {mcu}:\n\n"
            f"```\n{code[:4000]}\n```\n\n"
            "Szukaj:\n"
            "1. Przepełnienia bufora, undefined behavior\n"
            "2. Wycieki pamięci (malloc bez free)\n"
            "3. Brakująca inicjalizacja peryferiów\n"
            "4. Blokujące delay() w pętli głównej\n"
            "5. Brak volatile dla zmiennych ISR\n"
            "6. Błędy I2C/SPI (brak Wire.begin, brak CS pin toggle)\n"
            "7. Przepełnienie int (użyj long/uint32_t)\n"
            "8. GPIO 0/2/15 ESP32 przy bootowaniu\n\n"
            "Format: numerowana lista znalezionych problemów z lokalizacją i naprawą."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def extend_for_mcu(self, code: str, mcu: str,
                       on_chunk=None, on_done=None, on_error=None) -> None:
        features = {
            "ESP32": "WiFi (WiFiClient + MQTT PubSubClient), BLE (BLEServer advertise), OTA (ArduinoOTA), deep sleep (esp_deep_sleep_start), watchdog (esp_task_wdt)",
            "ESP32-S3": "USB HID natywny (USB_HID), BLE 5.0, TensorFlow Lite Micro, PSRAM, Camera MIPI",
            "ESP8266": "WiFi (WiFiClient, ESP8266WebServer), OTA (ElegantOTA), deep sleep (ESP.deepSleep)",
            "Raspberry Pi Pico (RP2040)": "multicore (multiprocessing, second_core), PIO state machines, USB CDC, sleep_ms/wfi",
            "STM32F103 (Blue Pill)": "HAL GPIO, HAL I2C, HAL UART DMA, CAN bus (bxCAN), USB CDC, IWDG watchdog",
            "ATmega328P": "Timer interrupts (TIMER1_COMPA), sleep (power_down), ADC prescaler",
            "nRF52840": "BLE 5.3 (Bluefruit), Thread mesh, USB HID, Crypto AES",
        }.get(mcu, "watchdog, przerwania, tryby niskiego poboru mocy, DMA")

        prompt = (
            f"Rozbuduj kod dla {mcu} o funkcje specyficzne dla tego mikrokontrolera:\n\n"
            f"```\n{code[:3000]}\n```\n\n"
            f"Dodaj:\n{features}\n\n"
            "Napisz kompletny rozbudowany kod gotowy do wgrania."
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)

    def explain_libraries(self, code: str, platform: str,
                          on_chunk=None, on_done=None, on_error=None) -> None:
        import re
        if "micropython" in platform.lower() or "python" in platform.lower():
            includes = re.findall(r'^(?:import|from)\s+([\w.]+)', code, re.MULTILINE)
        else:
            includes = re.findall(r'#include\s*[<"]([^>"]+)[>"]', code)

        if not includes:
            if on_done:
                on_done("Brak bibliotek do wyjaśnienia w kodzie.")
            return

        libs = "\n".join(f"• {lib}" for lib in dict.fromkeys(includes))
        prompt = (
            f"Wyjaśnij każdą bibliotekę z listy:\n\n{libs}\n\n"
            "Dla każdej:\n"
            "1. Do czego służy (1-2 zdania)\n"
            "2. Instalacja (Library Manager / pip / URL)\n"
            "3. Przykład inicjalizacji (2-4 linie kodu)\n"
            "4. Najważniejsze metody/funkcje (3-5 szt.)\n"
            "5. Alternatywne biblioteki (jeśli istnieją)"
        )
        self.ask_async(prompt, on_chunk=on_chunk, on_done=on_done, on_error=on_error)
