// Werkbanktest: Das DMC haengt nur am ESP, der ESP spielt dem DMC gegenueber den MultiPlus.
//
// Gesendet werden aufgezeichnete MultiPlus-Rahmen (vebus_dmc_replay.h): einmal der Hochlauf, danach endlos
// ein Abschnitt im Zustand Ein. Der Empfang und der TCP-Stream kommen unveraendert aus vebus_sniffer.h, die
// Antworten des DMC erscheinen also wie gewohnt in tools/vebus_capture.py. Der Inhalt ist fest: Die LEDs folgen
// der Aufzeichnung, nicht dem Schalter oder dem Drehknopf des DMC.
//
// Sperre: Vor dem ersten Senden hoert der ESP LISTEN_MS lang zu. Kommt dabei ein Rahmen mit der Adresse
// des MultiPlus an, haengt er am echten VE.Bus und sendet bis zum Neustart nicht.
// Nur auf einer eigenen Leitung zum DMC verwenden, siehe docs/VEBUS-MITSCHNITT.md.

#pragma once

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esphome/core/log.h"

#include "vebus_dmc_replay.h"
#include "vebus_sniffer.h"

namespace vebus_dmc_bench {

static const char *const TAG = "vebus_dmc_bench";
static constexpr uint32_t LISTEN_MS = 5000;

inline int g_tx_pin = 17;
inline std::atomic<uint32_t> g_sent{0}, g_loops{0}, g_foreign{0}, g_multiplus_seen{0};
inline std::atomic<bool> g_sending{false}, g_blocked{false};
inline std::atomic<uint8_t> g_next_nr{0};

// Laeuft in der Empfangstask. Die Rahmennummer teilen sich alle Teilnehmer, das DMC zaehlt mit.
inline void on_frame(const uint8_t *frame, size_t len) {
  if (len < 5) return;
  const bool multiplus = frame[0] == 0x83 && frame[1] == 0x83;
  if (multiplus) {
    if (!g_sending.load()) g_multiplus_seen++;
    return;
  }
  if (frame[2] >= 0xFC && frame[2] <= 0xFE && frame[3] < 0x80) {
    g_foreign++;
    g_next_nr = (frame[3] + 1) & 0x7F;
  }
}

// Setzt Nummer und Pruefsumme, Regeln wie in tools/vebus_make_replay.py.
inline size_t build(const uint8_t *head, size_t len, uint8_t nr, uint8_t *out) {
  memcpy(out, head, len);
  out[3] = nr;
  uint32_t total = 0xFF;
  for (size_t i = 2; i < len; i++) total += out[i];
  if (out[2] == 0xFD && len > 4 && out[4] == 0x55) total -= 0x55;
  const uint8_t value = (uint8_t) (0u - total);
  if (value > 0xFA) {
    out[len++] = 0xFA;
    out[len++] = (uint8_t) (value - 0xFA);
  } else {
    out[len++] = value;
  }
  out[len++] = 0xFF;
  return len;
}

inline void wait_until(int64_t due) {
  for (;;) {
    const int64_t left = due - esp_timer_get_time();
    if (left <= 0) return;
    if (left > 3000) {
      vTaskDelay(1);
    } else {
      esp_rom_delay_us((uint32_t) left);
    }
  }
}

inline void tx_task(void *) {
  while (!uart_is_driver_installed(vebus_sniffer::PORT)) vTaskDelay(pdMS_TO_TICKS(10));
  vTaskDelay(pdMS_TO_TICKS(LISTEN_MS));
  if (g_multiplus_seen.load() > 0) {
    g_blocked = true;
    ESP_LOGE(TAG, "MultiPlus-Rahmen empfangen: Der ESP haengt am echten VE.Bus. Senden gesperrt.");
    vTaskDelete(nullptr);
    return;
  }
  // Erst jetzt bekommt der UART seinen TX-Pin. Der Ruhepegel High laesst den Treiber des Wandlers aus.
  g_sending = true;
  ESP_ERROR_CHECK(uart_set_pin(vebus_sniffer::PORT, g_tx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                               UART_PIN_NO_CHANGE));
  ESP_LOGW(TAG, "Sende aufgezeichnete MultiPlus-Rahmen auf GPIO%d", g_tx_pin);

  uint8_t out[300];
  size_t pos = 0;
  int64_t due = esp_timer_get_time();
  for (;;) {
    const uint8_t *entry = vebus_dmc_replay::DATA + pos;
    const uint16_t delta = (uint16_t) (entry[0] | (entry[1] << 8));
    const uint8_t len = entry[2];
    due += (int64_t) delta * 100;
    wait_until(due);
    const uint8_t nr = g_next_nr.load();
    const size_t n = build(entry + 3, len, nr, out);
    uart_write_bytes(vebus_sniffer::PORT, out, n);
    g_next_nr = (nr + 1) & 0x7F;
    g_sent++;
    pos += 3u + len;
    if (pos >= vebus_dmc_replay::SIZE) {
      pos = vebus_dmc_replay::LOOP_OFFSET;
      g_loops++;
    }
  }
}

inline void start(int rx_pin, int tx_pin) {
  g_tx_pin = tx_pin;
  // Schon beim Zuhoeren fest High: TXD liegt damit sicher im Ruhepegel, der Treiber des Wandlers bleibt aus.
  gpio_set_direction((gpio_num_t) tx_pin, GPIO_MODE_OUTPUT);
  gpio_set_level((gpio_num_t) tx_pin, 1);
  vebus_sniffer::g_on_frame = on_frame;
  vebus_sniffer::start(rx_pin);
  xTaskCreatePinnedToCore(tx_task, "vebus_tx", 4096, nullptr, configMAX_PRIORITIES - 3, nullptr, 1);
}

inline void log_stats() {
  vebus_sniffer::log_stats();
  ESP_LOGI(TAG, "Status %s, gesendet %u, Schleifen %u, Fremdrahmen %u",
           g_blocked.load() ? "GESPERRT" : (g_sending.load() ? "sendet" : "hoert zu"), (unsigned) g_sent.load(),
           (unsigned) g_loops.load(), (unsigned) g_foreign.load());
}

}  // namespace vebus_dmc_bench
