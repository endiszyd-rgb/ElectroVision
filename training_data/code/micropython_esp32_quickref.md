# MicroPython ESP32 — Quick Reference
Source: docs.micropython.org/en/latest/esp32/quickref.html

## Available GPIO Pins
GPIO: 0-19, 21-23, 25-27, 32-39
- GPIO 34-39: input-only (no pull-up/down, no output)
- GPIO 6-11: reserved for internal SPI flash
- GPIO 0: boot mode (pull-up on boot)

---

## Pins and GPIO

```python
from machine import Pin

# Output
p0 = Pin(2, Pin.OUT)
p0.on(); p0.off()
p0.value(1)         # Set high
p0.value(0)         # Set low
p0.toggle()

# Input with pull-up
p2 = Pin(0, Pin.IN, Pin.PULL_UP)
print(p2.value())   # 0 or 1

# Open-drain output (for I2C emulation)
p3 = Pin(4, Pin.OPEN_DRAIN)

# Drive strength (max current)
p4 = Pin(5, Pin.OUT, drive=Pin.DRIVE_3)  # DRIVE_0=5mA, DRIVE_2=20mA default, DRIVE_3=40mA

# Interrupt on falling edge
def handler(pin):
    print("Edge on", pin)

p2.irq(trigger=Pin.IRQ_FALLING, handler=handler)
p2.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=handler)
```

---

## UART (Serial)

```python
from machine import UART

# UART1 with custom pins
uart = UART(1, baudrate=115200, tx=17, rx=16)
uart.write('Hello\r\n')
if uart.any():
    data = uart.read(64)
    line = uart.readline()      # Read until \n

# RS-485 with MAX485 (DE/RE pin)
de = Pin(4, Pin.OUT)
de.value(1)      # Enable transmit
uart.write(b'\x01\x03\x00\x00\x00\x02\xC4\x0B')  # Modbus RTU
de.value(0)      # Enable receive
```

---

## I2C Bus

```python
from machine import I2C, SoftI2C, Pin

# Hardware I2C (fastest)
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400_000)

# Software I2C (any pins)
i2c = SoftI2C(scl=Pin(5), sda=Pin(4), freq=100_000)

# Scan
devices = i2c.scan()
print([hex(d) for d in devices])

# Write to register
i2c.writeto_mem(0x76, 0xF4, b'\x27')   # BME280 control

# Read from register
data = i2c.readfrom_mem(0x76, 0xF7, 8)  # Read 8 bytes from reg 0xF7

# Full transaction
i2c.writeto(0x3C, b'\x00\xAE')    # SSD1306 display off
buf = bytearray(6)
i2c.readfrom_into(0x68, buf)       # MPU6050 read
```

---

## SPI Bus

```python
from machine import SPI, SoftSPI, Pin

# Hardware SPI (VSPI)
spi = SPI(2, baudrate=10_000_000,
          sck=Pin(18), mosi=Pin(23), miso=Pin(19))

cs = Pin(5, Pin.OUT, value=1)

# Read from SPI device
cs.value(0)
spi.write(b'\x9F')           # Send command
data = spi.read(3)           # Read 3 bytes
cs.value(1)

# Write + Read simultaneously
rxbuf = bytearray(4)
cs.value(0)
spi.write_readinto(b'\x03\x00\x00\x00', rxbuf)
cs.value(1)
```

---

## ADC (Analog Input)

```python
from machine import ADC, Pin

# Basic ADC
adc = ADC(Pin(34))
adc.atten(ADC.ATTN_11DB)    # Full 3.3V range
val = adc.read()            # 0-4095 (12-bit)
mv  = adc.read_uv() // 1000  # Millivolts (calibrated)

# Smoothing (average 16 samples)
def read_avg(adc, n=16):
    return sum(adc.read() for _ in range(n)) // n
```

---

## PWM

