// Passiver VE.Bus-Mitschnitt: liest den RS485-Bus (256000 8N1) nur mit und streamt jeden Rahmen per TCP.
//
// Passiv by design: Der UART bekommt nur einen RX-Pin, es gibt in dieser Firmware keinen TX-Pin und
// keinen Sendepfad. Der Dateneingang des RS485-Moduls liegt fest an VCC (siehe docs/VEBUS-MITSCHNITT.md).
//
// Stream (TCP-Port 8484, ein Client), little endian, je Datensatz:
//   u16 Kennung 0x5AA5 | u32 Zeit in us seit Start (Rahmenende, Genauigkeit ca. 0,2 ms) | u16 Laenge
//   | u8 Flags | Nutzdaten
// Flags: 0 = Rahmen bis einschliesslich 0xFF; 1 = abgeschnitten (Pause oder zu lang, kein 0xFF);
//        2 = Statistik (6 x u32: Rahmen, Sync, Bytes, UART-Fehler, Ueberlaeufe, verworfene Datensaetze)
// Ohne Client werden die Rahmen verworfen und nur gezaehlt. Auswertung: tools/vebus_capture.py.

#pragma once

#include <atomic>
#include <cstring>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/ringbuf.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "esphome/core/log.h"

namespace vebus_sniffer {

static const char *const TAG = "vebus_sniffer";

static constexpr uart_port_t PORT = UART_NUM_2;
static constexpr int BAUD = 256000;
static constexpr uint16_t TCP_PORT = 8484;
static constexpr size_t MAX_FRAME = 300;
static constexpr size_t MAX_RECORD = 600;  // groesster Datensatz im Strom (Flanken aus vebus_edges.h)
static constexpr int64_t GAP_US = 5000;  // Pause innerhalb eines Rahmens: Rest gilt als abgeschnitten
static constexpr size_t HEADER_LEN = 9;
static constexpr size_t RING_SIZE = 32 * 1024;

inline std::atomic<uint32_t> g_frames{0}, g_syncs{0}, g_bytes{0}, g_uart_errors{0}, g_overruns{0}, g_dropped{0};
inline std::atomic<bool> g_client{false};
inline RingbufHandle_t g_ring = nullptr;
inline QueueHandle_t g_events = nullptr;
inline int g_rx_pin = 16;
inline int g_baud = BAUD;  // die Werkbank-Firmware kann eine andere Baudrate vorgeben
inline void (*g_on_frame)(const uint8_t *frame, size_t len) = nullptr;  // nur fuer den Werkbanktest, sonst leer
// Textbefehl vom Mitschnitt-Client (nur Werkbank, fuer Versuche ohne Neuflashen), sonst leer
inline void (*g_on_command)(const char *text) = nullptr;

inline void push_record(uint32_t ts, uint8_t flags, const uint8_t *data, size_t len) {
  uint8_t rec[HEADER_LEN + MAX_RECORD];
  if (len > MAX_RECORD) len = MAX_RECORD;
  rec[0] = 0xA5;
  rec[1] = 0x5A;
  memcpy(rec + 2, &ts, 4);
  rec[6] = (uint8_t) len;
  rec[7] = (uint8_t) (len >> 8);
  rec[8] = flags;
  memcpy(rec + HEADER_LEN, data, len);
  if (xRingbufferSend(g_ring, rec, HEADER_LEN + len, 0) != pdTRUE) g_dropped++;
}

inline void rx_task(void *) {
  // Treiber in dieser Task installieren: Der Interrupt laeuft dann auf Kern 1, weg vom WLAN.
  uart_config_t cfg = {};
  cfg.baud_rate = g_baud;
  cfg.data_bits = UART_DATA_8_BITS;
  cfg.parity = UART_PARITY_DISABLE;
  cfg.stop_bits = UART_STOP_BITS_1;
  cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  cfg.source_clk = UART_SCLK_DEFAULT;
  ESP_ERROR_CHECK(uart_driver_install(PORT, 8192, 0, 64, &g_events, 0));
  ESP_ERROR_CHECK(uart_param_config(PORT, &cfg));
  // Nur RX. Der TX-Pin wird bewusst nicht zugewiesen.
  ESP_ERROR_CHECK(uart_set_pin(PORT, UART_PIN_NO_CHANGE, g_rx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
  gpio_set_pull_mode((gpio_num_t) g_rx_pin, GPIO_PULLUP_ONLY);
  // Kurzer Timeout: Das Rahmenende (Pause auf dem Bus) loest das Ereignis aus, daraus der Zeitstempel.
  uart_set_rx_full_threshold(PORT, 32);
  uart_set_rx_timeout(PORT, 3);
  ESP_LOGI(TAG, "UART2 RX GPIO%d, %d 8N1, nur Empfang", g_rx_pin, g_baud);

  uint8_t frame[MAX_FRAME];
  uint8_t chunk[256];
  size_t len = 0;
  int64_t last = 0;
  uart_event_t ev;
  for (;;) {
    if (xQueueReceive(g_events, &ev, pdMS_TO_TICKS(100)) != pdTRUE) {
      if (len > 0 && esp_timer_get_time() - last > GAP_US) {
        push_record((uint32_t) last, 1, frame, len);
        len = 0;
      }
      continue;
    }
    switch (ev.type) {
      case UART_DATA: {
        const int64_t now = esp_timer_get_time();
        size_t todo = ev.size;
        if (len > 0 && now - last > GAP_US) {
          push_record((uint32_t) last, 1, frame, len);
          len = 0;
        }
        while (todo > 0) {
          const int n = uart_read_bytes(PORT, chunk, todo > sizeof(chunk) ? sizeof(chunk) : todo, 0);
          if (n <= 0) break;
          todo -= (size_t) n;
          g_bytes += (uint32_t) n;
          for (int i = 0; i < n; i++) {
            frame[len++] = chunk[i];
            if (chunk[i] == 0xFF) {
              g_frames++;
              if (len >= 5 && frame[2] == 0xFD && frame[4] == 0x55) g_syncs++;
              if (g_on_frame != nullptr) g_on_frame(frame, len);
              push_record((uint32_t) now, 0, frame, len);
              len = 0;
            } else if (len >= MAX_FRAME) {
              push_record((uint32_t) now, 1, frame, len);
              len = 0;
            }
          }
        }
        last = now;
        break;
      }
      case UART_FIFO_OVF:
      case UART_BUFFER_FULL:
        g_overruns++;
        uart_flush_input(PORT);
        xQueueReset(g_events);
        len = 0;
        break;
      case UART_FRAME_ERR:
      case UART_PARITY_ERR:
      case UART_BREAK:
        g_uart_errors++;
        break;
      default:
        break;
    }
  }
}

inline void push_stats() {
  const uint32_t s[6] = {g_frames.load(), g_syncs.load(), g_bytes.load(), g_uart_errors.load(), g_overruns.load(),
                         g_dropped.load()};
  push_record((uint32_t) esp_timer_get_time(), 2, reinterpret_cast<const uint8_t *>(s), sizeof(s));
}

inline bool send_all(int fd, const uint8_t *p, size_t n) {
  while (n > 0) {
    const int r = lwip_send(fd, p, n, 0);
    if (r <= 0) return false;
    p += r;
    n -= (size_t) r;
  }
  return true;
}

inline void drain_ring() {
  size_t size;
  while (void *item = xRingbufferReceive(g_ring, &size, 0)) vRingbufferReturnItem(g_ring, item);
}

inline void tcp_task(void *) {
  const int listener = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  struct sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(TCP_PORT);
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  int one = 1;
  lwip_setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  if (lwip_bind(listener, (struct sockaddr *) &addr, sizeof(addr)) != 0 || lwip_listen(listener, 1) != 0) {
    ESP_LOGE(TAG, "TCP-Port %u nicht verfuegbar", TCP_PORT);
    vTaskDelete(nullptr);
    return;
  }
  ESP_LOGI(TAG, "TCP-Stream auf Port %u", TCP_PORT);
  for (;;) {
    fd_set rfds;
    FD_ZERO(&rfds);
    FD_SET(listener, &rfds);
    struct timeval to = {0, 200000};
    if (lwip_select(listener + 1, &rfds, nullptr, nullptr, &to) <= 0) {
      drain_ring();  // ohne Client nichts ansammeln
      continue;
    }
    const int fd = lwip_accept(listener, nullptr, nullptr);
    if (fd < 0) continue;
    lwip_setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
    struct timeval sto = {5, 0};
    lwip_setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &sto, sizeof(sto));
    drain_ring();
    g_client = true;
    ESP_LOGI(TAG, "Client verbunden");
    int64_t next_stats = 0;
    for (;;) {
      if (esp_timer_get_time() >= next_stats) {
        push_stats();  // auch bei stillem Bus: So faellt ein toter Client auf
        next_stats = esp_timer_get_time() + 1000000;
      }
      if (g_on_command != nullptr) {
        char cmd[64];
        const int r = lwip_recv(fd, cmd, sizeof(cmd) - 1, MSG_DONTWAIT);
        if (r > 0) {
          cmd[r] = 0;
          push_record((uint32_t) esp_timer_get_time(), 5, reinterpret_cast<const uint8_t *>(cmd), (size_t) r);
          g_on_command(cmd);
        } else if (r == 0) {
          break;  // Client hat geschlossen
        }
      }
      size_t size = 0;
      void *item = xRingbufferReceive(g_ring, &size, pdMS_TO_TICKS(g_on_command != nullptr ? 20 : 200));
      if (item == nullptr) continue;
      const bool ok = send_all(fd, static_cast<const uint8_t *>(item), size);
      vRingbufferReturnItem(g_ring, item);
      if (!ok) break;
    }
    lwip_close(fd);
    g_client = false;
    ESP_LOGI(TAG, "Client getrennt");
  }
}

inline void start(int rx_pin) {
  g_rx_pin = rx_pin;
  g_ring = xRingbufferCreate(RING_SIZE, RINGBUF_TYPE_NOSPLIT);
  xTaskCreatePinnedToCore(rx_task, "vebus_rx", 4096, nullptr, configMAX_PRIORITIES - 2, nullptr, 1);
  xTaskCreatePinnedToCore(tcp_task, "vebus_tcp", 4096, nullptr, 5, nullptr, 0);
}

inline void log_stats() {
  ESP_LOGI(TAG, "Rahmen %u, Sync %u, Bytes %u, UART-Fehler %u, Ueberlaeufe %u, verworfen %u, Client %s",
           (unsigned) g_frames.load(), (unsigned) g_syncs.load(), (unsigned) g_bytes.load(),
           (unsigned) g_uart_errors.load(), (unsigned) g_overruns.load(), (unsigned) g_dropped.load(),
           g_client.load() ? "ja" : "nein");
}

}  // namespace vebus_sniffer
