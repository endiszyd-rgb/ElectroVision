# FreeRTOS — Wzorce Projektowe dla Embedded

## Podstawy FreeRTOS (ESP32, STM32)

FreeRTOS to preemptywny RTOS z priorytetami 0-configMAX_PRIORITIES-1
(wyższy numer = wyższy priorytet).

---

## Tworzenie tasków

```c
// xTaskCreate — ogólne
BaseType_t xTaskCreate(
    TaskFunction_t pvTaskCode,    // Funkcja taska
    const char * const pcName,   // Nazwa (debug)
    uint32_t usStackDepth,        // Rozmiar stosu (w słowach/bajtach)
    void * pvParameters,          // Parametry przekazane do funkcji
    UBaseType_t uxPriority,       // Priorytet 0-24
    TaskHandle_t * pxCreatedTask  // Handle lub NULL
);

// xTaskCreatePinnedToCore — ESP32 (przypisanie do rdzenia)
xTaskCreatePinnedToCore(
    sensor_task,    // Funkcja
    "sensor",       // Nazwa
    4096,           // Stos: 4096 bajtów
    NULL,           // Brak parametrów
    5,              // Priorytet 5
    &sensor_handle, // Handle
    0               // Rdzeń 0 (Protocol CPU) lub 1 (App CPU)
);

// Usunięcie taska przez siebie:
void my_task(void *pvParam) {
    while (1) {
        // ... praca ...
        if (done) vTaskDelete(NULL);  // NULL = usuń siebie
    }
}
```

---

## Timing (nie używaj delay()!)

```c
// Zła praktyka:
void task(void *p) {
    while(1) {
        do_work();
        vTaskDelay(1000);  // NIE — blokuje na 1000ms, nieregularny timing
    }
}

// Dobra praktyka — stałe okresy:
void task(void *p) {
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(1000);  // 1Hz

    while(1) {
        do_work();
        vTaskDelayUntil(&xLastWake, xPeriod);  // Dokładnie 1000ms od poprzedniego
    }
}
```

---

## Semafory (synchronizacja)

```c
#include "freertos/semphr.h"

// Binary semaphore — sygnalizacja między taskami
SemaphoreHandle_t xSem = xSemaphoreCreateBinary();

// Daj semafor (z ISR):
void IRAM_ATTR gpio_isr(void *arg) {
    xSemaphoreGiveFromISR(xSem, NULL);
}

// Czekaj na semafor (w tasku):
void task(void *p) {
    while(1) {
        if (xSemaphoreTake(xSem, portMAX_DELAY) == pdTRUE) {
            process_gpio_event();
        }
    }
}

// Mutex — chronienie zasobu wspólnego
SemaphoreHandle_t xMutex = xSemaphoreCreateMutex();

void i2c_read(void *p) {
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        // Krytyczna sekcja — tylko jeden task na raz
        HAL_I2C_Master_Receive(&hi2c1, addr, buf, len, HAL_MAX_DELAY);
        xSemaphoreGive(xMutex);
    } else {
        // Timeout — mutex zajęty
        ESP_LOGW(TAG, "I2C mutex timeout!");
    }
}

// Counting semaphore — zliczanie zasobów
SemaphoreHandle_t xCount = xSemaphoreCreateCounting(5, 0);
xSemaphoreGive(xCount);    // Dodaj 1 do licznika
xSemaphoreTake(xCount, 0); // Pobierz (timeout=0 = nie czekaj)
```

---

## Kolejki (Queue) — komunikacja między taskami

```c
#include "freertos/queue.h"

typedef struct {
    float temperature;
    float humidity;
    uint32_t timestamp;
} sensor_data_t;

// Utwórz kolejkę 10 elementów
QueueHandle_t xQueue = xQueueCreate(10, sizeof(sensor_data_t));

// Producent (task sensorowy):
void sensor_task(void *p) {
    sensor_data_t data;
    while(1) {
        data.temperature = bme280_read_temp();
        data.humidity = bme280_read_hum();
        data.timestamp = esp_timer_get_time() / 1000;

        if (xQueueSend(xQueue, &data, pdMS_TO_TICKS(10)) != pdTRUE) {
            ESP_LOGW(TAG, "Queue full — dropped sample");
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

// Konsument (task wyświetlania):
void display_task(void *p) {
    sensor_data_t data;
    while(1) {
        if (xQueueReceive(xQueue, &data, portMAX_DELAY) == pdTRUE) {
            display_update(data.temperature, data.humidity);
        }
    }
}

// Z ISR:
BaseType_t xHigherPriorityTaskWoken = pdFALSE;
xQueueSendFromISR(xQueue, &data, &xHigherPriorityTaskWoken);
portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
```

---

## Event Groups — wiele zdarzeń jednocześnie

