// Uebersetzung DMC <-> Color Control GX. Das DMC haengt nur am ESP, der ESP spielt ihm gegenueber den MultiPlus.
//
// Zum DMC: Sync und uebrige Rahmen kommen aus der Aufzeichnung (vebus_dmc_replay.h), den LED-Rahmen 0x41 erzeugt
// die Firmware aus dem echten Zustand, den sie per Modbus TCP vom GX liest. Ohne Daten vom GX bleiben die LEDs aus.
// Vom DMC: Aendert sich die Schalterstellung oder die Stromgrenze im Rahmen 0x40, schreibt die Firmware EINMAL
// Register 33 (/Mode) oder 22 (Stromgrenze). Der erste Rahmen nach dem Start des DMC setzt nur den Ausgangswert und
// schreibt nichts: So gilt "letzter Befehl gewinnt", und ein Neustart schaltet den MultiPlus nicht.
//
// Geschrieben wird nur mit write_enable = true, sonst steht der geplante Befehl nur im Log.
// Die LEDs Ueberlast, Batterie und Temperatur werden noch nicht abgeleitet. Der Rahmen 0x38 auf FC 0F ist ein
// Versuch aus dem Mitschnitt, seine Bedeutung ist nicht dokumentiert.
// Nur auf einer eigenen Leitung zum DMC verwenden, siehe docs/VEBUS-MITSCHNITT.md.

#pragma once

#include <cerrno>
#include <cstdio>
#include <fcntl.h>

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "vebus_dmc_bench.h"

