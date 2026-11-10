// Uebersetzung DMC <-> Color Control GX. Das DMC haengt nur am ESP, der ESP spielt ihm gegenueber den MultiPlus.
//
// Zum DMC: Sync und uebrige Rahmen kommen aus der Aufzeichnung (vebus_dmc_replay.h), den LED-Rahmen 0x41 erzeugt
// die Firmware aus dem echten Zustand, den sie per Modbus TCP vom GX liest. Ohne Daten vom GX bleiben die LEDs aus.
// Vom DMC: Aendert sich die Schalterstellung oder die Stromgrenze im Rahmen 0x40, schreibt die Firmware EINMAL
// Register 33 (/Mode) oder 22 (Stromgrenze). Der erste Rahmen nach dem Start des DMC setzt nur den Ausgangswert und
// schreibt nichts: So gilt "letzter Befehl gewinnt", und ein Neustart schaltet den MultiPlus nicht.
//
// Geschrieben wird nur mit write_enable = true, sonst steht der geplante Befehl nur im Log.
// Die LEDs Ueberlast, Batterie und Temperatur kommen aus den Alarmregistern 34 bis 36 des GX: Warnung blinkt,
// Alarm leuchtet.
// Nur auf einer eigenen Leitung zum DMC verwenden, siehe docs/VEBUS-MITSCHNITT.md.

#pragma once

#include <cctype>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "hal/uart_ll.h"

#include "vebus_dmc_bench.h"

