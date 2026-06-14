# ESP32 GPIO API — Complete Reference (ESP-IDF)
Source: docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html

## Key ESP32 GPIO Restrictions
- GPIO 6-11: connected to internal SPI flash — DO NOT USE
- GPIO 34-39: input-only (no pull-up/pull-down, no output)
- GPIO 0, 2, 15: affect boot mode — use with care
- GPIO 1, 3: UART0 TX/RX — used for serial programming
- Strapping pins: GPIO 0, 2, 5, 12, 15 — checked at boot

---

## Core Configuration Structure

```c
typedef struct {
    uint64_t         pin_bit_mask;    // Bit mask of GPIOs to configure
    gpio_mode_t      mode;            // GPIO mode
    gpio_pullup_t    pull_up_en;      // Pull-up enable
    gpio_pulldown_t  pull_down_en;    // Pull-down enable
    gpio_int_type_t  intr_type;       // Interrupt type
} gpio_config_t;

// Configure multiple pins at once:
gpio_config_t io_conf = {
    .pin_bit_mask = (1ULL << GPIO_NUM_2) | (1ULL << GPIO_NUM_4),
    .mode = GPIO_MODE_OUTPUT,
    .pull_up_en = GPIO_PULLUP_DISABLE,
    .pull_down_en = GPIO_PULLDOWN_DISABLE,
    .intr_type = GPIO_INTR_DISABLE,
};
ESP_ERROR_CHECK(gpio_config(&io_conf));
```

---

## All GPIO Functions

### Configuration
| Function | Signature | Purpose |
|----------|-----------|---------|
| `gpio_config` | `esp_err_t gpio_config(const gpio_config_t *pGPIOConfig)` | Configure GPIO mode, pull, interrupt |
| `gpio_reset_pin` | `esp_err_t gpio_reset_pin(gpio_num_t gpio_num)` | Reset GPIO to default state |
| `gpio_set_direction` | `esp_err_t gpio_set_direction(gpio_num_t, gpio_mode_t)` | Set direction only |

### Level Control
| Function | Signature | Purpose |
|----------|-----------|---------|
| `gpio_set_level` | `esp_err_t gpio_set_level(gpio_num_t, uint32_t level)` | Set output 0 or 1 |
| `gpio_get_level` | `int gpio_get_level(gpio_num_t gpio_num)` | Read input 0 or 1 |

### Pull Resistors
| Function | Signature | Purpose |
|----------|-----------|---------|
| `gpio_pullup_en` | `esp_err_t gpio_pullup_en(gpio_num_t)` | Enable pull-up |
| `gpio_pullup_dis` | `esp_err_t gpio_pullup_dis(gpio_num_t)` | Disable pull-up |
| `gpio_pulldown_en` | `esp_err_t gpio_pulldown_en(gpio_num_t)` | Enable pull-down |
| `gpio_pulldown_dis` | `esp_err_t gpio_pulldown_dis(gpio_num_t)` | Disable pull-down |
| `gpio_set_pull_mode` | `esp_err_t gpio_set_pull_mode(gpio_num_t, gpio_pull_mode_t)` | Set pull mode |

### Interrupts
| Function | Signature | Purpose |
|----------|-----------|---------|
| `gpio_set_intr_type` | `esp_err_t gpio_set_intr_type(gpio_num_t, gpio_int_type_t)` | Set interrupt trigger |
| `gpio_intr_enable` | `esp_err_t gpio_intr_enable(gpio_num_t)` | Enable interrupt |
| `gpio_intr_disable` | `esp_err_t gpio_intr_disable(gpio_num_t)` | Disable interrupt |
| `gpio_install_isr_service` | `esp_err_t gpio_install_isr_service(int intr_alloc_flags)` | Install ISR service |
| `gpio_isr_handler_add` | `esp_err_t gpio_isr_handler_add(gpio_num_t, gpio_isr_t, void*)` | Add per-pin handler |
| `gpio_isr_handler_remove` | `esp_err_t gpio_isr_handler_remove(gpio_num_t)` | Remove handler |

### Deep Sleep / Hold
| Function | Purpose |
|----------|---------|
| `gpio_hold_en(gpio_num_t)` | Hold GPIO state during sleep |
| `gpio_hold_dis(gpio_num_t)` | Release hold |
| `gpio_deep_sleep_hold_en()` | Hold ALL digital GPIOs during deep sleep |
| `gpio_deep_sleep_hold_dis()` | Release hold on all |

