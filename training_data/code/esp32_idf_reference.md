# ESP-IDF API Reference — GPIO, I2C, SPI, FreeRTOS
# Źródło: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/

## GPIO — Konfiguracja pinów

### Struktura gpio_config_t
```c
typedef struct {
    uint64_t pin_bit_mask;    // maska bitowa pinów (np. (1ULL<<4) | (1ULL<<18))
    gpio_mode_t mode;          // tryb: INPUT, OUTPUT, INPUT_OUTPUT, OUTPUT_OD
    gpio_pullup_t pull_up_en;  // GPIO_PULLUP_ENABLE / DISABLE
    gpio_pulldown_t pull_down_en; // GPIO_PULLDOWN_ENABLE / DISABLE
    gpio_int_type_t intr_type; // typ przerwania
} gpio_config_t;
```

### Tryby GPIO (gpio_mode_t)
```c
GPIO_MODE_DISABLE          // wyłączony
GPIO_MODE_INPUT            // tylko wejście
GPIO_MODE_OUTPUT           // tylko wyjście
GPIO_MODE_OUTPUT_OD        // wyjście open-drain
GPIO_MODE_INPUT_OUTPUT_OD  // wejście + open-drain (I2C!)
GPIO_MODE_INPUT_OUTPUT     // dwukierunkowy
```

### Typy przerwań (gpio_int_type_t)
```c
GPIO_INTR_DISABLE    // brak przerwania
GPIO_INTR_POSEDGE    // zbocze narastające
GPIO_INTR_NEGEDGE    // zbocze opadające
GPIO_INTR_ANYEDGE    // oba zbocza
GPIO_INTR_LOW_LEVEL  // poziom niski
GPIO_INTR_HIGH_LEVEL // poziom wysoki
```

### Funkcje GPIO
```c
// Konfiguracja przez strukturę (zalecane)
esp_err_t gpio_config(const gpio_config_t *pGPIOConfig);

// Konfiguracja indywidualna
esp_err_t gpio_reset_pin(gpio_num_t gpio_num);
esp_err_t gpio_set_direction(gpio_num_t gpio_num, gpio_mode_t mode);
esp_err_t gpio_set_pull_mode(gpio_num_t gpio_num, gpio_pull_mode_t pull);
esp_err_t gpio_pullup_en(gpio_num_t gpio_num);
esp_err_t gpio_pulldown_en(gpio_num_t gpio_num);

// Odczyt/zapis
esp_err_t gpio_set_level(gpio_num_t gpio_num, uint32_t level); // 0=LOW, 1=HIGH
int       gpio_get_level(gpio_num_t gpio_num);                 // zwraca 0 lub 1

// Przerwania
esp_err_t gpio_set_intr_type(gpio_num_t gpio_num, gpio_int_type_t intr_type);
esp_err_t gpio_intr_enable(gpio_num_t gpio_num);
esp_err_t gpio_intr_disable(gpio_num_t gpio_num);
esp_err_t gpio_install_isr_service(int intr_alloc_flags);
esp_err_t gpio_isr_handler_add(gpio_num_t gpio_num, gpio_isr_t handler, void *args);
esp_err_t gpio_isr_handler_remove(gpio_num_t gpio_num);

// Diagnostyka
void gpio_dump_io_configuration(FILE *out, uint64_t io_bit_mask);
```

### Ważne ograniczenia ESP32
- GPIO 6–11: zarezerwowane dla SPI Flash — NIE używać
- GPIO 16–17: zarezerwowane dla PSRAM (jeśli jest)
- GPIO 34–39: tylko wejście, brak pull-up/pull-down hardware
- GPIO 0, 2, 5, 12, 15: strapping pins (ostrożnie przy bootowaniu)
- ADC2 (GPIO 0,2,4,12,13,14,15,25,26,27): niedostępne gdy WiFi aktywne → użyj ADC1

### Przykład — konfiguracja przycisku i LED
```c
#include "driver/gpio.h"

#define LED_PIN   GPIO_NUM_2
#define BTN_PIN   GPIO_NUM_4

void app_main(void)
{
    // LED jako wyjście
    gpio_config_t led_cfg = {
        .pin_bit_mask = (1ULL << LED_PIN),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&led_cfg);

    // Przycisk jako wejście z pull-up
    gpio_config_t btn_cfg = {
        .pin_bit_mask = (1ULL << BTN_PIN),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_NEGEDGE,  // przerwanie przy naciśnięciu
    };
    gpio_config(&btn_cfg);

    // Pętla główna
    while (1) {
        int btn = gpio_get_level(BTN_PIN);
        gpio_set_level(LED_PIN, !btn);  // LED = przeciwny stan przycisku
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
```

---

## I2C — nowoczesne API (ESP-IDF v5.x)

### Konfiguracja magistrali I2C
```c
#include "driver/i2c_master.h"

typedef struct {
    i2c_port_num_t  i2c_port;           // I2C_NUM_0 lub I2C_NUM_1
    gpio_num_t      sda_io_num;          // pin SDA
    gpio_num_t      scl_io_num;          // pin SCL
    i2c_clock_source_t clk_source;       // I2C_CLK_SRC_DEFAULT
    uint8_t         glitch_ignore_cnt;   // typowo 7
    int             intr_priority;       // priorytet przerwania
    size_t          trans_queue_depth;   // głębokość kolejki
    uint32_t        enable_internal_pullup; // 1 = włącz pull-up wewnętrzny
} i2c_master_bus_config_t;

typedef struct {
    i2c_addr_bit_len_t dev_addr_length;  // I2C_ADDR_BIT_LEN_7 (standard)
    uint16_t           device_address;   // adres urządzenia (np. 0x76 dla BME280)
    uint32_t           scl_speed_hz;     // 100000 (standard) lub 400000 (fast)
    uint32_t           scl_wait_us;      // czas oczekiwania (0 = domyślny)
} i2c_device_config_t;
```