```c
#include "freertos/event_groups.h"

#define WIFI_CONNECTED_BIT   BIT0
#define MQTT_CONNECTED_BIT   BIT1
#define SENSOR_READY_BIT     BIT2
#define ALL_READY_BITS       (WIFI_CONNECTED_BIT | MQTT_CONNECTED_BIT | SENSOR_READY_BIT)

EventGroupHandle_t xEvents = xEventGroupCreate();

// Ustaw bit z taska:
xEventGroupSetBits(xEvents, WIFI_CONNECTED_BIT);

// Czekaj na WSZYSTKIE bity:
EventBits_t bits = xEventGroupWaitBits(
    xEvents,
    ALL_READY_BITS,    // Które bity czekamy
    pdTRUE,            // Wyczyść bity po czekaniu
    pdTRUE,            // WSZYSTKIE muszą być (pdFALSE = którykolwiek)
    pdMS_TO_TICKS(30000)  // Timeout 30s
);

if ((bits & ALL_READY_BITS) == ALL_READY_BITS) {
    start_main_loop();
}
```

---

## Timery programowe (Software Timers)

```c
#include "freertos/timers.h"

TimerHandle_t xTimer;

void timer_callback(TimerHandle_t xTimer) {
    static int count = 0;
    count++;
    if (count >= 10) {
        xTimerStop(xTimer, 0);
    }
}

// Utwórz timer jednorazowy (pdFALSE) lub cykliczny (pdTRUE)
xTimer = xTimerCreate(
    "MyTimer",           // Nazwa
    pdMS_TO_TICKS(500),  // Okres: 500ms
    pdTRUE,              // Cykliczny
    NULL,                // ID taska
    timer_callback       // Callback
);
xTimerStart(xTimer, 0);
xTimerChangePeriod(xTimer, pdMS_TO_TICKS(1000), 0);
xTimerStop(xTimer, 0);
xTimerReset(xTimer, 0);
```

---

## Pamięć statyczna (bez malloc)

```c
// Bezpieczna alternatywa — stack i TCB z puli statycznej
StaticTask_t xTaskBuffer;
StackType_t xStack[2048];

TaskHandle_t xHandle = xTaskCreateStatic(
    my_task,
    "static_task",
    2048,
    NULL,
    5,
    xStack,
    &xTaskBuffer
);

// Sprawdzanie użycia stosu:
UBaseType_t free_stack = uxTaskGetStackHighWaterMark(NULL);
ESP_LOGI(TAG, "Free stack: %u words", free_stack);
```

---

## Wzorzec producent-konsument z buforami

```c
// Ping-pong buffer — zero-copy dla danych DMA
typedef struct {
    uint8_t buf[2][DMA_BUFFER_SIZE];
    int current;
    SemaphoreHandle_t ready;
} pingpong_t;

pingpong_t pp = {
    .current = 0,
    .ready = xSemaphoreCreateBinary()
};

// W ISR DMA (przełącz bufor):
void DMA_IRQHandler(void) {
    pp.current ^= 1;  // Przełącz 0/1
    start_dma(pp.buf[pp.current]);  // Nowy transfer
    xSemaphoreGiveFromISR(pp.ready, NULL);
}

// W tasku przetwarzania:
void process_task(void *p) {
    while(1) {
        xSemaphoreTake(pp.ready, portMAX_DELAY);
        int idx = pp.current ^ 1;  // Poprzedni bufor
        process_buffer(pp.buf[idx], DMA_BUFFER_SIZE);
    }
}
```

---

## Typowe priorytety dla ESP32 projektu

```c
#define PRIORITY_IDLE    0   // FreeRTOS idle task
#define PRIORITY_STATS   1   // Statystyki, log
#define PRIORITY_DISPLAY 2   // UI / wyświetlacz
#define PRIORITY_NETWORK 3   // WiFi, MQTT, HTTP
#define PRIORITY_SENSOR  4   // Odczyt sensorów (co 100ms-1s)
#define PRIORITY_CONTROL 5   // Sterowanie wyjściami
#define PRIORITY_REALTIME 6  // Timery, PWM, ekstremalnie czas-krytyczne

// Stosy:
#define STACK_SENSOR  4096   // Sensor + I2C
#define STACK_WIFI    8192   // WiFi stack duży!
#define STACK_DISPLAY 4096   // Wyświetlacz
#define STACK_MAIN    2048   // Prosty task
```

---

## Debugowanie (ESP32)

```c
#include "esp_log.h"
static const char *TAG = "my_module";

ESP_LOGI(TAG, "Info: temp=%.1f", temp);
ESP_LOGW(TAG, "Warning: queue full");
ESP_LOGE(TAG, "Error: I2C timeout after %dms", timeout_ms);
ESP_LOGD(TAG, "Debug: raw ADC=%d", raw);  // Wyłączone w release

// Stack overflow hook:
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName) {
    ESP_LOGE("FreeRTOS", "Stack overflow in task: %s", pcTaskName);
    esp_restart();
}

// Runtime stats:
char stats_buf[2048];
vTaskGetRunTimeStats(stats_buf);
printf("%s\n", stats_buf);
```