namespace vebus_dmc_bridge {

static const char *const TAG = "vebus_dmc_bridge";
using vebus_dmc_bench::build;
using vebus_dmc_bench::wait_until;

static constexpr uint16_t REG_LIMIT = 22, REG_STATE = 31, REG_MODE = 33;
// Alarme des VE.Bus-Geraets am GX: 0 ok, 1 Warnung, 2 Alarm (Victron CCGX-Modbus-TCP-Liste, com.victronenergy.vebus)
static constexpr uint16_t REG_ALARM_TEMP = 34, REG_ALARM_LOWBAT = 35, REG_ALARM_OVERLOAD = 36;
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
// Versuche zur FC-0F-Flut, gesetzt aus der YAML:
// g_live_time: Sync alle 20 ms im eigenen Raster, Zeitstempel in Sync und E4 aus der eigenen Uhr statt aus der
//              Aufzeichnung. g_fc_reply: 0 keine Antwort auf FC 0F, 1 Rahmen 38, 2 sofort Sync und danach 38.
// Zur Laufzeit umschaltbar ueber Textbefehle vom Mitschnitt-Client (tools/vebus_capture.py --script):
//   L0 L1 = g_live_time, R0 R1 R2 = g_fc_reply, Dxx = Rahmentyp xx (hex) nicht senden, Uxx = wieder senden, A = alle,
//   B<n> = Baudrate, O<n> = Abstand der Sync-Zeit, Wxxyy = LED-Test (LED-Byte xx, Blink-Byte yy), W = Test aus.
inline std::atomic<int> g_live_time{0};
inline std::atomic<int> g_fc_reply{1};
inline std::atomic<bool> g_drop[256];
inline std::atomic<int> g_sync_off{945};  // Befehl O<n>: Sync-Zeit minus angekuendigte Zeit aus E4, am echten Bus 910..956
inline TaskHandle_t g_tx_handle = nullptr;

// Vom GX
inline std::atomic<uint16_t> g_gx_limit{0}, g_gx_state{0}, g_gx_mode{0};
inline std::atomic<uint8_t> g_gx_alarm_temp{0}, g_gx_alarm_lowbat{0}, g_gx_alarm_overload{0};
// Test der Warn-LEDs ohne echten Alarm: Befehl Wxxyy setzt LED-Byte xx und Blink-Byte yy fest, W allein hebt es auf
inline std::atomic<int> g_test_led{-1}, g_test_blink{0}, g_test_b4{-1}, g_test_b5{-1};
// Test der Stromwerte im LED-Rahmen in 0,1 A: X<n> Minimum, Y<n> Maximum, Z<n> Grenze; Buchstabe allein hebt auf
inline std::atomic<int> g_test_imin{-1}, g_test_imax{-1}, g_test_ilim{-1};
// Anzeige nachfuehren: Das DMC begrenzt den Knopfwert auf Minimum und Maximum aus dem Rahmen 41 und behaelt den
// begrenzten Wert, bis der Knopf bewegt wird (ausprobiert 08.11.2026). Kommt eine neue Grenze vom GX, setzt die
// Firmware beide kurz auf diesen Wert. Danach zeigt das DMC ihn an, bis jemand am Knopf dreht.
static constexpr int64_t FORCE_US = 3000 * 1000;
inline std::atomic<int> g_force_limit{-1};
inline std::atomic<uint32_t> g_forced{0};  // Wxxyy[zz[ww]]: auch Byte 4 und 5
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
    if (g_tx_handle != nullptr) xTaskNotifyGive(g_tx_handle);  // weckt die Sendetask fuer die Antwort
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
  uint8_t led = fresh ? leds_from_state(g_gx_state.load()) : 0;
  uint8_t blink = 0;
  // Warn-LEDs stehen im Byte nach dem Blink-Byte, am DMC ausprobiert am 08.11.2026 (nicht wie im MK2-Dokument):
  //   Bit 0 Temperatur blinkt, Bit 1 Batterie blinkt, Bit 2 Ueberlast blinkt, Bit 3 Ueberlast und Batterie blinken
  //   (Ripple), Bit 0+4 Temperatur leuchtet, Bit 1+5 Batterie leuchtet, Bit 6 Ueberlast leuchtet.
  //   Bit 4, 5 und 7 allein zeigen nichts. GX-Alarm 1 = Warnung blinkt, 2 = Alarm leuchtet.
  uint8_t warn = 0;
  if (fresh) {
    const uint8_t t = g_gx_alarm_temp.load(), b = g_gx_alarm_lowbat.load(), o = g_gx_alarm_overload.load();
    if (t == 1) warn |= 0x01;
    if (t >= 2) warn |= 0x11;
    if (b == 1) warn |= 0x02;
    if (b >= 2) warn |= 0x22;
    if (o == 1) warn |= 0x04;
    if (o >= 2) warn |= 0x40;
  }
  if (g_test_led.load() >= 0) {
    led = (uint8_t) g_test_led.load();
    blink = (uint8_t) g_test_blink.load();
  }
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
  const uint8_t b4 = g_test_b4.load() >= 0 ? (uint8_t) g_test_b4.load() : warn;
  // 0x94 wie im Mitschnitt. Bit 0 oder 1 gesetzt: Anzeige wechselt zwischen 0.0 und AC2 bzw. AC3 (Eingangswahl).
  const uint8_t b5 = g_test_b5.load() >= 0 ? (uint8_t) g_test_b5.load() : 0x94;
  uint16_t lmax = LIMIT_MAX;
  if (fresh && g_force_limit.load() >= 0) lmin = lmax = (uint16_t) g_force_limit.load();
  if (g_test_imin.load() >= 0) lmin = (uint16_t) g_test_imin.load();
  if (g_test_imax.load() >= 0) lmax = (uint16_t) g_test_imax.load();
  const uint16_t lval = g_test_ilim.load() >= 0 ? (uint16_t) g_test_ilim.load() : limit;
  const uint8_t data[] = {0x41, 0x10, led, blink, b4, b5, (uint8_t) lmin, (uint8_t) (lmin >> 8),
                          (uint8_t) lmax, (uint8_t) (lmax >> 8), (uint8_t) lval, (uint8_t) (lval >> 8),
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

// Zeitlicher Aufbau der Rahmen des MultiPlus, Flankenmessung am VE.Bus 08.11.2026 (logs/vebus-20261108-edges-bus.log):
// Jeder Rahmen: zwei Adressbytes, dann 8,5 us Pause, dann der Rest dicht an dicht.
// Der Sync zusaetzlich: nach der Rahmennummer 98,6 us Pause, dann 55, dann 98,9 us Pause, dann Zeit, Pruefsumme, FF.
// Ohne diese Pausen hat das DMC den Sync des ESP nie mitgezaehlt. Zeiten ab Beginn des Rahmens in us:
static constexpr int64_t T_ADDR_REST_US = 88;   // 83 83 (79 us) + 8,5 us Pause
static constexpr int64_t T_SYNC_55_US = 266;    // Beginn des Bytes 55
static constexpr int64_t T_SYNC_TIME_US = 405;  // Beginn der Zeitbytes

inline void write_at(const uint8_t *p, size_t n, int64_t at) {
  while (esp_timer_get_time() < at) {
  }
  uart_ll_write_txfifo(UART_LL_GET_HW(vebus_sniffer::PORT), p, (uint32_t) n);
}

// Sendet einen fertigen Rahmen (mit Pruefsumme und FF) ab t0 mit den Pausen des MultiPlus.
inline void send_shaped(const uint8_t *out, size_t n, int64_t t0) {
  const bool sync = n >= 8 && out[2] == 0xFD && out[4] == 0x55;
  write_at(out, 2, t0);
  if (!sync) {
    write_at(out + 2, n - 2, t0 + T_ADDR_REST_US);
  } else {
    write_at(out + 2, 2, t0 + T_ADDR_REST_US);  // FD und Nummer
    write_at(out + 4, 1, t0 + T_SYNC_55_US);
    write_at(out + 5, n - 5, t0 + T_SYNC_TIME_US);
  }
  vebus_sniffer::push_record((uint32_t) t0, 4, out, n);  // eigener Rahmen in den Mitschnitt (T)
}

inline void send_frame(const uint8_t *head, size_t len) {
  uint8_t out[64];
  wait_bus_idle();
  const uint8_t nr = g_next_nr.load();
  const size_t n = build(head, len, nr, out);
  send_shaped(out, n, esp_timer_get_time() + 20);
  g_next_nr = (nr + 1) & 0x7F;
  g_sent++;
}

// Uhr des MultiPlus: 24 Bit, 0,4 us je Schritt (2,5 MHz). Der Sync traegt die Zeit seines Endes, im Mitschnitt
// immer 969 Schritte nach der Zeit, die der Rahmen E4 davor als Beginn der naechsten Periode ankuendigt.
static constexpr int64_t PERIOD_US = 20000;
static constexpr uint32_t LISTEN_MS = 300;
static constexpr int64_t E4_BEFORE_SYNC_US = 4600;

inline uint32_t ticks24(int64_t us) { return (uint32_t) ((us * 5 / 2) & 0xFFFFFF); }

// Sendet den Sync zeitgenau: Start bei target_us (oder sofort, wenn das schon vorbei ist). Der MultiPlus haelt den
// in E4 angekuendigten Zeitpunkt auf etwa 1 us ein, das DMC zaehlt einen Sync sonst nicht mit.
inline void send_sync_now(int64_t target_us) {
  static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
  uint8_t h[16];
  wait_bus_idle();
  int64_t start = esp_timer_get_time() + 40;  // Zeit zum Bauen des Rahmens
  if (target_us > start) start = target_us;
  const uint32_t t = (ticks24(start) + (uint32_t) g_sync_off.load()) & 0xFFFFFF;
  size_t n = 0;
  h[n++] = 0x83;
  h[n++] = 0x83;
  h[n++] = 0xFD;
  h[n++] = 0x00;
  h[n++] = 0x55;
  n = put(h, n, (uint8_t) t);
  n = put(h, n, (uint8_t) (t >> 8));
  n = put(h, n, (uint8_t) (t >> 16));
  uint8_t out[24];
  const uint8_t nr = g_next_nr.load();
  const size_t m = build(h, n, nr, out);
  (void) mux;
  send_shaped(out, m, start);
  g_next_nr = (nr + 1) & 0x7F;
  g_sent++;
}

// E4 aus der Aufzeichnung, Periode und angekuendigte Zeit ersetzt.
inline size_t head_e4_live(const uint8_t *rec, size_t len, int64_t next_sync_us, uint8_t *h) {
  uint8_t plain[32];
  size_t k = 0;
  for (size_t i = 4; i < len && k < sizeof(plain); i++) {
    if (rec[i] == 0xFA && i + 1 < len) {
      plain[k++] = (uint8_t) (rec[++i] + 0x80);
    } else {
      plain[k++] = rec[i];
    }
  }
  if (k >= 7) {
    const uint32_t t = ticks24(next_sync_us);
    plain[2] = 0x50;  // Periode 50000 Schritte = 20 ms
    plain[3] = 0xC3;
    plain[4] = (uint8_t) t;
    plain[5] = (uint8_t) (t >> 8);
    plain[6] = (uint8_t) (t >> 16);
  }
  size_t n = 0;
  h[n++] = 0x83;
  h[n++] = 0x83;
  h[n++] = 0xFE;
  h[n++] = 0x00;
  for (size_t i = 0; i < k; i++) n = put(h, n, plain[i]);
  return n;
}

// Versorgung des DMC: Mini560 (9 V) mit EN an g_pwr_pin, 10 kOhm nach GND. Das DMC haengt sich auf, wenn es
// ohne Busverkehr startet (08.11.2026). Deshalb erst senden, dann einschalten, und bei Schweigen neu starten.
static constexpr int64_t PWR_ON_DELAY_US = 500000;           // nach dem ersten Senden
static constexpr int64_t PWR_FIRST_FRAME_US = 10 * 1000000;  // Zeit bis zum ersten Rahmen 40 nach dem Einschalten
static constexpr int64_t PWR_LOST_US = 10 * 1000000;         // so lange ohne Rahmen 40 gilt das DMC als haengend
static constexpr int64_t PWR_OFF_US = 2 * 1000000;           // Pause beim Neustart
static constexpr int64_t PWR_BACKOFF_US = 60 * 1000000;      // nach 3 vergeblichen Neustarts in Folge
inline int g_pwr_pin = -1;
inline std::atomic<uint32_t> g_dmc_restarts{0};
inline std::atomic<bool> g_pwr_on{false}, g_pwr_restart_req{false};

inline void pwr_set(bool on) {
  if (g_pwr_pin < 0) return;
  gpio_set_level((gpio_num_t) g_pwr_pin, on ? 1 : 0);
  g_pwr_on = on;
}

inline void pwr_task(void *) {
  while (!g_sending.load()) {
    if (g_blocked.load()) {  // am echten VE.Bus: DMC bleibt aus
      vTaskDelete(nullptr);
      return;
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
  vTaskDelay(pdMS_TO_TICKS(PWR_ON_DELAY_US / 1000));
  pwr_set(true);
  ESP_LOGW(TAG, "DMC eingeschaltet (GPIO%d)", g_pwr_pin);
  int64_t on_since = esp_timer_get_time();
  int fails = 0;
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(200));
    const int64_t now = esp_timer_get_time();
    const int64_t last = g_dmc_us.load();
    const bool seen = last > on_since;  // Rahmen 40 seit dem letzten Einschalten
    if (seen) fails = 0;
    const char *why = nullptr;
    if (g_pwr_restart_req.exchange(false)) {
      why = "Befehl";
    } else if (!seen && now - on_since > (fails >= 3 ? PWR_BACKOFF_US : PWR_FIRST_FRAME_US)) {
      why = "kein Rahmen 40 nach dem Einschalten";
    } else if (seen && now - last > PWR_LOST_US) {
      why = "keine Rahmen 40 mehr";
    }
    if (why == nullptr) continue;
    if (!seen) fails++;
    g_dmc_restarts++;
    ESP_LOGW(TAG, "DMC neu starten: %s (Fehlversuche in Folge %d)", why, fails);
    pwr_set(false);
    vTaskDelay(pdMS_TO_TICKS(PWR_OFF_US / 1000));
    pwr_set(true);
    on_since = esp_timer_get_time();
  }
}

inline void on_command(const char *text) {
  for (const char *p = text; *p != 0; p++) {
    const char c = *p;
    if (c == 'P') {
      g_pwr_restart_req = true;  // DMC aus- und wieder einschalten
    } else if ((c == 'L' || c == 'R') && p[1] >= '0' && p[1] <= '9') {
      (c == 'L' ? g_live_time : g_fc_reply) = p[1] - '0';
      p++;
    } else if ((c == 'D' || c == 'U') && p[1] != 0 && p[2] != 0) {
      const char hex[3] = {p[1], p[2], 0};
      g_drop[strtoul(hex, nullptr, 16) & 0xFF] = (c == 'D');
      p += 2;
    } else if (c == 'W') {
      char hex[9] = {0};
      int k = 0;
      while (k < 8 && isxdigit((unsigned char) p[1 + k])) {
        hex[k] = p[1 + k];
        k++;
      }
      auto byte_at = [&](int i) { char h[3] = {hex[i], hex[i + 1], 0}; return (int) strtol(h, nullptr, 16); };
      g_test_led = k >= 4 ? byte_at(0) : -1;
      g_test_blink = k >= 4 ? byte_at(2) : 0;
      g_test_b4 = k >= 6 ? byte_at(4) : -1;
      g_test_b5 = k >= 8 ? byte_at(6) : -1;
      p += k;
    } else if (c == 'X' || c == 'Y' || c == 'Z') {
      std::atomic<int> &t = c == 'X' ? g_test_imin : (c == 'Y' ? g_test_imax : g_test_ilim);
      if (p[1] >= '0' && p[1] <= '9') {
        t = (int) strtol(p + 1, nullptr, 10);
        while (p[1] >= '0' && p[1] <= '9') p++;
      } else {
        t = -1;
      }
    } else if (c == 'B') {
      const int baud = (int) strtol(p + 1, nullptr, 10);
      if (baud >= 200000 && baud <= 300000) {
        uart_set_baudrate(vebus_sniffer::PORT, (uint32_t) baud);
        vebus_sniffer::g_baud = baud;
      }
      while (p[1] >= '0' && p[1] <= '9') p++;
    } else if (c == 'O') {
      g_sync_off = (int) strtol(p + 1, nullptr, 10);
      while (p[1] >= '0' && p[1] <= '9') p++;
    } else if (c == 'A') {
      for (auto &d : g_drop) d = false;
    }
  }
  ESP_LOGW(TAG, "Befehl '%s': eigene Zeitbasis %d, Antwort auf FC 0F %d, %d Baud", text, g_live_time.load(),
           g_fc_reply.load(), vebus_sniffer::g_baud);
}

inline void tx_task(void *) {
  g_tx_handle = xTaskGetCurrentTaskHandle();
  while (!uart_is_driver_installed(vebus_sniffer::PORT)) vTaskDelay(pdMS_TO_TICKS(10));
  // Kurz zuhoeren: Der MultiPlus sendet alle 20 ms, 300 ms reichen fuer die Sperre. Laenger nicht, das DMC haengt
  // sich bei Stille nach dem Einschalten auf.
  vTaskDelay(pdMS_TO_TICKS(LISTEN_MS));
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
  int64_t sync_due = due + PERIOD_US;  // nur mit g_live_time
  int64_t last_38 = 0, last_reply = 0;
  for (;;) {
    const uint8_t *entry = vebus_dmc_replay::DATA + pos;
    const uint16_t delta = (uint16_t) (entry[0] | (entry[1] << 8));
    const uint8_t len = entry[2];
    const uint8_t *rec = entry + 3;
    const bool is_sync = len >= 5 && rec[2] == 0xFD && rec[4] == 0x55;
    const bool is_e4 = len >= 5 && rec[2] == 0xFE && rec[4] == 0xE4;
    due += (int64_t) delta * 100;
    if (g_live_time && is_sync) due = sync_due - 420;  // Vorlauf fuer die Ruhepruefung (300 us) in send_sync_now
    if (g_live_time && is_e4) due = sync_due - E4_BEFORE_SYNC_US;
    // Warten, dabei sofort auf FC 0F antworten (Versuch 2: wie der MultiPlus beim Busstart mit Sync und 38)
    for (;;) {
      const int64_t left = due - esp_timer_get_time();
      if (left <= 0) break;
      if (left > 1000) {
        ulTaskNotifyTake(pdTRUE, 1);
      } else {
        esp_rom_delay_us((uint32_t) left);
      }
      if (g_fc_reply == 2 && g_want_38.exchange(false)) {
        const int64_t now = esp_timer_get_time();
        if (now - last_reply > 10000) {
          send_sync_now(0);
          send_frame(HEAD_38, sizeof(HEAD_38));
          g_sent38++;
          last_reply = now;
        }
      }
    }
    if (len >= 5 && rec[2] == 0xFE && g_drop[rec[4]].load()) {
      // Versuch: diesen Rahmentyp auslassen
    } else if (g_live_time && is_sync) {
      send_sync_now(sync_due);
      sync_due += PERIOD_US;
      if (sync_due < esp_timer_get_time()) sync_due = esp_timer_get_time() + PERIOD_US;
    } else if (g_live_time && is_e4) {
      const size_t n = head_e4_live(rec, len, sync_due, head);
      send_frame(head, n);
    } else if (len >= 5 && rec[2] == 0xFE && rec[4] == 0x41) {
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
    if (g_fc_reply == 1 && g_want_38.exchange(false) && now - last_38 > 200000) {
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
  int64_t force_until = 0;
  // Nachpruefen der Schaltbefehle: Nach laengerem Aus setzte der GX Mode 3 nach rund 10 s selbst wieder auf 4
  // (08.11.2026, zweimal nachgestellt; Einschalten per VRM klappte). Zeigte der GX den neuen Wert schon einmal und
  // springt er innerhalb von VERIFY_US auf den Wert vor dem Befehl zurueck, waehrend der Schalter am DMC unveraendert
  // steht, schreibt die Firmware erneut. Ohne "schon einmal gezeigt" schrieb sie 0,3 s nach dem Befehl ein zweites
  // Mal, weil der GX den alten Wert noch meldete (08.11.2026 14:51:32).
  static constexpr int64_t VERIFY_US = 30 * 1000 * 1000;
  static constexpr int VERIFY_MAX = 5;
  uint16_t verify_value = 0, verify_prev = 0;
  int64_t verify_until = 0;
  int verify_tries = 0;
  bool verify_seen = false;  // der GX hat den neuen Wert schon einmal gezeigt; erst danach zaehlt ein Zuruecksetzen
  // Stromgrenze bei Aus: Der GX bestaetigt das Schreiben, behaelt den Wert aber nicht (08.11.2026, Knopf bei Aus auf
  // 16,0 A, nach dem Einschalten stand der GX weiter auf 9,0 A). Die Firmware schreibt ihn nach dem Einschalten erneut.
  bool limit_dirty = false;
  uint16_t limit_dirty_value = 0;
  int last_gx_limit = -1;  // zuletzt gelesene Grenze vom GX, -1 = noch keine
  bool sync_display = false;  // nach dem Start des DMC einmal auf den GX-Wert bringen

  // Anzeige des DMC auf den GX-Wert bringen, ohne dass daraus ein Schreibbefehl wird.
  auto force_display = [&](uint16_t v, int64_t now) {
    if (v < LIMIT_MIN) v = LIMIT_MIN;
    if (v > LIMIT_MAX) v = LIMIT_MAX;
    if (v == seen_limit) return;
    base_limit = v;  // das DMC meldet gleich diesen Wert, das ist keine Aenderung am Knopf
    g_force_limit = v;
    force_until = now + FORCE_US;
    g_forced++;
    ESP_LOGI(TAG, "Anzeige des DMC auf %u (0,1 A) wie am GX", v);
  };

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
        sync_display = true;
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
        verify_until = 0;  // neuer Befehl vom DMC, alte Pruefung hinfaellig
        verify_tries = 0;
      }
      if (force_until != 0 && now >= force_until) {
        force_until = 0;
        if (seen_limit != (uint16_t) g_force_limit.load()) {
          // Das DMC hat den Wert nicht uebernommen: seinen Wert als Ausgangswert nehmen, nicht schreiben
          ESP_LOGW(TAG, "Anzeige nicht uebernommen, DMC bleibt bei %u", seen_limit);
          base_limit = seen_limit;
        }
        g_force_limit = -1;
      }
      // Erst wenn der ESP sendet: Nach einem Neustart hoert er zuerst 5 s nur zu, das DMC sendet trotzdem.
      // Am 08.11.2026 lief die Nachfuehrung dadurch ins Leere, und der Knopfwert 16,0 A ging an den GX.
      if (sync_display && last_gx_limit >= 0 && !limit.active && g_sending.load()) {
        sync_display = false;
        force_display((uint16_t) last_gx_limit, now);
      }
      if (force_until == 0 && seen_limit != base_limit && now - limit_since >= LIMIT_STABLE_US) {
        base_limit = seen_limit;
        uint16_t v = base_limit;
        if (v < LIMIT_MIN) v = LIMIT_MIN;
        if (v > LIMIT_MAX) v = LIMIT_MAX;
        plan_write(limit, REG_LIMIT, v);
        if (g_gx_mode.load() == 4) {
          limit_dirty = true;
          limit_dirty_value = v;
        }
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
        if (p == &mode) {
          if (verify_until == 0) verify_prev = g_gx_mode.load();  // Wert vor dem ersten Befehl
          verify_value = p->value;
          verify_until = now + VERIFY_US;
          verify_seen = false;
        }
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
      uint16_t l = 0, st = 0, m = 0, at = 0, ab = 0, ao = 0;
      ok = transact(s, 3, REG_LIMIT, &l) && transact(s, 3, REG_STATE, &st) && transact(s, 3, REG_MODE, &m) &&
           transact(s, 3, REG_ALARM_TEMP, &at) && transact(s, 3, REG_ALARM_LOWBAT, &ab) &&
           transact(s, 3, REG_ALARM_OVERLOAD, &ao);
      if (ok) {
        // Neue Grenze vom GX, nicht von uns geschrieben: Anzeige des DMC nachfuehren
        if (baseline && last_gx_limit >= 0 && l != (uint16_t) last_gx_limit && !limit.active && l != seen_limit &&
            !(limit_dirty && m == 4)) {
          force_display(l, esp_timer_get_time());
          limit_dirty = false;  // neuere Grenze vom GX oder aus VRM gewinnt
        }
        if (limit_dirty && m != 4 && st != 0 && !limit.active) {
          limit_dirty = false;
          if (l != limit_dirty_value) {
            ESP_LOGW(TAG, "MultiPlus laeuft wieder, Grenze %u vom DMC erneut (GX hatte %u)", limit_dirty_value, l);
            plan_write(limit, REG_LIMIT, limit_dirty_value);
          }
        }
        last_gx_limit = l;
        g_gx_limit = l;
        if (verify_until != 0) {
          static const uint16_t MODE_FOR_POS2[4] = {1, 2, 3, 4};
          const int64_t t = esp_timer_get_time();
          if (m == verify_value) verify_seen = true;
          if (t > verify_until) {
            verify_until = 0;
          } else if (verify_seen && m == verify_prev && m != verify_value && MODE_FOR_POS2[base_pos & 3] == verify_value &&
                     !mode.active) {
            if (++verify_tries > VERIFY_MAX) {
              ESP_LOGE(TAG, "GX setzt Mode immer wieder auf %u zurueck, gebe auf", m);
              verify_until = 0;
              g_writes_failed++;
            } else {
              ESP_LOGW(TAG, "GX hat Mode auf %u zurueckgesetzt, schreibe %u erneut (%d)", m, verify_value, verify_tries);
              mode.active = true;
              mode.reg = REG_MODE;
              mode.value = verify_value;
              mode.tries = 0;
              mode.next_us = 0;
            }
          }
        }
        g_gx_state = st;
        g_gx_mode = m;
        g_gx_alarm_temp = (uint8_t) at;
        g_gx_alarm_lowbat = (uint8_t) ab;
        g_gx_alarm_overload = (uint8_t) ao;
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

// Bus-Teil: so frueh wie moeglich, vor dem WLAN. Das DMC haengt sich auf, wenn nach seinem Einschalten einige
// Sekunden nichts auf dem Bus kommt (Einbau Loesung B, 08.11.2026).
inline void start_bus(int rx_pin, int tx_pin, int pwr_pin, bool live_time, int fc_reply, int baud) {
  g_pwr_pin = pwr_pin;
  if (pwr_pin >= 0) {
    gpio_set_direction((gpio_num_t) pwr_pin, GPIO_MODE_OUTPUT);
    pwr_set(false);  // DMC aus, bis der ESP sendet
  }
  vebus_sniffer::g_baud = baud;
  g_live_time = live_time;
  g_fc_reply = fc_reply;
  g_tx_pin = tx_pin;
  gpio_set_direction((gpio_num_t) tx_pin, GPIO_MODE_OUTPUT);
  gpio_set_level((gpio_num_t) tx_pin, 1);  // Ruhepegel bis zum Senden
  vebus_sniffer::g_on_frame = on_frame;
  vebus_sniffer::g_on_command = on_command;
  vebus_sniffer::start_rx(rx_pin);
  xTaskCreatePinnedToCore(tx_task, "vebus_tx", 4096, nullptr, configMAX_PRIORITIES - 3, nullptr, 1);
  if (pwr_pin >= 0) xTaskCreatePinnedToCore(pwr_task, "vebus_pwr", 3072, nullptr, 3, nullptr, 0);
}

// Netzwerk-Teil: GX und Mitschnitt-Server, nach dem Netzwerk-Stack
inline void start_net(const char *gx_ip, uint8_t unit, bool write_enable) {
  g_gx_ip = gx_ip;
  g_unit = unit;
  g_write_enable = write_enable;
  vebus_sniffer::start_tcp();
  xTaskCreatePinnedToCore(gx_task, "vebus_gx", 4096, nullptr, 4, nullptr, 0);
  ESP_LOGW(TAG, "Schreiben auf den GX ist %s, eigene Zeitbasis %s, Antwort auf FC 0F: %d", write_enable ? "AN" : "aus",
           g_live_time.load() ? "an" : "aus", g_fc_reply.load());
}

inline void log_stats() {
  vebus_sniffer::log_stats();
  const int64_t age = g_gx_ok_us.load() == 0 ? -1 : (esp_timer_get_time() - g_gx_ok_us.load()) / 1000000;
  ESP_LOGI(TAG, "%s, gesendet %u, Schleifen %u, 0x38 %u, gewartet %u/%u | DMC %s, Neustarts %u, 0x40 ok %u, "
           "schlecht %u, FC0F %u, Schalter %u, Grenze %u",
           g_blocked.load() ? "GESPERRT" : (g_sending.load() ? "sendet" : "hoert zu"), (unsigned) g_sent.load(),
           (unsigned) g_loops.load(), (unsigned) g_sent38.load(), (unsigned) g_busy_waits.load(),
           (unsigned) g_busy_timeouts.load(), g_pwr_pin < 0 ? "Strom fest" : (g_pwr_on.load() ? "an" : "aus"),
           (unsigned) g_dmc_restarts.load(), (unsigned) g_panel_ok.load(),
           (unsigned) g_panel_bad.load(), (unsigned) g_fc0f.load(), (unsigned) g_dmc_pos.load(),
           (unsigned) g_dmc_limit.load());
  ESP_LOGI(TAG, "GX vor %d s: Mode %u, State %u, Grenze %u, LED %02X, Alarme T/B/U %u/%u/%u | geschrieben %u, "
           "fehlgeschlagen %u, GX-Fehler %u",
           (int) age, (unsigned) g_gx_mode.load(), (unsigned) g_gx_state.load(), (unsigned) g_gx_limit.load(),
           leds_from_state(g_gx_state.load()), (unsigned) g_gx_alarm_temp.load(), (unsigned) g_gx_alarm_lowbat.load(),
           (unsigned) g_gx_alarm_overload.load(), (unsigned) g_writes_ok.load(), (unsigned) g_writes_failed.load(),
           (unsigned) g_gx_errors.load());
}

}  // namespace vebus_dmc_bridge
