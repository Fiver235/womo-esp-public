// Flankengenaue Aufzeichnung am VE.Bus, als Zusatz zum passiven Mitschnitt (vebus_sniffer.h).
//
// Zweck: Der UART-Mitschnitt zeigt nur Bytes. Das DMC nimmt den Sync des ESP nicht an, obwohl Bytes und Zeitangaben
// mit dem echten Sync uebereinstimmen (docs/VEBUS-MITSCHNITT.md, Ursachensuche FC 0F). Hier misst die RMT-Einheit
// des ESP32 am selben RX-Pin jede Flanke eines Rahmens auf 25 ns. Der UART laeuft daneben unveraendert weiter.
//
// Ein Datensatz (Kennung 6 im Strom, Zeile E im Log): Zeitstempel = Ende des Rahmens plus Ruhezeit IDLE_NS in us,
// Daten = RMT-Symbole zu je 4 Bytes: Dauer0 (15 Bit) und Pegel0, Dauer1 (15 Bit) und Pegel1, Dauer in 25 ns.
// Ein Rahmen beginnt mit der fallenden Flanke des ersten Startbits und endet nach IDLE_NS Ruhe.
// Aufgezeichnet wird nur ein zufaelliger Teil der Rahmen (jeder N-te), sonst wird der Strom zu gross.
// Befehl vom Mitschnitt-Client: E<n> setzt N, E0 schaltet ab.
//
// Nur Empfang. Diese Datei sendet nichts.

#pragma once

#include "driver/rmt_rx.h"
#include "esp_random.h"
#include "esp_rom_gpio.h"
#include "soc/gpio_sig_map.h"

#include "vebus_sniffer.h"

namespace vebus_edges {

static const char *const TAG = "vebus_edges";

static constexpr uint32_t RESOLUTION_HZ = 40000000;  // 25 ns
static constexpr uint32_t IDLE_NS = 300000;          // Ruhe, die einen Rahmen beendet
static constexpr uint32_t GLITCH_NS = 200;           // kuerzere Pulse verwirft die Hardware
static constexpr size_t MAX_SYMBOLS = 256;
static constexpr size_t MAX_SEND_SYMBOLS = 140;      // 560 Bytes, passt in einen Datensatz

struct Event {
  int64_t us;
  size_t symbols;
};

inline std::atomic<int> g_every{3};
inline std::atomic<uint32_t> g_frames{0}, g_sent{0}, g_long{0}, g_errors{0};
inline QueueHandle_t g_queue = nullptr;
inline int g_pin = 16;

inline bool on_done(rmt_channel_handle_t, const rmt_rx_done_event_data_t *data, void *) {
  Event e = {esp_timer_get_time(), data->num_symbols};
  BaseType_t woken = pdFALSE;
  xQueueSendFromISR(g_queue, &e, &woken);
  return woken == pdTRUE;
}

inline void on_command(const char *text) {
  for (const char *p = text; *p != 0; p++) {
    if (*p == 'E' && p[1] >= '0' && p[1] <= '9') g_every = (int) strtol(p + 1, nullptr, 10);
  }
  ESP_LOGW(TAG, "Befehl '%s': Flanken von jedem %d. Rahmen", text, g_every.load());
}

inline void task(void *) {
  // Erst nach dem UART: Der Pin gehoert dann beiden, der UART-Eingang bleibt verbunden.
  while (!uart_is_driver_installed(vebus_sniffer::PORT)) vTaskDelay(pdMS_TO_TICKS(10));
  vTaskDelay(pdMS_TO_TICKS(200));

  static rmt_symbol_word_t symbols[MAX_SYMBOLS];
  rmt_channel_handle_t chan = nullptr;
  rmt_rx_channel_config_t cfg = {};
  cfg.gpio_num = (gpio_num_t) g_pin;
  cfg.clk_src = RMT_CLK_SRC_DEFAULT;
  cfg.resolution_hz = RESOLUTION_HZ;
  cfg.mem_block_symbols = MAX_SYMBOLS;
  rmt_rx_event_callbacks_t cbs = {};
  cbs.on_recv_done = on_done;
  if (rmt_new_rx_channel(&cfg, &chan) != ESP_OK || rmt_rx_register_event_callbacks(chan, &cbs, nullptr) != ESP_OK ||
      rmt_enable(chan) != ESP_OK) {
    ESP_LOGE(TAG, "RMT-Empfang auf GPIO%d laesst sich nicht einrichten", g_pin);
    vTaskDelete(nullptr);
    return;
  }
  gpio_set_pull_mode((gpio_num_t) g_pin, GPIO_PULLUP_ONLY);  // wie in vebus_sniffer.h
  // GPIO16 ist der feste Pin von U2RXD. Der UART nimmt ihn deshalb direkt, ohne die GPIO-Matrix, und die RMT-Einheit
  // schaltet den Pin beim Einrichten auf GPIO um: Der UART empfing danach nichts mehr (erster Lauf 06.11.2026).
  // Hier bekommt der UART sein Signal wieder, diesmal ueber die Matrix wie die RMT-Einheit.
  static_assert(vebus_sniffer::PORT == UART_NUM_2, "Signalnummer unten gilt fuer UART2");
  esp_rom_gpio_connect_in_signal((uint32_t) g_pin, U2RXD_IN_IDX, false);
  ESP_LOGI(TAG, "Flanken auf GPIO%d, 25 ns, jeder %d. Rahmen", g_pin, g_every.load());

  rmt_receive_config_t rx = {};
  rx.signal_range_min_ns = GLITCH_NS;
  rx.signal_range_max_ns = IDLE_NS;
  for (;;) {
    if (rmt_receive(chan, symbols, sizeof(symbols), &rx) != ESP_OK) {
      g_errors++;
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    Event e;
    if (xQueueReceive(g_queue, &e, pdMS_TO_TICKS(1000)) != pdTRUE) continue;  // stiller Bus, Empfang laeuft weiter
    g_frames++;
    const int every = g_every.load();
    if (every <= 0 || !vebus_sniffer::g_client.load()) continue;
    if (every > 1 && esp_random() % (uint32_t) every != 0) continue;
    size_t n = e.symbols;
    if (n > MAX_SEND_SYMBOLS) {
      g_long++;
      n = MAX_SEND_SYMBOLS;
    }
    vebus_sniffer::push_record((uint32_t) e.us, 6, reinterpret_cast<const uint8_t *>(symbols), n * 4);
    g_sent++;
  }
}

inline void start(int rx_pin, int every) {
  g_pin = rx_pin;
  g_every = every;
  g_queue = xQueueCreate(4, sizeof(Event));
  vebus_sniffer::g_on_command = on_command;
  // Kern 1 wie die Empfangstask, aber niedrigere Prioritaet: Der UART-Mitschnitt geht vor.
  xTaskCreatePinnedToCore(task, "vebus_edges", 4096, nullptr, configMAX_PRIORITIES - 4, nullptr, 1);
}

inline void log_stats() {
  ESP_LOGI(TAG, "Rahmen %u, gesendet %u, gekuerzt %u, Fehler %u", (unsigned) g_frames.load(), (unsigned) g_sent.load(),
           (unsigned) g_long.load(), (unsigned) g_errors.load());
}

}  // namespace vebus_edges
