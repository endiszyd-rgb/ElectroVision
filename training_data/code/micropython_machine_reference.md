# MicroPython — machine Module Complete Reference
Source: docs.micropython.org/en/latest/library/machine.html

## Overview
The `machine` module provides hardware-level functions for microcontroller boards.
Direct misuse can cause "malfunction, lockups, crashes, and in extreme cases, hardware damage."

---

## Memory Access Objects

### `machine.mem8`, `machine.mem16`, `machine.mem32`
Raw memory access using subscript notation with byte addresses.

```python
import machine
from micropython import const

GPIOA = const(0x48000000)
GPIO_BSRR = const(0x18)

# Set PA2 high
machine.mem32[GPIOA + GPIO_BSRR] = 1 << 2
```

---

## Reset Functions

| Function | Purpose |
|----------|---------|
| `machine.reset()` | Hard reset device (like pressing RESET button) |
| `machine.soft_reset()` | Soft reset interpreter, delete Python objects |
| `machine.reset_cause()` | Returns reset cause constant |
| `machine.bootloader([value])` | Enter bootloader mode for firmware programming |

---

## Interrupt Control

```python
state = machine.disable_irq()   # Disable interrupts
# Time-critical work here
machine.enable_irq(state)        # Restore previous state
```

---

## Power Management

| Function | Purpose |
|----------|---------|
| `machine.freq([hz])` | Get/set CPU frequency in hertz |
| `machine.idle()` | Gate CPU clock to reduce power consumption |
| `machine.lightsleep([time_ms])` | Low-power sleep with full RAM retention |
| `machine.deepsleep([time_ms])` | Deep sleep, may lose state |
| `machine.wake_reason()` | Returns wake-up reason (ESP32) |

**Reset cause constants:**
- `machine.PWRON_RESET` — power-on reset
- `machine.HARD_RESET` — hard reset
- `machine.WDT_RESET` — watchdog timer reset
- `machine.DEEPSLEEP_RESET` — wake from deep sleep
- `machine.SOFT_RESET` — soft reset

---

## Pin (GPIO) Class

```python
from machine import Pin

# Basic I/O
p_out = Pin(2, Pin.OUT)          # output
p_in  = Pin(4, Pin.IN, Pin.PULL_UP)  # input with pull-up

p_out.value(1)                   # set high
p_out.on(); p_out.off()          # shorthand
level = p_in.value()             # read 0 or 1

# Interrupt
def callback(pin):
    print("IRQ:", pin)

p_in.irq(trigger=Pin.IRQ_FALLING, handler=callback)

# Toggle
p_out.toggle()
```

**Modes:** `Pin.IN`, `Pin.OUT`, `Pin.OPEN_DRAIN`
**Pull:** `Pin.PULL_UP`, `Pin.PULL_DOWN`, `Pin.PULL_HOLD`
**IRQ triggers:** `Pin.IRQ_FALLING`, `Pin.IRQ_RISING`, `Pin.IRQ_LOW_LEVEL`, `Pin.IRQ_HIGH_LEVEL`

---

## ADC (Analog-to-Digital Converter)

```python
from machine import ADC, Pin

adc = ADC(Pin(34))             # ESP32: only 34-39 for ADC
adc.atten(ADC.ATTN_11DB)       # 0-3.3V range
adc.width(ADC.WIDTH_12BIT)     # 12-bit resolution (0-4095)
value = adc.read()             # 0..4095
voltage = adc.read_uv() / 1e6  # Read in microvolts → volts
```

**Attenuation:**
- `ADC.ATTN_0DB` — 0-1.0V
- `ADC.ATTN_2_5DB` — 0-1.35V
- `ADC.ATTN_6DB` — 0-2.0V
- `ADC.ATTN_11DB` — 0-3.3V

---

## PWM (Pulse Width Modulation)

