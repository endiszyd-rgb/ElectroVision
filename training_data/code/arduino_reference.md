# Arduino Language Reference — Kompletny przewodnik
# Źródło: https://docs.arduino.cc/language-reference/

## Digital I/O

### pinMode(pin, mode)
Konfiguruje pin jako wejście lub wyjście.
- `pin`: numer pinu (int)
- `mode`: INPUT, OUTPUT, INPUT_PULLUP, INPUT_PULLDOWN (ESP32)
```cpp
void setup() {
    pinMode(13, OUTPUT);       // LED
    pinMode(2,  INPUT_PULLUP); // przycisk z pull-up do VCC
}
```

### digitalWrite(pin, value)
Ustawia stan cyfrowy na pinie wyjściowym.
- `value`: HIGH (1) lub LOW (0)
```cpp
digitalWrite(13, HIGH);  // włącz LED
digitalWrite(13, LOW);   // wyłącz LED
```

### digitalRead(pin)
Odczytuje stan pinu cyfrowego.
- Zwraca: HIGH lub LOW (int)
```cpp
int state = digitalRead(2);
if (state == LOW) { /* przycisk wciśnięty (pull-up) */ }
```

## Analog I/O

### analogRead(pin)
Odczyt analogowy (ADC). Arduino Uno: 10-bit (0-1023), ESP32: 12-bit (0-4095).
- Napięcie: 0 do AREF (domyślnie 5V na Uno, 3.3V na ESP32)
```cpp
int val = analogRead(A0);
float voltage = val * (3.3 / 4095.0);  // ESP32
```

### analogWrite(pin, value)
PWM output. Zakres: 0 (off) do 255 (pełne). NIE dostępne na wszystkich pinach.
- Częstotliwość: ~490Hz (piny 3,9,10,11) lub ~980Hz (piny 5,6) na Arduino Uno
```cpp
analogWrite(9, 128);  // 50% duty cycle
```

### analogReference(type)
Zmienia napięcie referencyjne ADC:
- DEFAULT: 5V (Uno) lub 3.3V (ESP32)
- INTERNAL: 1.1V (Uno)
- EXTERNAL: AREF pin

### analogReadResolution(bits) — tylko Arduino Due/Zero/ESP32
```cpp
analogReadResolution(12);  // 12-bit (0-4095)
```

## Czas

### delay(ms)
Wstrzymuje program na `ms` milisekund. **Blokuje przerwania Serial!**
```cpp
delay(1000);  // 1 sekunda
```

### millis()
Zwraca czas od uruchomienia w ms (unsigned long, przepełnia co ~50 dni).
```cpp
unsigned long start = millis();
// ... coś trwa ...
Serial.println(millis() - start);  // czas trwania
```

### Non-blocking delay (zalecane zamiast delay())
```cpp
unsigned long prev = 0;
const long interval = 1000;  // 1 sekunda

void loop() {
    if (millis() - prev >= interval) {
        prev = millis();
        // kod wykonywany co 1 sekundę
        toggleLED();
    }
}
```

### micros()
Jak millis() ale w mikrosekundach (przepełnienie co ~70 minut).
```cpp
unsigned long t = micros();  // precyzja ~4µs (Arduino Uno)
```

### delayMicroseconds(us)
Opóźnienie w mikrosekundach (precyzja do ~3µs).

## Matematyka

### map(value, fromLow, fromHigh, toLow, toHigh)
Mapuje wartość z jednego zakresu do drugiego (liniowo).
```cpp
int brightness = map(potValue, 0, 1023, 0, 255);
```

### constrain(x, a, b)
Ogranicza wartość do zakresu [a, b].
```cpp
int safe = constrain(rawValue, 0, 100);
```

### abs(x) — wartość bezwzględna
### min(a, b), max(a, b) — minimum/maximum
### sq(x) — kwadrat (x*x)
### sqrt(x) — pierwiastek kwadratowy
### pow(base, exponent) — potęgowanie

## Komunikacja szeregowa (Serial)

### Serial.begin(baudrate)
Inicjalizuje UART.
```cpp
void setup() {
    Serial.begin(115200);  // ESP32 domyślnie 115200
    // Serial.begin(9600);  // klasyczny Arduino
    while (!Serial) { delay(10); }  // poczekaj na połączenie (Leonardo/Zero)
}
```

### Serial.print() / Serial.println()
```cpp
Serial.print("Temperatura: ");
Serial.println(temp, 2);  // 2 miejsca po przecinku
Serial.println();          // pusta linia
Serial.printf("T=%.1f°C, RH=%.0f%%\n", temp, hum);  // (ESP32/printf)
```

### Serial.available() / Serial.read()
```cpp
if (Serial.available() > 0) {
    char c = Serial.read();
    // lub: String s = Serial.readStringUntil('\n');
}
```

## I2C — biblioteka Wire

