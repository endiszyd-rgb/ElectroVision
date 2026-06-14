# Raspberry Pi Pico / RP2040 — MicroPython Reference

## RP2040 Key Specifications
- Dual-core ARM Cortex-M0+ @ 133MHz
- 264KB SRAM (split into 6 banks)
- External flash: 2MB (Pico) / 4-16MB (W variant)
- 30 GPIO pins (26 exposed on Pico header)
- 2× UART, 2× SPI, 2× I2C, 16× PWM
- 3× 12-bit ADC (ADC0=GP26, ADC1=GP27, ADC2=GP28)
- 8× PIO state machines (2× blocks of 4)
- USB 1.1 host/device (native, no chip needed)
- 3.3V I/O, 5V tolerant inputs: NONE (all 3.3V only!)

---

## GPIO Pinout (Pico)
| GPIO | Special Function |
|------|-----------------|
| GP0  | UART0 TX, I2C0 SDA, SPI0 RX |
| GP1  | UART0 RX, I2C0 SCL, SPI0 CS |
| GP2  | I2C1 SDA, SPI0 SCK |
| GP3  | I2C1 SCL, SPI0 TX |
| GP4  | UART1 TX, I2C0 SDA |
| GP5  | UART1 RX, I2C0 SCL |
| GP6-7| SPI0 SCK/TX |
| GP8-9| I2C0 SDA/SCL |
| GP10-11| SPI1 SCK/TX |
| GP12-13| SPI1 RX/CS |
| GP14-15| SPI1 SCK/TX |
| GP16-17| SPI0 RX/CS |
| GP18-19| SPI0 SCK/TX |
| GP20-21| I2C0 SDA/SCL |
| GP22  | (general GPIO) |
| GP23  | SMPS power save pin (Pico internal) |
| GP24  | VBUS sense (Pico internal) |
| GP25  | LED (Pico onboard LED!) |
| GP26  | ADC0, I2C1 SDA |
| GP27  | ADC1, I2C1 SCL |
| GP28  | ADC2 |
| GP29  | ADC3, VSYS/3 measurement |

---

## Basic GPIO

```python
from machine import Pin

# Onboard LED
led = Pin(25, Pin.OUT)
led.on()
led.off()
led.toggle()

# External button (pull-up)
btn = Pin(15, Pin.IN, Pin.PULL_UP)
if btn.value() == 0:   # Pressed (active low)
    print("Button pressed!")

# Interrupt
btn.irq(trigger=Pin.IRQ_FALLING, handler=lambda p: print("IRQ"))
```

---

## ADC

```python
from machine import ADC, Pin

# Read potentiometer on ADC0
adc = ADC(Pin(26))
val = adc.read_u16()        # 0-65535
voltage = val * 3.3 / 65535  # Convert to volts

# Internal temperature sensor
sensor = ADC(4)             # Channel 4 = internal temp
raw = sensor.read_u16()
voltage_temp = raw * 3.3 / 65535
temp_c = 27 - (voltage_temp - 0.706) / 0.001721
```

---

## I2C

```python
from machine import I2C, Pin

# Hardware I2C (I2C0 default pins)
i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=400_000)

# Hardware I2C (I2C1)
i2c = I2C(1, scl=Pin(27), sda=Pin(26), freq=400_000)

# Scan devices
for addr in i2c.scan():
    print(f"Found device at 0x{addr:02X}")
```

---

## SPI

```python
from machine import SPI, Pin

spi = SPI(0, sck=Pin(18), mosi=Pin(19), miso=Pin(16), baudrate=1_000_000)
cs  = Pin(17, Pin.OUT, value=1)

cs.value(0)
spi.write(b'\x80\x01')
result = spi.read(2)
cs.value(1)
```

---

## UART

```python
from machine import UART, Pin

uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
uart.write('Hello\n')
if uart.any():
    data = uart.read(32)
```

---

## Dual-Core Programming

```python
import _thread
import time

shared_value = 0
lock = _thread.allocate_lock()

def core1_task():
    global shared_value
    while True:
        with lock:
            shared_value += 1
        time.sleep_ms(10)

# Start second core
_thread.start_new_thread(core1_task, ())

while True:
    with lock:
        print("Value:", shared_value)
    time.sleep_ms(100)
```

---

## PIO (Programmable I/O) — State Machine

```python
import rp2
from machine import Pin

# WS2812 PIO program
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=24)
def ws2812():
    T1 = 2; T2 = 5; T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1)            .side(0)    [T3 - 1]
    jmp(not_x, "do_zero").side(1)    [T1 - 1]
    jmp("bitloop")       .side(1)    [T2 - 1]
    label("do_zero")
    nop()                .side(0)    [T2 - 1]
    wrap()

sm = rp2.StateMachine(0, ws2812, freq=8_000_000, sideset_base=Pin(22))
sm.active(1)

# Send pixel data
import array
buf = array.array("I", [0] * 8)
buf[0] = (255 << 16)    # Red pixel
sm.put(buf, 8)

# Pulse generator (1MHz square wave)
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def square_wave():
    set(pins, 1)   [14]
    set(pins, 0)   [14]

sm2 = rp2.StateMachine(1, square_wave, freq=2_000_000, set_base=Pin(2))
sm2.active(1)
```

---

## USB CDC (Serial)

```python
import sys

# Pico appears as serial port via USB CDC (no drivers needed!)
sys.stdout.write("Hello from Pico!\n")
data = sys.stdin.readline()

# Print to USB serial (same as print())
print("Temperature:", 25.3)
```

---

## Flash File System (LittleFS)

```python
import os

os.listdir('/')           # List root files
with open('/data.txt', 'w') as f:
    f.write("hello")

with open('/data.txt', 'r') as f:
    print(f.read())

os.remove('/data.txt')    # Delete file
os.stat('/data.txt')      # File info
```

---

## Watchdog Timer

```python
from machine import WDT

wdt = WDT(timeout=5000)    # 5 second timeout

while True:
    do_work()
    wdt.feed()             # Must be called within 5s
```

---

## Sleep / Power Management

```python
import machine, time

# Regular sleep
time.sleep_ms(100)
time.sleep_us(50)

# Lightsleep (CPU stopped, RAM retained)
machine.lightsleep(5000)   # Sleep 5 seconds

# Deep sleep (RAM lost, restart from main.py)
machine.deepsleep(10000)   # Sleep 10 seconds

# Wake-up source
if machine.reset_cause() == machine.DEEPSLEEP_RESET:
    print("Woke from deep sleep!")
```

---

## I2C Sensors — Common Examples

```python
# MPU-6050 Accelerometer + Gyroscope (I2C addr: 0x68)
from machine import I2C, Pin
import struct

i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=400_000)
i2c.writeto_mem(0x68, 0x6B, b'\x00')   # Wake up MPU6050

def read_mpu6050():
    data = i2c.readfrom_mem(0x68, 0x3B, 14)
    ax, ay, az, temp, gx, gy, gz = struct.unpack('>hhhhhhh', data)
    return ax/16384, ay/16384, az/16384   # g units

# DS3231 RTC (I2C addr: 0x68)
def bcd2dec(bcd):
    return (bcd >> 4) * 10 + (bcd & 0x0F)

def read_ds3231(i2c):
    data = i2c.readfrom_mem(0x68, 0x00, 7)
    sec, mn, hr, _, day, mo, yr = [bcd2dec(b) for b in data]
    return (2000+yr, mo, day, hr, mn, sec)
```