namespace vebus_dmc_bridge {

static const char *const TAG = "vebus_dmc_bridge";
using vebus_dmc_bench::build;
using vebus_dmc_bench::wait_until;

static constexpr uint16_t REG_LIMIT = 22, REG_STATE = 31, REG_MODE = 33;
static constexpr int64_t GX_STALE_US = 10 * 1000000;
static constexpr int64_t DMC_LOST_US = 3 * 1000000;
static constexpr int64_t SWITCH_STABLE_US = 300 * 1000;
static constexpr int64_t LIMIT_STABLE_US = 1500 * 1000;
static constexpr int64_t POLL_US = 1000 * 1000;
static constexpr int64_t RETRY_US = 2000 * 1000;
static constexpr int MAX_TRIES = 5;
static constexpr uint16_t LIMIT_MIN = 31, LIMIT_MAX = 160;  // 0,1 A; Bereich laut Rahmen 0x41 im Mitschnitt

inline const char *g_gx_ip = "";
inline uint8_t g_unit = 246;
inline bool g_write_enable = false;
inline int g_tx_pin = 17;

// Vom GX
inline std::atomic<uint16_t> g_gx_limit{0}, g_gx_state{0}, g_gx_mode{0};
inline std::atomic<int64_t> g_gx_ok_us{0};
// Vom DMC, gesetzt in der Empfangstask
inline std::atomic<uint8_t> g_dmc_pos{0};
inline std::atomic<uint16_t> g_dmc_limit{0};
inline std::atomic<int64_t> g_dmc_us{0};
inline std::atomic<uint32_t> g_panel_ok{0}, g_panel_bad{0}, g_fc0f{0};
inline std::atomic<bool> g_want_38{false};
// Sendeseite
inline std::atomic<uint8_t> g_next_nr{0};
inline std::atomic<bool> g_sending{false}, g_blocked{false};
inline std::atomic<uint32_t> g_busy_waits{0}, g_busy_timeouts{0};
inline std::atomic<uint32_t> g_multiplus_seen{0}, g_sent{0}, g_loops{0}, g_sent38{0};
inline std::atomic<uint32_t> g_writes_ok{0}, g_writes_failed{0}, g_gx_errors{0};

// ---------------------------------------------------------------------- Empfang
inline void parse_panel(const uint8_t *frame, size_t len) {
  uint32_t total = 0;
  for (size_t i = 2; i < len; i++) total += frame[i];
  if ((total & 0xFF) != 0) {
    g_panel_bad++;
    return;
  }
  uint8_t plain[8];  // Daten ab dem Byte nach 0x40, ohne Pruefsumme und FF
  size_t n = 0;
  const size_t end = (len >= 3 && frame[len - 3] == 0xFA) ? len - 3 : len - 2;
  for (size_t i = 5; i < end && n < sizeof(plain); i++) {
    if (frame[i] == 0xFA && i + 1 < end) {
      plain[n++] = (uint8_t) (frame[++i] + 0x80);
    } else {
      plain[n++] = frame[i];
    }
  }
  if (n < 3 || !(plain[0] & 0x08)) {  // nur das erweiterte Format wie im Mitschnitt
    g_panel_bad++;
    return;
  }
  g_dmc_pos = plain[0] & 0x03;
  g_dmc_limit = (uint16_t) (plain[1] | (plain[2] << 8));
  g_dmc_us = esp_timer_get_time();
  g_panel_ok++;
}

inline void on_frame(const uint8_t *frame, size_t len) {
  if (len < 5) return;
  if (frame[0] == 0x83 && frame[1] == 0x83) {
    if (!g_sending.load()) g_multiplus_seen++;
    return;
  }
  if (frame[2] < 0xFC || frame[2] > 0xFE || frame[3] >= 0x80) return;
  g_next_nr = (frame[3] + 1) & 0x7F;
  if (frame[0] != 0xF0 || frame[1] != 0xF7) return;
  if (frame[2] == 0xFE && frame[4] == 0x40) parse_panel(frame, len);
  if (frame[2] == 0xFC && frame[4] == 0x0F) {
    g_fc0f++;
    g_want_38 = true;
  }
}

// ---------------------------------------------------------------------- Senden
inline uint8_t leds_from_state(uint16_t state) {
  // Bits laut MK2-Dokument: 0 Netz, 1 Absorption, 2 Bulk, 3 Float, 4 Wechselrichter. Zuordnung wie im Mitschnitt.
  switch (state) {
    case 3: return 0x05;  // Bulk
    case 4: return 0x03;  // Absorption
    case 5: return 0x09;  // Float
    case 6: return 0x09;  // Storage
    case 7: return 0x03;  // Equalize
    case 8: return 0x01;  // Durchleitung
    case 9: return 0x10;  // Wechselrichter
    case 10: return 0x11;  // Assist
    default: return 0x00;  // Aus, Low Power, Fehler, unbekannt
  }
}

inline size_t put(uint8_t *out, size_t n, uint8_t b) {
  if (b >= 0xFA) {
    out[n++] = 0xFA;
    out[n++] = (uint8_t) (b - 0x80);
  } else {
    out[n++] = b;
  }
  return n;
}

// Kopf und kodierte Daten des LED-Rahmens, aufgebaut wie 8383 FE nr 41 10 05 00 00 94 1F 00 A0 00 A0 00 77
inline size_t head_41(uint8_t *h) {
  const bool fresh = esp_timer_get_time() - g_gx_ok_us.load() < GX_STALE_US && g_gx_ok_us.load() != 0;
  const uint16_t mode = g_gx_mode.load();
  const uint8_t led = fresh ? leds_from_state(g_gx_state.load()) : 0;
  const uint16_t limit = fresh ? g_gx_limit.load() : 0;
  uint8_t sw = 0x77;
  uint16_t lmin = LIMIT_MIN;
  if (fresh && mode == 4) {
    sw = 0x44;
    lmin = 0;
  } else if (fresh && mode == 1) {
    sw = 0x55;
    lmin = 0;
  }
  const uint8_t data[] = {0x41, 0x10, led, 0x00, 0x00, 0x94, (uint8_t) lmin, (uint8_t) (lmin >> 8),
                          (uint8_t) LIMIT_MAX, (uint8_t) (LIMIT_MAX >> 8), (uint8_t) limit, (uint8_t) (limit >> 8),
                          sw};
  size_t n = 0;
  h[n++] = 0x83;
  h[n++] = 0x83;
  h[n++] = 0xFE;
  h[n++] = 0x00;  // Nummer setzt build()
  for (uint8_t b : data) n = put(h, n, b);
  return n;
}

// Erst hoeren, dann senden. Das DMC sendet in seinem eigenen Takt, der ESP spielt die Aufzeichnung ab. Ohne diese
// Pruefung faellt der ESP dem DMC ins Wort (Mitschnitt 05.11.2026 23:59: 29 gestoerte 0x40 in 3 min, das DMC
// blinkt dabei kurz mit Wechselrichter, Float und Bulk). Der eigene Rahmen kommt nicht zurueck auf RX (der Wandler
// schaltet beim Senden den Empfaenger ab), Pegel Low auf RX heisst also: das DMC sendet.
// Frei ist die Leitung nach IDLE_US am Stueck High. Innerhalb eines Rahmens sind es hoechstens 9 Bit (35 us). 80 us
// reichten nicht: Der ESP draengte sich in die Luecken zwischen den FC-0F-Rahmen (999 gestoerte statt 320).
static constexpr int64_t IDLE_US = 300;  // laenger als die Pause zwischen den FC-0F-Rahmen des DMC (~0,1 ms)
static constexpr int64_t BUSY_MAX_US = 5000;

inline void wait_bus_idle() {
  uart_wait_tx_done(vebus_sniffer::PORT, pdMS_TO_TICKS(10));  // eigener Rahmen ganz draussen
  const gpio_num_t rx = (gpio_num_t) vebus_sniffer::g_rx_pin;
  const int64_t start = esp_timer_get_time();
  int64_t high_since = start;
  bool busy = false;
  for (;;) {
    const int64_t now = esp_timer_get_time();
    if (gpio_get_level(rx) == 0) {
      high_since = now;
      busy = true;
    } else if (now - high_since >= IDLE_US) {
      break;
    }
    if (now - start > BUSY_MAX_US) {
      g_busy_timeouts++;
      break;
    }
  }
  if (busy) g_busy_waits++;
}

inline void send_frame(const uint8_t *head, size_t len) {
  uint8_t out[64];
  wait_bus_idle();
  const uint8_t nr = g_next_nr.load();
  const size_t n = build(head, len, nr, out);
  uart_write_bytes(vebus_sniffer::PORT, out, n);
  g_next_nr = (nr + 1) & 0x7F;
  g_sent++;
}

inline void tx_task(void *) {
  while (!uart_is_driver_installed(vebus_sniffer::PORT)) vTaskDelay(pdMS_TO_TICKS(10));
  vTaskDelay(pdMS_TO_TICKS(vebus_dmc_bench::LISTEN_MS));
  if (g_multiplus_seen.load() > 0) {
    g_blocked = true;
    ESP_LOGE(TAG, "MultiPlus-Rahmen empfangen: Der ESP haengt am echten VE.Bus. Senden gesperrt.");
    vTaskDelete(nullptr);
    return;
  }
  g_sending = true;
  ESP_ERROR_CHECK(uart_set_pin(vebus_sniffer::PORT, g_tx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                               UART_PIN_NO_CHANGE));
  ESP_LOGW(TAG, "Sende an das DMC auf GPIO%d", g_tx_pin);

  static const uint8_t HEAD_38[] = {0x83, 0x83, 0xFE, 0x00, 0x38, 0x01, 0xC0, 0xC0};
  uint8_t head[32];
  size_t pos = 0;
  int64_t due = esp_timer_get_time();
  int64_t last_38 = 0;
  for (;;) {
    const uint8_t *entry = vebus_dmc_replay::DATA + pos;
    const uint16_t delta = (uint16_t) (entry[0] | (entry[1] << 8));
    const uint8_t len = entry[2];
    const uint8_t *rec = entry + 3;
    due += (int64_t) delta * 100;
    wait_until(due);
    if (len >= 5 && rec[2] == 0xFE && rec[4] == 0x41) {
      const size_t n = head_41(head);
      send_frame(head, n);
    } else {
      send_frame(rec, len);
    }
    pos += 3u + len;
    if (pos >= vebus_dmc_replay::SIZE) {
      pos = vebus_dmc_replay::LOOP_OFFSET;
      g_loops++;
    }
    const int64_t now = esp_timer_get_time();
    if (g_want_38.exchange(false) && now - last_38 > 200000) {
      uart_wait_tx_done(vebus_sniffer::PORT, pdMS_TO_TICKS(5));
      esp_rom_delay_us(300);
      send_frame(HEAD_38, sizeof(HEAD_38));
      g_sent38++;
      last_38 = now;
    }
  }
}

// ---------------------------------------------------------------------- Modbus
inline int gx_connect() {
  const int s = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (s < 0) return -1;
  struct sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(502);
  if (inet_pton(AF_INET, g_gx_ip, &addr.sin_addr) != 1) {
    lwip_close(s);
    return -1;
  }
  const int flags = lwip_fcntl(s, F_GETFL, 0);
  lwip_fcntl(s, F_SETFL, flags | O_NONBLOCK);
  int r = lwip_connect(s, (struct sockaddr *) &addr, sizeof(addr));
  if (r != 0 && errno != EINPROGRESS) {
    lwip_close(s);
    return -1;
  }
  if (r != 0) {
    fd_set wfds;
    FD_ZERO(&wfds);
    FD_SET(s, &wfds);
    struct timeval to = {2, 0};
    r = lwip_select(s + 1, nullptr, &wfds, nullptr, &to);
    int so_error = 0;
    socklen_t sl = sizeof(so_error);
    if (r <= 0 || lwip_getsockopt(s, SOL_SOCKET, SO_ERROR, &so_error, &sl) != 0 || so_error != 0) {
      lwip_close(s);
      return -1;
    }
  }
  lwip_fcntl(s, F_SETFL, flags);
  struct timeval tv = {2, 0};
  lwip_setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
  lwip_setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
  return s;
}

inline bool recv_all(int s, uint8_t *p, size_t n) {
  while (n > 0) {
    const int r = lwip_recv(s, p, n, 0);
    if (r <= 0) return false;
    p += r;
    n -= (size_t) r;
  }
  return true;
}

// Funktion 03 (lesen) oder 06 (schreiben), jeweils ein Register. value: Antwortwert bzw. zu schreibender Wert.
inline bool transact(int s, uint8_t fc, uint16_t reg, uint16_t *value) {
  static uint16_t tid = 0;
  const uint16_t t = ++tid;
  const uint16_t arg = fc == 3 ? 1 : *value;
  const uint8_t req[12] = {(uint8_t) (t >> 8), (uint8_t) t, 0, 0, 0, 6, g_unit, fc,
                           (uint8_t) (reg >> 8), (uint8_t) reg, (uint8_t) (arg >> 8), (uint8_t) arg};
  if (lwip_send(s, req, sizeof(req), 0) != (int) sizeof(req)) return false;
  uint8_t head[7];
  if (!recv_all(s, head, sizeof(head))) return false;
  const size_t pdu_len = (size_t) ((head[4] << 8) | head[5]);
  if (pdu_len < 2 || pdu_len > 16 || ((head[0] << 8) | head[1]) != t) return false;
  uint8_t pdu[16];
  if (!recv_all(s, pdu, pdu_len - 1)) return false;
  if (pdu[0] != fc) return false;  // auch Modbus-Ausnahme
  if (fc == 3) {
    if (pdu[1] != 2 || pdu_len < 5) return false;
    *value = (uint16_t) ((pdu[2] << 8) | pdu[3]);
  }
  return true;
}

struct Pending {
  bool active = false;
  uint16_t reg = 0, value = 0;
  int tries = 0;
  int64_t next_us = 0;
};

inline void plan_write(Pending &p, uint16_t reg, uint16_t value) {
  if (!g_write_enable) {
    ESP_LOGW(TAG, "Schreiben ist abgeschaltet: Register %u waere jetzt %u", reg, value);
    return;
  }
  p.active = true;  // ein neuerer Befehl ersetzt einen noch nicht gesendeten
  p.reg = reg;
  p.value = value;
  p.tries = 0;
  p.next_us = 0;
  ESP_LOGW(TAG, "Befehl vom DMC: Register %u = %u", reg, value);
}

inline void gx_task(void *) {
  int s = -1;
  Pending mode, limit;
  bool baseline = false;
  uint8_t base_pos = 0, seen_pos = 0;
  uint16_t base_limit = 0, seen_limit = 0;
  int64_t pos_since = 0, limit_since = 0, next_poll = 0;

  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(100));
    const int64_t now = esp_timer_get_time();

