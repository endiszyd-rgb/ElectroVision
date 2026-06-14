# Wzory Elektroniczne — Kompletna Ściągawka

## Prawo Ohma i moc
```
U = I × R         (napięcie = prąd × oporność)
P = U × I         (moc = napięcie × prąd)
P = I² × R        (moc w rezystorze)
P = U² / R
```

## Dzielnik napięcia
```
U_out = U_in × R2 / (R1 + R2)

Przykład: U_in=5V, chcemy U_out=3.3V:
Stosunek: R2/(R1+R2) = 3.3/5 = 0.66
Np. R1=10kΩ, R2=20kΩ → U_out = 5 × 20/(10+20) = 3.33V ✓
```

## Rezystor dla LED
```
R = (U_zasilanie - U_forward) / I_LED

Typowe wartości:
- LED czerwona: U_f = 1.8-2.2V, I = 10-20mA
- LED zielona:  U_f = 2.0-2.4V
- LED niebieska: U_f = 2.8-3.4V
- LED biała:    U_f = 3.0-3.6V

Przykład: 5V, LED czerwona 2V, 10mA:
R = (5 - 2) / 0.010 = 300Ω → użyj 330Ω
```

## Kondensatory filtrujące zasilanie
```
Reguła ogólna:
- 100nF (0.1µF) ceramiczny: przy każdym IC (szyna zasilania)
- 10µF elektrolityczny: przy każdym LDO / główna szyna
- 100µF: na wejściu zasilacza, przy przetwornicach

Wzór: C = I_peak × t_spike / ΔU
- I_peak = szczytowy prąd obciążenia
- t_spike = czas spike'u (np. 1µs dla MCU)
- ΔU = dopuszczalne odchylenie napięcia (np. 50mV)
```

## Filtr RC (dolnoprzepustowy)
```
f_c = 1 / (2π × R × C)    ← częstotliwość graniczna

Przykład: f_c = 1kHz, C = 100nF:
R = 1 / (2π × 1000 × 100e-9) = 1592Ω ≈ 1.5kΩ

Zastosowanie: filtrowanie sygnału ADC, wygładzanie PWM do analogowego
```

## Filtr RC (górnoprzepustowy)
```
f_c = 1 / (2π × R × C)    ← ta sama formuła
Przepuszcza: f > f_c
Blokuje: f < f_c (składowa stała)
```

## Przekształtnik Buck (Step-Down)
```
Stosunek wypełnienia: D = U_out / U_in
Indukcyjność: L = (U_in - U_out) × D / (f × ΔI_L)
  f = częstotliwość przełączania (np. 300kHz)
  ΔI_L = ripple prądu (20-40% I_max)

Kondensator wyjściowy:
  C_out = ΔI_L / (8 × f × ΔU_out)

Przykład: Buck 12V→5V, I=2A, f=300kHz, ΔI_L=0.5A, ΔU=50mV:
  D = 5/12 = 0.417
  L = (12-5) × 0.417 / (300e3 × 0.5) = 19.5µH ≈ 22µH
  C = 0.5 / (8 × 300e3 × 0.05) = 4.2µF ≈ 10µF
```

## Przekształtnik Boost (Step-Up)
```
D = 1 - U_in / U_out
L = U_in × D / (f × ΔI_L)
```

## Impedancja ścieżek PCB (mikrostrip)
```
50Ω mikrostrip (FR4, er=4.4):
  Szerokość W = 1.9mm dla grubości dielektryka h=1.0mm (4-warstwy, core)
  W = 2.8mm dla h=1.6mm (2-warstwy)

Wzór IPC-2141A:
  Z0 = (87 / √(er+1.41)) × ln(5.98×h / (0.8×W + T))
  er = 4.4 (FR4), T = grubość miedzi

USB D+/D-: 90Ω impedancja różniczkowa (para)
LVDS: 100Ω impedancja różniczkowa
```

## Szerokość ścieżki (IPC-2221A)
```
Ścieżka zewnętrzna (zewn. warstwy):
  W = (I / (k × ΔT^0.44))^(1/0.725) / (A^0.725)
  gdzie A = przekrój [mil²], k=0.048, ΔT = wzrost temp.

Tabela uproszczona (miedź 1oz, wzrost +10°C):
  0.5A → 0.2mm
  1A   → 0.3mm
  2A   → 0.6mm
  3A   → 1.0mm
  5A   → 1.7mm
  10A  → 3.5mm
  15A  → 5.0mm
  20A  → 7.0mm

Ścieżki wewnętrzne (k=0.024 → 2× szerzej niż zewnętrzne)
```