```python
from machine import PWM, Pin

# Servo control (50Hz, 1ms-2ms pulse)
servo = PWM(Pin(25), freq=50)
servo.duty_ns(1_500_000)   # 1.5ms = center position

# LED dimmer
led = PWM(Pin(2), freq=1000)
led.duty_u16(32768)         # 50% = half brightness

# Buzzer
buzzer = PWM(Pin(26))
buzzer.freq(440)            # 440 Hz = A4 note
buzzer.duty_u16(32768)
```

---

## Timer

```python
from machine import Timer

# Periodic callback
tim = Timer(0)
counter = [0]

def tick(t):
    counter[0] += 1

tim.init(period=100, mode=Timer.PERIODIC, callback=tick)
tim.deinit()
```

---

## WiFi (ESP32)

```python
import network, time

# Connect to WiFi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect('MySSID', 'password')

# Wait for connection
timeout = 20
while not wlan.isconnected() and timeout > 0:
    time.sleep(1)
    timeout -= 1

if wlan.isconnected():
    ip, mask, gw, dns = wlan.ipconfig('addr4')
    print(f"IP: {ip}")
else:
    print("Connection failed!")

# Access Point mode
ap = network.WLAN(network.AP_IF)
ap.config(ssid='ESP32-AP', password='12345678', authmode=network.AUTH_WPA2_PSK)
ap.active(True)
print("AP IP:", ap.ipconfig('addr4')[0])
```

---

## HTTP Request (urequests)

```python
import urequests

# GET request
r = urequests.get('http://api.example.com/data')
print(r.status_code)
data = r.json()
r.close()

# POST with JSON
import ujson
payload = ujson.dumps({"temp": 25.3, "hum": 60})
r = urequests.post('http://api.example.com/log',
                   data=payload,
                   headers={'Content-Type': 'application/json'})
r.close()
```

---

## NeoPixel (WS2812B)

```python
from machine import Pin
from neopixel import NeoPixel
import time

pin = Pin(4, Pin.OUT)
np  = NeoPixel(pin, 8)     # 8 LEDs

# Solid color
np.fill((255, 0, 0))       # Red
np.write()

# Rainbow
def wheel(pos):
    if pos < 85:
        return (pos*3, 255-pos*3, 0)
    elif pos < 170:
        pos -= 85
        return (255-pos*3, 0, pos*3)
    else:
        pos -= 170
        return (0, pos*3, 255-pos*3)

for i in range(8):
    np[i] = wheel(i * 32)
np.write()
```

---

## OLED SSD1306 Display

```python
from machine import I2C, Pin
import ssd1306

i2c  = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

oled.fill(0)                        # Clear
oled.text('Hello!', 0, 0, 1)       # White text
oled.text('T: 25.3 C', 0, 16, 1)
oled.show()                         # Flush buffer to display
oled.invert(True)                   # Invert colors
```

---

## BME280 Sensor (I2C)

```python
from machine import I2C, Pin
import bme280

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
bme = bme280.BME280(i2c=i2c, address=0x76)

temp, pressure, hum = bme.read_compensated_data()
print(f"T={temp/100:.1f}°C P={pressure//256:.0f}hPa H={hum/1024:.1f}%")
```

---

## PlatformIO platformio.ini examples

```ini
; ESP32 Arduino
[env:esp32]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
    adafruit/Adafruit BME280 Library
    adafruit/Adafruit SSD1306
    bblanchon/ArduinoJson@^7.0.0
    knolleary/PubSubClient@^2.8

; RP2040 (Raspberry Pi Pico)
[env:pico]
platform = raspberrypi
board = pico
framework = arduino
upload_protocol = picotool

; STM32 (Blue Pill)
[env:bluepill]
platform = ststm32
board = bluepill_f103c8
framework = arduino
upload_protocol = stlink

; ATmega328P (Arduino Nano)
[env:nano]
platform = atmelavr
board = nanoatmega328new
framework = arduino
```