    // DMC auswerten: Der erste Rahmen nach einer Pause setzt nur den Ausgangswert.
    const int64_t dmc_us = g_dmc_us.load();
    if (dmc_us == 0 || now - dmc_us > DMC_LOST_US) {
      if (baseline) ESP_LOGW(TAG, "Keine Rahmen mehr vom DMC");
      baseline = false;
    } else {
      const uint8_t pos = g_dmc_pos.load();
      const uint16_t lim = g_dmc_limit.load();
      if (!baseline) {
        baseline = true;
        base_pos = seen_pos = pos;
        base_limit = seen_limit = lim;
        pos_since = limit_since = now;
        ESP_LOGI(TAG, "DMC da: Schalterstellung %u, Grenze %u (0,1 A), Ausgangswert ohne Schreiben", pos, lim);
      }
      if (pos != seen_pos) {
        seen_pos = pos;
        pos_since = now;
      }
      if (lim != seen_limit) {
        seen_limit = lim;
        limit_since = now;
      }
      if (seen_pos != base_pos && now - pos_since >= SWITCH_STABLE_US) {
        base_pos = seen_pos;
        static const uint16_t MODE_FOR_POS[4] = {1, 2, 3, 4};  // Ladegeraet, Wechselrichter, Ein, Aus
        plan_write(mode, REG_MODE, MODE_FOR_POS[base_pos & 3]);
      }
      if (seen_limit != base_limit && now - limit_since >= LIMIT_STABLE_US) {
        base_limit = seen_limit;
        uint16_t v = base_limit;
        if (v < LIMIT_MIN) v = LIMIT_MIN;
        if (v > LIMIT_MAX) v = LIMIT_MAX;
        plan_write(limit, REG_LIMIT, v);
      }
    }

