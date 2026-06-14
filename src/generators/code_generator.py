"""Generate starter code for Arduino, MicroPython, ESP-IDF from component list."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, BaseLoader, TemplateNotFound
from src.core.models.component import Component

_ARDUINO_TEMPLATE = '''\
/*
 * {{ project_name }} — wygenerowano przez ElectroVision
 * MCU: {{ mcu }}
 * Platforma: Arduino
 *
 * KOMPONENTY:
{% for c in components %}
 *   {{ c.reference }} — {{ c.value }} ({{ c.component_type }})
{% endfor %}
 */

{% for lib in libraries %}
#include <{{ lib }}>
{% endfor %}

// ===== DEFINICJE PINÓW =====
{% for c in components %}
{% if c.pin_defines %}
{% for pd in c.pin_defines %}
#define {{ pd.name }}  {{ pd.value }}
{% endfor %}
{% endif %}
{% endfor %}

// ===== ZMIENNE GLOBALNE =====
{% for c in components %}
{% if c.global_vars %}
{{ c.global_vars }}
{% endif %}
{% endfor %}

void setup() {
    Serial.begin(115200);
    Serial.println("{{ project_name }} - Start");

{% for c in components %}
{% if c.setup_code %}
    // {{ c.reference }} — {{ c.value }}
{{ c.setup_code | indent(4) }}
{% endif %}
{% endfor %}
}

void loop() {
{% for c in components %}
{% if c.loop_code %}
    // {{ c.reference }} — {{ c.value }}
{{ c.loop_code | indent(4) }}
{% endif %}
{% endfor %}
    delay(100);
}
'''

_MICROPYTHON_TEMPLATE = '''\
# {{ project_name }} — wygenerowano przez ElectroVision
# MCU: {{ mcu }}
# Platforma: MicroPython
#
# KOMPONENTY:
{% for c in components %}
# {{ c.reference }} — {{ c.value }} ({{ c.component_type }})
{% endfor %}

from machine import Pin, I2C, SPI, UART, ADC, PWM
import time
{% for lib in libraries %}
import {{ lib }}
{% endfor %}

# ===== KONFIGURACJA PINÓW =====
{% for c in components %}
{% if c.pin_defines %}
{% for pd in c.pin_defines %}
{{ pd.name }} = {{ pd.value }}
{% endfor %}
{% endif %}
{% endfor %}

# ===== INICJALIZACJA =====
{% for c in components %}
{% if c.setup_code %}
# {{ c.reference }} — {{ c.value }}
{{ c.setup_code }}
{% endif %}
{% endfor %}

def main():
    print("{{ project_name }} - Start")
{% for c in components %}
{% if c.loop_code %}
    # {{ c.reference }} — {{ c.value }}
{{ c.loop_code | indent(4) }}
{% endif %}
{% endfor %}
    while True:
        time.sleep_ms(100)

if __name__ == "__main__":
    main()
'''

_CPP_TEMPLATE = '''\
/*
 * {{ project_name }} — wygenerowano przez ElectroVision
 * MCU: {{ mcu }}
 * Platforma: ESP-IDF / PlatformIO C++
 */

#include <Arduino.h>
{% for lib in libraries %}
#include <{{ lib }}>
{% endfor %}

// ===== DEFINICJE PINÓW =====
{% for c in components %}
{% if c.pin_defines %}
{% for pd in c.pin_defines %}
constexpr int {{ pd.name }} = {{ pd.value }};
{% endfor %}
{% endif %}
{% endfor %}

void setup() {
    Serial.begin(115200);
{% for c in components %}
{% if c.setup_code %}
    // {{ c.reference }} — {{ c.value }}
{{ c.setup_code | indent(4) }}
{% endif %}
{% endfor %}
}

void loop() {
{% for c in components %}
{% if c.loop_code %}
    // {{ c.reference }} — {{ c.value }}
{{ c.loop_code | indent(4) }}
{% endif %}
{% endfor %}
    delay(100);
}
'''


_COMPONENT_KNOWLEDGE: dict[str, dict] = {
    "led": {
        "libraries": [],
        "pin_prefix": "LED",
        "setup": 'pinMode({pin}, OUTPUT);',
        "loop":  'digitalWrite({pin}, HIGH); delay(500); digitalWrite({pin}, LOW); delay(500);',
    },
    "resistor": {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "capacitor": {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "inductor":  {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "fuse":      {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "transistor": {
        "libraries": [],
        "pin_prefix": "TRANSISTOR",
        "setup": 'pinMode({pin}, OUTPUT);',
        "loop":  "",
    },
    "diode": {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "switch": {
        "libraries": [],
        "pin_prefix": "BTN",
        "setup": 'pinMode({pin}, INPUT_PULLUP);',
        "loop":  'if (!digitalRead({pin})) {{ Serial.println("{ref} pressed"); }}',
    },
    "connector": {"libraries": [], "pin_prefix": "CONN", "setup": "", "loop": ""},
    "crystal":   {"libraries": [], "pin_prefix": None, "setup": "", "loop": ""},
    "ic": {
        "libraries": ["Wire"],
        "pin_prefix": "IC",
        "setup": 'Wire.begin();',
        "loop":  "",
    },
    "generic": {"libraries": [], "pin_prefix": "COMP", "setup": "", "loop": ""},
}

_VALUE_OVERRIDES: dict[str, dict] = {
    "esp32":   {"libraries": ["WiFi", "Wire", "SPI"], "setup": "WiFi.mode(WIFI_STA);", "loop": ""},
    "esp8266": {"libraries": ["ESP8266WiFi"], "setup": "WiFi.mode(WIFI_STA);", "loop": ""},
    "dht22":   {"libraries": ["DHT"], "setup": "DHT dht({pin}, DHT22); dht.begin();",
                "loop": 'float t={ref}_dht.readTemperature(); Serial.println(t);'},
    "dht11":   {"libraries": ["DHT"], "setup": "DHT dht({pin}, DHT11); dht.begin();",
                "loop": 'float t={ref}_dht.readTemperature(); Serial.println(t);'},
    "bme280":  {"libraries": ["Adafruit_BME280"], "setup": "bme.begin(0x76);", "loop": 'Serial.println(bme.readTemperature());'},
    "ssd1306": {"libraries": ["Adafruit_SSD1306"], "setup": 'display.begin(SSD1306_SWITCHCAPVCC, 0x3C); display.clearDisplay();', "loop": ""},
    "mpu6050": {"libraries": ["MPU6050"], "setup": "mpu.initialize();", "loop": ""},
    "nrf24l01":{"libraries": ["RF24"], "setup": "radio.begin(); radio.openReadingPipe(0, address);", "loop": ""},
    "ds18b20": {"libraries": ["OneWire", "DallasTemperature"],
                "setup": "sensors.begin();",
                "loop": 'sensors.requestTemperatures(); Serial.println(sensors.getTempCByIndex(0));'},
    "hcsr04":  {"libraries": [], "setup": 'pinMode({pin}_TRIG, OUTPUT); pinMode({pin}_ECHO, INPUT);',
                "loop": 'digitalWrite({pin}_TRIG, HIGH); delayMicroseconds(10); digitalWrite({pin}_TRIG, LOW);'},
    "servo":   {"libraries": ["Servo"], "setup": 'myServo.attach({pin});', "loop": ""},
    "l298n":   {"libraries": [], "setup": 'pinMode({pin}_IN1, OUTPUT); pinMode({pin}_IN2, OUTPUT);', "loop": ""},
    "oled":    {"libraries": ["Adafruit_SSD1306"], "setup": 'display.begin(SSD1306_SWITCHCAPVCC, 0x3C);', "loop": ""},
    "lcd":     {"libraries": ["LiquidCrystal_I2C"], "setup": 'lcd.init(); lcd.backlight();', "loop": 'lcd.setCursor(0,0); lcd.print("Hello");'},
}


def _enrich_component(comp: Component, platform: str, pin_counter: list[int]) -> object:
    class Enriched:
        pass
    e = Enriched()
    e.reference = comp.reference
    e.value = comp.value
    e.component_type = comp.component_type

    val_lower = comp.value.lower().replace("-", "").replace("_", "").replace(".", "")
    knowledge = _VALUE_OVERRIDES.get(val_lower) or _COMPONENT_KNOWLEDGE.get(comp.component_type, {})

    e.libraries = knowledge.get("libraries", [])

    pin_num = pin_counter[0]
    pin_counter[0] += 1
    pin_name = f"{comp.reference.replace(' ', '_').upper()}_PIN"

    prefix = knowledge.get("pin_prefix")
    if not prefix:
        e.pin_defines = []
        e.setup_code = knowledge.get("setup", "").format(pin=pin_num, ref=comp.reference)
        e.loop_code  = knowledge.get("loop", "").format(pin=pin_num, ref=comp.reference)
        e.global_vars = ""
        return e

    e.pin_defines = [type("PD", (), {"name": pin_name, "value": str(pin_num)})()]
    template_setup = knowledge.get("setup", "")
    template_loop  = knowledge.get("loop", "")
    e.setup_code = template_setup.replace("{pin}", pin_name).replace("{ref}", comp.reference)
    e.loop_code  = template_loop.replace("{pin}", pin_name).replace("{ref}", comp.reference)
    e.global_vars = ""
    return e


class CodeGenerator:
    @staticmethod
    def generate(
        components: list[Component],
        platform: str = "arduino",
        mcu: str = "Arduino Uno",
        project_name: str = "ElectroVision",
    ) -> str:
        pin_counter = [2]
        enriched = [_enrich_component(c, platform, pin_counter) for c in components]

        all_libs: list[str] = []
        for e in enriched:
            for lib in e.libraries:
                if lib not in all_libs:
                    all_libs.append(lib)

        ctx = {
            "project_name": project_name,
            "mcu": mcu,
            "platform": platform,
            "components": enriched,
            "libraries": all_libs,
        }

        env = Environment(loader=BaseLoader())
        if platform == "micropython":
            tmpl = env.from_string(_MICROPYTHON_TEMPLATE)
        elif platform in ("esp_idf", "platformio"):
            tmpl = env.from_string(_CPP_TEMPLATE)
        else:
            tmpl = env.from_string(_ARDUINO_TEMPLATE)

        return tmpl.render(**ctx)