---

## Enumerations

### gpio_mode_t
```c
GPIO_MODE_DISABLE         // Disable input and output
GPIO_MODE_INPUT           // Input only
GPIO_MODE_OUTPUT          // Output only
GPIO_MODE_OUTPUT_OD       // Output open-drain
GPIO_MODE_INPUT_OUTPUT_OD // Input + output open-drain
GPIO_MODE_INPUT_OUTPUT    // Input + output
```

### gpio_int_type_t
```c
GPIO_INTR_DISABLE    // Disable interrupt
GPIO_INTR_POSEDGE    // Rising edge
GPIO_INTR_NEGEDGE    // Falling edge
GPIO_INTR_ANYEDGE    // Both edges
GPIO_INTR_LOW_LEVEL  // Low level trigger
GPIO_INTR_HIGH_LEVEL // High level trigger
```

### gpio_pull_mode_t
```c
GPIO_PULLUP_ONLY      // Pull up only
GPIO_PULLDOWN_ONLY    // Pull down only
GPIO_PULLUP_PULLDOWN  // Both (not recommended)
GPIO_FLOATING         // Floating (no pull)
```

### gpio_drive_cap_t
```c
GPIO_DRIVE_CAP_0          // Weak (5mA)
GPIO_DRIVE_CAP_1          // Medium-weak
GPIO_DRIVE_CAP_2 (DEFAULT)// Medium (20mA)
GPIO_DRIVE_CAP_3          // Strongest (40mA)
```

---

## Complete Examples

### Output + Blink
```c
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define LED_PIN GPIO_NUM_2

void app_main(void) {
    // Configure LED pin as output
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << LED_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));

    while (1) {
        gpio_set_level(LED_PIN, 1);
        vTaskDelay(pdMS_TO_TICKS(500));
        gpio_set_level(LED_PIN, 0);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
```

### Button with Interrupt
```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define BUTTON_PIN GPIO_NUM_0
#define LED_PIN    GPIO_NUM_2

static QueueHandle_t gpio_evt_queue = NULL;

static void IRAM_ATTR gpio_isr_handler(void *arg) {
    uint32_t gpio_num = (uint32_t)arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

static void gpio_task(void *arg) {
    uint32_t io_num;
    while (1) {
        if (xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            printf("GPIO[%ld] intr, val: %d\n", io_num, gpio_get_level(io_num));
            gpio_set_level(LED_PIN, !gpio_get_level(LED_PIN));
        }
    }
}

void app_main(void) {
    gpio_evt_queue = xQueueCreate(10, sizeof(uint32_t));

    // LED output
    gpio_set_direction(LED_PIN, GPIO_MODE_OUTPUT);

    // Button input with interrupt
    gpio_config_t btn_conf = {
        .pin_bit_mask = (1ULL << BUTTON_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    gpio_config(&btn_conf);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(BUTTON_PIN, gpio_isr_handler, (void *)BUTTON_PIN);

    xTaskCreate(gpio_task, "gpio_task", 2048, NULL, 10, NULL);
}
```

### I2C Master (v5 API)
```c
#include "driver/i2c_master.h"

#define I2C_SCL GPIO_NUM_22
#define I2C_SDA GPIO_NUM_21
#define I2C_FREQ 400000
#define BME280_ADDR 0x76

void i2c_init(i2c_master_bus_handle_t *bus, i2c_master_dev_handle_t *dev) {
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = I2C_SDA,
        .scl_io_num = I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, bus));

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = BME280_ADDR,
        .scl_speed_hz = I2C_FREQ,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(*bus, &dev_cfg, dev));
}

void bme280_read(i2c_master_dev_handle_t dev, uint8_t reg, uint8_t *buf, size_t len) {
    ESP_ERROR_CHECK(i2c_master_transmit_receive(dev, &reg, 1, buf, len, -1));
}
```

### FreeRTOS Task
```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

SemaphoreHandle_t xMutex;

void sensor_task(void *pvParam) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(1000);

    while (1) {
        if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            // Read sensor
            xSemaphoreGive(xMutex);
        }
        vTaskDelayUntil(&xLastWakeTime, xPeriod);  // Precise 1Hz timing
    }
}

void app_main(void) {
    xMutex = xSemaphoreCreateMutex();
    xTaskCreatePinnedToCore(sensor_task, "sensor", 4096, NULL, 5, NULL, 0); // Core 0
}
```