    const bool due_write = (mode.active && now >= mode.next_us) || (limit.active && now >= limit.next_us);
    if (now < next_poll && !due_write) continue;

    if (s < 0) {
      s = gx_connect();
      if (s < 0) {
        g_gx_errors++;
        next_poll = esp_timer_get_time() + POLL_US;
        for (Pending *p : {&mode, &limit}) {
          if (p->active && now >= p->next_us && ++p->tries >= MAX_TRIES) {
            p->active = false;
            g_writes_failed++;
            ESP_LOGE(TAG, "Register %u: GX nicht erreichbar, Befehl verworfen", p->reg);
          } else if (p->active) {
            p->next_us = now + RETRY_US;
          }
        }
        continue;
      }
    }

    bool ok = true;
    for (Pending *p : {&mode, &limit}) {
      if (!p->active || now < p->next_us) continue;
      uint16_t v = p->value;
      if (transact(s, 6, p->reg, &v)) {
        p->active = false;
        g_writes_ok++;
        ESP_LOGW(TAG, "Register %u = %u bestaetigt", p->reg, p->value);
        next_poll = 0;
      } else {
        ok = false;
        p->next_us = now + RETRY_US;
        if (++p->tries >= MAX_TRIES) {
          p->active = false;
          g_writes_failed++;
          ESP_LOGE(TAG, "Register %u = %u fehlgeschlagen, Befehl verworfen", p->reg, p->value);
        }
        break;
      }
    }