### Kluczowe funkcje I2C v5
```c
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *bus_config,
                              i2c_master_bus_handle_t *ret_bus_handle);

esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t bus_handle,
                                     const i2c_device_config_t *dev_config,
                                     i2c_master_dev_handle_t *ret_handle);

esp_err_t i2c_master_transmit(i2c_master_dev_handle_t i2c_dev,
                               const uint8_t *write_buffer, size_t write_size,
                               int xfer_timeout_ms);

esp_err_t i2c_master_receive(i2c_master_dev_handle_t i2c_dev,
                              uint8_t *read_buffer, size_t read_size,
                              int xfer_timeout_ms);

esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t i2c_dev,
                                       const uint8_t *write_buffer, size_t write_size,
                                       uint8_t *read_buffer, size_t read_size,
                                       int xfer_timeout_ms);
```

### Przykład — odczyt rejestru z BME280
```c
#include "driver/i2c_master.h"

#define I2C_SDA  GPIO_NUM_21
#define I2C_SCL  GPIO_NUM_22
#define BME280_ADDR 0x76

void read_bme280_register(uint8_t reg_addr, uint8_t *data, size_t len)
{
    // Konfiguracja magistrali
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port             = I2C_NUM_0,
        .sda_io_num           = I2C_SDA,
        .scl_io_num           = I2C_SCL,
        .clk_source           = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt    = 7,
        .enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

    // Dodanie urządzenia
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address  = BME280_ADDR,
        .scl_speed_hz    = 400000,  // Fast Mode
    };
    i2c_master_dev_handle_t dev;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dev_cfg, &dev));

    // Zapis adresu rejestru + odczyt danych
    ESP_ERROR_CHECK(i2c_master_transmit_receive(dev, &reg_addr, 1, data, len, 100));
}
```

---

## FreeRTOS — zadania i synchronizacja

### Tworzenie zadań
```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Definicja zadania
void my_task(void *pvParameters) {
    while (1) {
        // praca zadania
        vTaskDelay(pdMS_TO_TICKS(1000));  // 1 sekunda
    }
}

// Tworzenie zadania
xTaskCreate(
    my_task,         // funkcja zadania
    "my_task",       // nazwa
    4096,            // rozmiar stosu (słowa)
    NULL,            // parametry
    5,               // priorytet (0=najniższy, configMAX_PRIORITIES-1=najwyższy)
    NULL             // uchwyt (NULL jeśli niepotrzebny)
);

// Na wybranym rdzeniu (ESP32 dual-core)
xTaskCreatePinnedToCore(my_task, "task", 4096, NULL, 5, NULL,
                         0);  // rdzeń 0 (protokół WiFi) lub 1 (aplikacja)
```

### Semafory i mutexy
```c
#include "freertos/semphr.h"

SemaphoreHandle_t mutex = xSemaphoreCreateMutex();

// W zadaniu:
if (xSemaphoreTake(mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    // sekcja krytyczna
    xSemaphoreGive(mutex);
}

// Semafor binarny (np. z ISR do zadania)
SemaphoreHandle_t sem = xSemaphoreCreateBinary();
// W ISR:
xSemaphoreGiveFromISR(sem, &xHigherPriorityTaskWoken);
// W zadaniu:
xSemaphoreTake(sem, portMAX_DELAY);
```

### Kolejki (Queue)
```c
#include "freertos/queue.h"

QueueHandle_t q = xQueueCreate(10, sizeof(int));

// Wysłanie (np. z ISR):
int value = 42;
xQueueSendFromISR(q, &value, NULL);

// Odbiór (w zadaniu):
int received;
xQueueReceive(q, &received, pdMS_TO_TICKS(1000));
```

---

## NVS — Non-Volatile Storage (pamięć flash)

```c
#include "nvs_flash.h"
#include "nvs.h"

// Inicjalizacja
ESP_ERROR_CHECK(nvs_flash_init());

// Zapis
nvs_handle_t h;
nvs_open("storage", NVS_READWRITE, &h);
nvs_set_i32(h, "counter", 42);
nvs_set_str(h, "ssid", "MyWiFi");
nvs_commit(h);
nvs_close(h);

// Odczyt
nvs_open("storage", NVS_READONLY, &h);
int32_t counter = 0;
nvs_get_i32(h, "counter", &counter);
char ssid[64];
size_t ssid_len = sizeof(ssid);
nvs_get_str(h, "ssid", ssid, &ssid_len);
nvs_close(h);
```

---

## WiFi — łączenie z siecią (ESP-IDF v5)

```c
#include "esp_wifi.h"
#include "esp_event.h"
#include "nvs_flash.h"

void wifi_init_sta(const char *ssid, const char *password)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t wifi_cfg = {};
    strncpy((char*)wifi_cfg.sta.ssid,     ssid,     32);
    strncpy((char*)wifi_cfg.sta.password, password, 64);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_connect());
}
```