### Wire.begin([address])
Inicjalizuje I2C. Bez adresu = master, z adresem = slave.
```cpp
Wire.begin();         // master
Wire.begin(0x08);     // slave na adresie 0x08
Wire.begin(SDA, SCL); // custom pins (ESP32)
Wire.begin(21, 22);   // SDA=GPIO21, SCL=GPIO22 (ESP32)
Wire.setClock(400000); // Fast Mode 400kHz (po Wire.begin())
```

### Wire.beginTransmission(address) / Wire.endTransmission()
```cpp
Wire.beginTransmission(0x76);  // BME280
Wire.write(0xF3);               // rejestr
int error = Wire.endTransmission();  // 0=sukces
```

### Wire.requestFrom(address, quantity)
Żąda odczytu `quantity` bajtów od urządzenia.
```cpp
Wire.requestFrom(0x76, 2);   // czytaj 2 bajty
while (Wire.available()) {
    byte b = Wire.read();
}
```

### Pełny przykład I2C scan
```cpp
#include <Wire.h>

void setup() {
    Wire.begin(21, 22);  // ESP32 SDA=21, SCL=22
    Serial.begin(115200);
    Serial.println("I2C Scanner:");
    for (byte addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("Znaleziono: 0x%02X\n", addr);
        }
    }
}
```

## SPI — biblioteka SPI

### SPI.begin([sck, miso, mosi, ss])
```cpp
SPI.begin();                    // domyślne piny
SPI.begin(18, 19, 23, 5);      // ESP32: SCK, MISO, MOSI, CS
SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
```

### SPISettings(maxSpeed, dataOrder, dataMode)
- maxSpeed: np. 1000000 (1MHz), 8000000 (8MHz)
- dataOrder: MSBFIRST lub LSBFIRST
- dataMode: SPI_MODE0 (CPOL=0, CPHA=0), SPI_MODE1, SPI_MODE2, SPI_MODE3

### SPI.transfer(data)
```cpp
SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
digitalWrite(CS_PIN, LOW);
byte result = SPI.transfer(0x9F);  // zwraca odczytany bajt
SPI.transfer16(0x1234);            // 16-bitowy transfer
SPI.endTransaction();
digitalWrite(CS_PIN, HIGH);
```

## EEPROM

```cpp
#include <EEPROM.h>

// Arduino Uno: 1024 bajtów
// ESP32: emulowana w Flash, domyślnie 4096 bajtów

// Inicjalizacja (ESP32):
EEPROM.begin(512);

// Zapis/odczyt
EEPROM.write(addr, byte_value);
byte val = EEPROM.read(addr);

// Typy złożone
int intVal = 42;
EEPROM.put(addr, intVal);   // zapisuje sizeof(int) bajtów
EEPROM.get(addr, intVal);   // odczytuje

// ESP32: commit() po zapisie
EEPROM.commit();
```

## Przerwania

```cpp
void IRAM_ATTR buttonISR() {  // IRAM_ATTR = w pamięci RAM (ESP32)
    button_pressed = true;
}

void setup() {
    pinMode(BTN_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BTN_PIN), buttonISR, FALLING);
}
```

## Watchdog (ESP32 Arduino)

```cpp
#include "esp_task_wdt.h"

void setup() {
    esp_task_wdt_init(5, true);     // 5s timeout, panic on trigger
    esp_task_wdt_add(NULL);         // dodaj bieżące zadanie
}

void loop() {
    esp_task_wdt_reset();           // "karm" watchdoga co iterację
    // ... reszta kodu ...
}
```

## Popularne biblioteki Arduino

| Biblioteka | Zastosowanie | Przykład include |
|---|---|---|
| Adafruit_BME280 | Sensor temp/hum/press | `#include <Adafruit_BME280.h>` |
| Adafruit_SSD1306 | OLED 128×64 | `#include <Adafruit_SSD1306.h>` |
| Adafruit_GFX | Grafika dla wyświetlaczy | `#include <Adafruit_GFX.h>` |
| Adafruit_NeoPixel | LED WS2812B | `#include <Adafruit_NeoPixel.h>` |
| DHT sensor library | Sensor DHT11/22 | `#include <DHT.h>` |
| DallasTemperature | Sensor DS18B20 (1-Wire) | `#include <DallasTemperature.h>` |
| OneWire | Protokół 1-Wire | `#include <OneWire.h>` |
| WiFi (ESP32) | Połączenie WiFi | `#include <WiFi.h>` |
| PubSubClient | MQTT klient | `#include <PubSubClient.h>` |
| ArduinoJson | JSON parsing | `#include <ArduinoJson.h>` |
| FastLED | LED strips | `#include <FastLED.h>` |
| Servo | Sterowanie serwami | `#include <Servo.h>` |
| SD | Karta SD przez SPI | `#include <SD.h>` |
| TFT_eSPI | Szybkie TFT LCD | `#include <TFT_eSPI.h>` |

## Debugowanie

```cpp
// Makro debug (wyłączalne)
#define DEBUG 1
#if DEBUG
  #define DBG(x) Serial.println(x)
  #define DBGF(fmt, ...) Serial.printf(fmt, __VA_ARGS__)
#else
  #define DBG(x)
  #define DBGF(fmt, ...)
#endif
```