## Antena PCB (ESP32, 2.4GHz)
```
λ/4 monopool: L = 75mm / √er (dla er=4.4: ~30mm)
PIFA (inverted-F): 31mm długość, 6mm podniesienie nad GND
Trace antenna wbudowana w ESP32-WROOM: 3.5dBi gain
Reguły:
- Keep-out GND pod anteną: min 15mm każda strona
- Nie umieszczaj komponentów w obszarze anteny
- Rezystor 0Ω szeregowo na antenie zewnętrznej/IPEX
```

## Pull-up dla I2C
```
Wartości pull-up (VCC do SDA/SCL):
- 100kHz standard: 10kΩ
- 400kHz fast:     4.7kΩ (zalecane)
- 1MHz fast-plus:  1kΩ

Wzór max R_pull: R_max = (VCC - 0.4) / 3mA = (3.3-0.4)/0.003 = 967Ω
Wzór min R_pull: t_r / (0.8473 × C_bus)
C_bus = 100pF typowo → t_r/84pF
```

## Watchdog timer
```
t_WDT_timeout = prescaler × reload / f_WDT_clock

Przykład STM32 IWDG:
  f_clock = 40kHz (LSI oscillator)
  prescaler = 64
  reload = 625
  timeout = 64 × 625 / 40000 = 1.0s

Przykład Arduino (ESP32):
  esp_task_wdt_init(5, true);  // 5 sekund timeout
  esp_task_wdt_add(NULL);      // rejestracja tasku
  esp_task_wdt_reset();        // feed co <5s
```

## Napięcia odcięcia baterii (Li-Ion/Li-Po)
```
Nominalnie:    3.7V (Li-Ion), 3.8V (Li-Po)
Pełne ładowanie: 4.2V (standardowe), 4.35V (high capacity)
Odcięcie rozładowania: 3.0V (absolutne min), 3.3-3.5V (zalecane)

1S (1 ogniwo): 3.0-4.2V
2S (2 ogniwa): 6.0-8.4V
Ładowanie CC/CV: I_ładow = 0.5-1C
  dla 2000mAh → 1000-2000mA, napięcie 4.2V

Pomiar SoC przez ADC:
  U_baterii = U_ADC × (R1+R2) / R2  (dzielnik napięcia)
```

## Cewki i transformatory
```
Indukcyjność cewki powietrznej:
  L = (μ₀ × N² × A) / l
  N = ilość zwojów, A = pole przekroju [m²], l = długość [m]

Reaktancja indukcyjna: X_L = 2π × f × L

Ferrite bead (koraliki ferrytowe) — filtrowanie EMI:
  Impedancja w paśmie 100MHz: 100-1000Ω
  Montaż: szeregowo na linii zasilania MCU
  Wartość: 600Ω@100MHz (typowe dla 50mA ścieżek)
```

## Sensory — typowe wartości
```
NTC termistor 10kΩ (B=3950):
  R_T = R_0 × exp(B × (1/T - 1/T_0))
  T_0 = 298.15K (25°C), R_0 = 10kΩ
  Schemat: dzielnik z R_fixed=10kΩ

ACS712-5A (prąd AC/DC):
  Czułość: 185mV/A
  Offset: VCC/2 = 2.5V (przy 5V zasilaniu)
  I = (U_out - 2.5) / 0.185

INA226 (moc przez shunt):
  Shunt 0.1Ω, max 3.2A
  Programowalny wzmacniacz 1/4/16/64x
  I2C adres: 0x40-0x4F (A0,A1 piny)
  Resolution: 2.5µA/LSB przy shuncie 0.1Ω
```

## Pojemność przez PCB (pasożytnicza)
```
Ścieżka równoległa do ścieżki:
  C = 0.055 × W × L / h [pF]
  W, L, h w mm, W=szerokość, L=długość, h=odległość między ścieżkami

Pad nad płaszczyzną GND:
  C ≈ er × A / (4π × k × h) [pF]
  er=4.4, A w mm², h=grubość dielektryka

Typowo: 1-3pF/cm ścieżki 0.5mm na FR4
```