    if (ok && now >= next_poll) {
      uint16_t l = 0, st = 0, m = 0;
      ok = transact(s, 3, REG_LIMIT, &l) && transact(s, 3, REG_STATE, &st) && transact(s, 3, REG_MODE, &m);
      if (ok) {
        g_gx_limit = l;
        g_gx_state = st;
        g_gx_mode = m;
        g_gx_ok_us = esp_timer_get_time();
      }
      next_poll = esp_timer_get_time() + POLL_US;
    }
    if (!ok) {
      g_gx_errors++;
      lwip_close(s);
      s = -1;
      next_poll = esp_timer_get_time() + POLL_US;
    }
  }
}

inline void start(int rx_pin, int tx_pin, const char *gx_ip, uint8_t unit, bool write_enable) {
  g_tx_pin = tx_pin;
  g_gx_ip = gx_ip;
  g_unit = unit;
  g_write_enable = write_enable;
  gpio_set_direction((gpio_num_t) tx_pin, GPIO_MODE_OUTPUT);
  gpio_set_level((gpio_num_t) tx_pin, 1);  // Ruhepegel bis zum Senden
  vebus_sniffer::g_on_frame = on_frame;
  vebus_sniffer::start(rx_pin);
  xTaskCreatePinnedToCore(tx_task, "vebus_tx", 4096, nullptr, configMAX_PRIORITIES - 3, nullptr, 1);
  xTaskCreatePinnedToCore(gx_task, "vebus_gx", 4096, nullptr, 4, nullptr, 0);
  ESP_LOGW(TAG, "Schreiben auf den GX ist %s", write_enable ? "AN" : "aus");
}

inline void log_stats() {
  vebus_sniffer::log_stats();
  const int64_t age = g_gx_ok_us.load() == 0 ? -1 : (esp_timer_get_time() - g_gx_ok_us.load()) / 1000000;
  ESP_LOGI(TAG, "%s, gesendet %u, Schleifen %u, 0x38 %u, gewartet %u/%u | DMC 0x40 ok %u, schlecht %u, FC0F %u, "
           "Schalter %u, Grenze %u",
           g_blocked.load() ? "GESPERRT" : (g_sending.load() ? "sendet" : "hoert zu"), (unsigned) g_sent.load(),
           (unsigned) g_loops.load(), (unsigned) g_sent38.load(), (unsigned) g_busy_waits.load(),
           (unsigned) g_busy_timeouts.load(), (unsigned) g_panel_ok.load(),
           (unsigned) g_panel_bad.load(), (unsigned) g_fc0f.load(), (unsigned) g_dmc_pos.load(),
           (unsigned) g_dmc_limit.load());
  ESP_LOGI(TAG, "GX vor %d s: Mode %u, State %u, Grenze %u, LED %02X | geschrieben %u, fehlgeschlagen %u, GX-Fehler %u",
           (int) age, (unsigned) g_gx_mode.load(), (unsigned) g_gx_state.load(), (unsigned) g_gx_limit.load(),
           leds_from_state(g_gx_state.load()), (unsigned) g_writes_ok.load(), (unsigned) g_writes_failed.load(),
           (unsigned) g_gx_errors.load());
}

}  // namespace vebus_dmc_bridge