```python
from machine import PWM, Pin

pwm = PWM(Pin(25))
pwm.freq(1000)          # 1 kHz
pwm.duty(512)           # duty cycle 0-1023 (50%)
pwm.duty_u16(32768)     # duty cycle 0-65535
pwm.duty_ns(500000)     # 500us pulse width in nanoseconds
pwm.deinit()            # stop PWM
```

---

## I2C (Inter-Integrated Circuit)

```python
from machine import I2C, Pin

# Software I2C (any pins)
i2c = I2C(scl=Pin(22), sda=Pin(21), freq=400_000)

# Hardware I2C
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400_000)

# Scan for devices
devices = i2c.scan()         # returns list of 7-bit addresses
print([hex(d) for d in devices])

# Write
i2c.writeto(0x68, b'\x00')  # write byte to address 0x68
i2c.writeto_mem(0x68, 0x6B, b'\x00')  # write register

# Read
data = i2c.readfrom(0x68, 6)            # read 6 bytes
data = i2c.readfrom_mem(0x68, 0x3B, 14)  # read 14 bytes from register 0x3B

# BME280 example
i2c.writeto_mem(0x76, 0xF2, b'\x01')   # osrs_h = 1x
i2c.writeto_mem(0x76, 0xF4, b'\x27')   # osrs_t=1x, osrs_p=1x, mode=normal
data = i2c.readfrom_mem(0x76, 0xF7, 8)
```

---

## SPI (Serial Peripheral Interface)

```python
from machine import SPI, Pin

# Hardware SPI
spi = SPI(1, baudrate=1_000_000, polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(23), miso=Pin(19))

cs = Pin(5, Pin.OUT, value=1)  # CS initially high

# Transfer
cs.value(0)
data = spi.read(4)             # read 4 bytes
spi.write(b'\x9F')             # write command
rxbuf = bytearray(4)
spi.write_readinto(b'\x03\x00\x00\x00', rxbuf)  # full-duplex
cs.value(1)
```

---

## UART (Serial Communication)

```python
from machine import UART

uart = UART(1, baudrate=115200, tx=17, rx=16)
uart = UART(1, baudrate=9600, bits=8, parity=None, stop=1)

uart.write('Hello\r\n')
if uart.any():
    data = uart.read(64)      # read up to 64 bytes
    line = uart.readline()    # read until \n
```

---

## Timer

```python
from machine import Timer

timer = Timer(0)

# Periodic callback (100ms)
def tick(t):
    led.toggle()

timer.init(period=100, mode=Timer.PERIODIC, callback=tick)

# One-shot
timer.init(period=1000, mode=Timer.ONE_SHOT, callback=lambda t: print("done"))

timer.deinit()
```

---

## Watchdog Timer (WDT)

```python
from machine import WDT

wdt = WDT(timeout=2000)  # 2 second timeout

# Must call in loop to prevent reset:
while True:
    do_work()
    wdt.feed()       # reset watchdog timer
```

---

## RTC (Real-Time Clock)

```python
from machine import RTC

rtc = RTC()
rtc.datetime((2024, 1, 15, 1, 12, 30, 0, 0))  # (year, month, day, weekday, h, m, s, subseconds)
print(rtc.datetime())
```

---

## SD Card

```python
import machine, os

sd = machine.SDCard(slot=2, sck=18, mosi=23, miso=19, cs=5)
os.mount(sd, '/sd')
with open('/sd/test.txt', 'w') as f:
    f.write('hello')
os.umount('/sd')
```

---

## Typical ESP32 MicroPython Project Structure

```python
# main.py — boilerplate
import machine
import time
from machine import Pin, I2C, UART, WDT

# Watchdog — 8 seconds
wdt = WDT(timeout=8000)

# Pins
LED = Pin(2, Pin.OUT)
BTN = Pin(0, Pin.IN, Pin.PULL_UP)

# I2C sensor
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400_000)

def setup():
    devices = i2c.scan()
    print("I2C:", [hex(d) for d in devices])

def loop():
    LED.toggle()
    wdt.feed()
    time.sleep_ms(500)

setup()
while True:
    loop()
```
